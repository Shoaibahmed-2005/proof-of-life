"""
Verification pipeline for POST /api/v1/auth/verify (build-prompt §5.2).

Fail fast, in this order:
 1. Signature is valid ECDSA-SHA256 over the exact payload bytes (P-256 key).
 2. Payload parses into the schema.
 3. Session exists, has the right purpose, matching nonce, is not expired, and
    is claimed atomically (each session/nonce is usable once).
 1b. Device binding — needs the pensioner, which is only known from the
    session: LIFE_CERTIFICATE requires the key registered for that pensioner;
    ENROLLMENT registers the key (bound once the officer approves).
 4. Timestamp freshness (+ consent recorded, for the new purposes).
 5. Liveness: BPM range, SNR ≥ minimum, liveness_passed.
 6. Challenge: matches the one issued for the session and was passed.
 7. Face match (LIFE_CERTIFICATE): 1:1 against this pensioner's template only.
 8. Decide, update state, write the ledger, and return events to push.

The pipeline is synchronous (DB work); the router publishes the returned
events over WebSocket.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import (
    AuthSession, BiometricTemplate, CertificateStatus, Device, KeyType,
    LifeCertificate, Pensioner, PensionerStatus, SessionPurpose, SessionStatus,
)
from app.db.types import utcnow
from app.schemas.auth import BiometricPayload, VerifyRequest, VerifyResponse
from app.services import face_match, pensioners
from app.services import session as sessions
from app.services.crypto import (
    InvalidPublicKeyError, SignatureVerificationError, load_public_key_from_der,
    public_key_to_pem, require_p256, same_public_key, verify_signature,
)
from app.services.ledger import LedgerEvent, ledger
from app.services.liveness import SpoofingDetectedError, check_liveness, validate_liveness
from app.services.score_log import log_score

logger = logging.getLogger(__name__)


# Only biometric failures from the pensioner's own registered device count
# toward freezing. Otherwise anyone who knows a pension ID could freeze it
# from their own phone (DEVICE_MISMATCH) or with malformed requests.
FREEZE_COUNTED_FAILURES = {"NO_PULSE", "CHALLENGE_FAILED", "FACE_MISMATCH"}


# ── Result types ────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    response: VerifyResponse
    # (session_id or None, event) pairs for the router to publish
    events: list[tuple[str | None, dict[str, Any]]] = field(default_factory=list)


class InvalidPublicKey(Exception):
    """The request's public key cannot be parsed → HTTP 400 (legacy behaviour)."""


class _Reject(Exception):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _denied(session_id: str, code: str, reason: str,
            purpose: SessionPurpose | None = None) -> VerificationResult:
    return VerificationResult(VerifyResponse(
        status="ACCESS_DENIED", session_id=session_id, reason=reason,
        reason_code=code, purpose=purpose, outcome="REJECTED" if purpose else None,
    ))


def key_fingerprint(public_key_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()


# ── Entry point ─────────────────────────────────────────────────────────

def verify(db: Session, request: VerifyRequest) -> VerificationResult:
    # Step 1: signature over the exact bytes the phone signed.
    try:
        require_p256(load_public_key_from_der(request.public_key))
        verify_signature(request.payload, request.signature, request.public_key)
    except InvalidPublicKeyError as e:
        raise InvalidPublicKey(str(e)) from e
    except SignatureVerificationError as e:
        logger.warning("Signature verification failed: %s", e)
        return _denied("unknown", "INVALID_SIGNATURE", "Cryptographic signature verification failed")

    # Step 2: parse.
    try:
        payload = BiometricPayload(**json.loads(base64.b64decode(request.payload)))
    except Exception as e:
        logger.warning("Payload decode failed: %s", e)
        return _denied("unknown", "INVALID_PAYLOAD", f"Invalid payload format: {e}")

    sid = payload.session_id

    # Step 3: session checks, then claim (single use).
    session = sessions.get(db, sid)
    if session is None:
        return _denied(sid, "SESSION_NOT_FOUND", "Session not found or expired", payload.purpose)
    if session.purpose is not payload.purpose:
        return _denied(sid, "PURPOSE_MISMATCH",
                       f"Payload is for {payload.purpose.value} but the session is for "
                       f"{session.purpose.value}", payload.purpose)
    if session.purpose is not SessionPurpose.AUTH and payload.nonce != session.nonce:
        return _denied(sid, "NONCE_MISMATCH", "Session nonce does not match", payload.purpose)
    if sessions.is_expired(session):
        return _denied(sid, "SESSION_EXPIRED", "Session has expired", payload.purpose)
    if session.status is not SessionStatus.PENDING or not sessions.claim(db, sid):
        db.refresh(session)
        return _denied(sid, "SESSION_ALREADY_USED", f"Session is already {session.status.value}",
                       payload.purpose)
    db.refresh(session)

    # From here the session is consumed: every outcome finishes it.
    try:
        if session.purpose is SessionPurpose.AUTH:
            return _verify_auth(db, session, payload)
        if session.purpose is SessionPurpose.ENROLLMENT:
            return _verify_enrollment(db, session, payload, request)
        return _verify_life_certificate(db, session, payload, request)
    except _Reject as r:
        return _finish_rejected(db, session, payload, r.code, r.reason)
    except Exception:
        # Never leave a consumed session stuck in PROCESSING, and never count
        # our own bug as a failed attempt against the pensioner.
        logger.exception("Unexpected error verifying session %s", sid)
        db.rollback()
        session = sessions.get(db, sid)
        reason = "Internal error during verification; please try again"
        sessions.finish(db, session, SessionStatus.REJECTED, outcome="REJECTED",
                        reason_code="INTERNAL_ERROR", reason=reason)
        return VerificationResult(
            VerifyResponse(status="ACCESS_DENIED", session_id=sid, reason=reason,
                           reason_code="INTERNAL_ERROR", purpose=session.purpose, outcome="REJECTED"),
            [(sid, _base_event("REJECTED", session, reason_code="INTERNAL_ERROR", reason=reason))],
        )


# ── Shared steps ────────────────────────────────────────────────────────

def _check_freshness(session: AuthSession, payload: BiometricPayload) -> None:
    now = utcnow()
    skew = settings.TIMESTAMP_MAX_SKEW_SECONDS
    age = (now - payload.timestamp).total_seconds()
    if abs(age) > skew:
        raise _Reject("STALE_PAYLOAD",
                      f"Payload timestamp is {age:.0f}s from server time (max {skew}s). "
                      "Check the phone's clock.")
    if (payload.timestamp - session.created_at).total_seconds() < -skew:
        raise _Reject("STALE_PAYLOAD", "Payload was created before this session")


def _check_consent(db: Session, session: AuthSession, payload: BiometricPayload) -> None:
    if payload.consent is not True:
        raise _Reject("CONSENT_MISSING", "The pensioner's consent to the scan was not recorded")
    session.consent_at = utcnow()
    db.add(session)


def _check_liveness(payload: BiometricPayload) -> None:
    try:
        check_liveness(payload.bpm, payload.snr, bool(payload.liveness_passed))
    except SpoofingDetectedError as e:
        raise _Reject(e.reason_code, str(e)) from e


def _check_challenge(session: AuthSession, payload: BiometricPayload) -> None:
    if payload.challenge_id != session.challenge_id:
        raise _Reject("CHALLENGE_MISMATCH", "Challenge does not match the one issued for this session")
    if not payload.challenge_passed:
        raise _Reject("CHALLENGE_FAILED",
                      "Challenge failed: the requested action was not performed in time")


def _base_event(event: str, session: AuthSession, **extra: Any) -> dict[str, Any]:
    return {"event": event, "session_id": session.session_id,
            "purpose": session.purpose.value, "pensioner_id": session.pensioner_id,
            "at": utcnow().isoformat(), **extra}


def _finish_rejected(db: Session, session: AuthSession, payload: BiometricPayload,
                     code: str, reason: str) -> VerificationResult:
    """Records a rejection after the session was claimed and returns the events."""
    events: list[tuple[str | None, dict]] = []
    certificate_id = None
    if session.purpose is SessionPurpose.LIFE_CERTIFICATE and session.pensioner_id:
        pensioner = db.get(Pensioner, session.pensioner_id)
        cert = LifeCertificate(
            pensioner_id=session.pensioner_id, year=utcnow().year,
            status=CertificateStatus.REJECTED, bpm=payload.bpm, snr=payload.snr,
            challenge_type=session.challenge_type, challenge_passed=payload.challenge_passed,
            key_type=payload.key_security_level, session_id=session.session_id,
            reason_code=code, reason=reason,
        )
        db.add(cert)
        db.flush()
        certificate_id = cert.id
        entry = ledger.append(db, LedgerEvent.CERTIFICATE_REJECTED, {
            "certificate_id": cert.id, "pensioner_id": session.pensioner_id,
            "session_id": session.session_id, "reason_code": code, "at": cert.created_at.isoformat(),
        }, ref=f"certificate:{cert.id}")
        cert.ledger_hash = entry.entry_hash
        db.add(cert)
        if pensioner and code in FREEZE_COUNTED_FAILURES and pensioners.record_failure(db, pensioner):
            events.append((session.session_id, _base_event(
                "STATUS_CHANGED", session, pension_status=PensionerStatus.FROZEN.value,
                reason=pensioner.status_reason)))

    sessions.finish(db, session, SessionStatus.REJECTED, outcome="REJECTED",
                    reason_code=code, reason=reason, certificate_id=certificate_id,
                    bpm=payload.bpm, device_id=payload.device_id)
    events.insert(0, (session.session_id, _base_event(
        "REJECTED", session, reason_code=code, reason=reason, certificate_id=certificate_id)))
    logger.warning("Session %s rejected: %s (%s)", session.session_id, code, reason)
    return VerificationResult(VerifyResponse(
        status="ACCESS_DENIED", session_id=session.session_id, reason=reason, reason_code=code,
        purpose=session.purpose, outcome="REJECTED", certificate_id=certificate_id,
    ), events)


# ── AUTH (original login demo) ──────────────────────────────────────────

def _verify_auth(db: Session, session: AuthSession, payload: BiometricPayload) -> VerificationResult:
    age = (utcnow() - payload.timestamp).total_seconds()
    if abs(age) > settings.SESSION_EXPIRY_SECONDS:
        raise _Reject("STALE_PAYLOAD", "Payload timestamp is too old")
    try:
        validate_liveness(bpm=payload.bpm, snr=payload.snr, variance=payload.variance)
    except SpoofingDetectedError as e:
        raise _Reject(e.reason_code, str(e)) from e

    sessions.finish(db, session, SessionStatus.GRANTED, outcome="GRANTED",
                    bpm=payload.bpm, device_id=payload.device_id)
    event = {"event": "ACCESS_GRANTED", "session_id": session.session_id,
             "bpm": payload.bpm, "device_id": payload.device_id,
             "granted_at": utcnow().isoformat()}
    return VerificationResult(
        VerifyResponse(status="ACCESS_GRANTED", session_id=session.session_id,
                       purpose=session.purpose, outcome="GRANTED"),
        [(session.session_id, event)],
    )


# ── ENROLLMENT ──────────────────────────────────────────────────────────

def _verify_enrollment(db: Session, session: AuthSession, payload: BiometricPayload,
                       request: VerifyRequest) -> VerificationResult:
    pensioner = db.get(Pensioner, session.pensioner_id) if session.pensioner_id else None
    if pensioner is None:
        raise _Reject("PENSIONER_NOT_FOUND", "Pensioner record not found")
    if pensioner.status is not PensionerStatus.PENDING_ENROLLMENT:
        raise _Reject("ALREADY_REGISTERED", "This pensioner is already registered")

    _check_freshness(session, payload)
    _check_consent(db, session, payload)
    _check_liveness(payload)
    _check_challenge(session, payload)

    model_version = payload.model_version or settings.FACE_MODEL_VERSION
    try:
        template = face_match.validate_embedding(payload.reference_template or [])
    except face_match.EmbeddingError as e:
        raise _Reject("INVALID_TEMPLATE", f"Reference template rejected: {e}") from e

    # Store the template (not yet trusted) and the device key (inactive until approval).
    # A retry while still pending replaces the previous capture.
    enc = face_match.encrypt_vector(template)
    existing = db.exec(select(BiometricTemplate)
                       .where(BiometricTemplate.pensioner_id == pensioner.id)).first()
    if existing:
        existing.anchor_template = enc
        existing.current_template = enc
        existing.embedding_dim = len(template)
        existing.model_version = model_version
        existing.updated_at = utcnow()
        db.add(existing)
    else:
        db.add(BiometricTemplate(pensioner_id=pensioner.id, anchor_template=enc,
                                 current_template=enc, embedding_dim=len(template),
                                 model_version=model_version))
    for old in db.exec(select(Device).where(Device.pensioner_id == pensioner.id)
                       .where(Device.active == False)).all():  # noqa: E712
        db.delete(old)
    key_type = payload.key_security_level or KeyType.UNKNOWN
    db.add(Device(pensioner_id=pensioner.id, public_key_pem=public_key_to_pem(request.public_key),
                  key_type=key_type, device_id=payload.device_id, active=False))

    sessions.finish(db, session, SessionStatus.COMPLETED, outcome="CAPTURED",
                    bpm=payload.bpm, device_id=payload.device_id, commit=False)
    ledger.append(db, LedgerEvent.REGISTRATION_CAPTURED, {
        "pensioner_id": pensioner.id, "session_id": session.session_id,
        "key_fingerprint": key_fingerprint(request.public_key), "key_type": key_type.value,
        "model_version": model_version, "frames_used": payload.frames_used,
        "at": utcnow().isoformat(),
    }, ref=f"pensioner:{pensioner.id}")

    event = _base_event("ENROLLMENT_CAPTURED", session, bpm=payload.bpm, snr=payload.snr,
                        frames_used=payload.frames_used, key_type=key_type.value,
                        challenge_type=session.challenge_type)
    return VerificationResult(VerifyResponse(
        status="ACCESS_GRANTED", session_id=session.session_id, purpose=session.purpose,
        outcome="CAPTURED",
    ), [(session.session_id, event)])


# ── LIFE_CERTIFICATE ────────────────────────────────────────────────────

def _verify_life_certificate(db: Session, session: AuthSession, payload: BiometricPayload,
                             request: VerifyRequest) -> VerificationResult:
    pensioner = db.get(Pensioner, session.pensioner_id) if session.pensioner_id else None
    if pensioner is None:
        raise _Reject("PENSIONER_NOT_FOUND", "Pensioner record not found")

    # Step 1b: the key must be the device registered for this pensioner.
    device = db.exec(select(Device).where(Device.pensioner_id == pensioner.id)
                     .where(Device.active == True)).first()  # noqa: E712
    if device is None:
        raise _Reject("DEVICE_NOT_REGISTERED", "No registered device for this pensioner")
    if not same_public_key(request.public_key, device.public_key_pem):
        raise _Reject("DEVICE_MISMATCH",
                      "This phone is not the device registered for this pensioner")

    _check_freshness(session, payload)
    _check_consent(db, session, payload)
    _check_liveness(payload)
    _check_challenge(session, payload)

    # Step 7: 1:1 face match against this pensioner's template only.
    template = db.exec(select(BiometricTemplate)
                       .where(BiometricTemplate.pensioner_id == pensioner.id)).first()
    if template is None:
        raise _Reject("TEMPLATE_MISSING", "No registered face template for this pensioner")
    if payload.model_version and payload.model_version != template.model_version:
        raise _Reject("MODEL_MISMATCH",
                      f"App face model {payload.model_version} differs from the registered "
                      f"{template.model_version}; please re-register")
    try:
        probe = face_match.validate_embedding(payload.face_embedding or [], template.embedding_dim)
    except face_match.EmbeddingError as e:
        raise _Reject("INVALID_EMBEDDING", f"Face embedding rejected: {e}") from e

    current = face_match.decrypt_vector(template.current_template)
    anchor = face_match.decrypt_vector(template.anchor_template)
    decision = face_match.decide(probe, current, anchor)
    log_score(session.session_id, pensioner.id, decision.score, decision.anchor_score,
              decision.band.value, template.model_version)

    if decision.band is face_match.MatchBand.REJECT:
        raise _Reject(decision.reason_code or "FACE_MISMATCH",
                      "Face does not match the registered pensioner")

    # A frozen pension is only released by an officer, even on a strong match.
    band = decision.band
    reason_code, reason = decision.reason_code, decision.reason
    if band is face_match.MatchBand.APPROVE and pensioner.status is PensionerStatus.FROZEN:
        band = face_match.MatchBand.REVIEW
        reason_code, reason = "FROZEN_REVIEW", "Pension is frozen; an officer must confirm this certificate"

    now = utcnow()
    status = CertificateStatus.ISSUED if band is face_match.MatchBand.APPROVE else CertificateStatus.UNDER_REVIEW
    cert = LifeCertificate(
        pensioner_id=pensioner.id, year=now.year, status=status,
        match_score=round(decision.score, 4), anchor_score=round(decision.anchor_score, 4),
        bpm=payload.bpm, snr=payload.snr, challenge_type=session.challenge_type,
        challenge_passed=payload.challenge_passed, key_type=device.key_type,
        session_id=session.session_id, reason_code=reason_code, reason=reason,
    )
    db.add(cert)
    db.flush()

    if status is CertificateStatus.ISSUED:
        updated = face_match.blend_template(current, anchor, probe, decision)
        if updated is not None:
            template.current_template = face_match.encrypt_vector(updated)
            template.update_count += 1
            template.updated_at = now
            db.add(template)
        pensioner.failed_attempts = 0
        db.add(pensioner)
        event_type, ws_event = LedgerEvent.CERTIFICATE_ISSUED, "CERTIFICATE_ISSUED"
    else:
        event_type, ws_event = LedgerEvent.CERTIFICATE_UNDER_REVIEW, "UNDER_REVIEW"

    sessions.finish(db, session, SessionStatus.COMPLETED, outcome=status.value,
                    reason_code=reason_code, reason=reason, certificate_id=cert.id,
                    bpm=payload.bpm, device_id=payload.device_id, commit=False)
    entry = ledger.append(db, event_type, certificate_record(cert), ref=f"certificate:{cert.id}")
    cert.ledger_hash = entry.entry_hash
    db.add(cert)
    db.commit()

    event = _base_event(ws_event, session, certificate_id=cert.id, year=cert.year,
                        match_score=cert.match_score, bpm=cert.bpm, snr=cert.snr,
                        challenge_type=cert.challenge_type, ledger_hash=cert.ledger_hash,
                        reason_code=reason_code, reason=reason)
    return VerificationResult(VerifyResponse(
        status="ACCESS_GRANTED" if status is CertificateStatus.ISSUED else "UNDER_REVIEW",
        session_id=session.session_id, reason=reason, reason_code=reason_code,
        purpose=session.purpose, outcome=status.value, certificate_id=cert.id,
    ), [(session.session_id, event)])


def certificate_record(cert: LifeCertificate) -> dict[str, Any]:
    """The certificate facts that are hashed into the ledger (no personal data)."""
    return {
        "certificate_id": cert.id, "pensioner_id": cert.pensioner_id, "year": cert.year,
        "status": cert.status.value, "match_score": cert.match_score,
        "session_id": cert.session_id, "created_at": cert.created_at.isoformat(),
    }
