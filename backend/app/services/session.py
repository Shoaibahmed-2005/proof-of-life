"""
Session service (database-backed).

A session is created when the portal needs a QR code. It carries a purpose
(AUTH / ENROLLMENT / LIFE_CERTIFICATE), a single-use nonce and — for the new
purposes — a random liveness challenge chosen here, so the phone cannot
predict it. The QR payload also carries the backend base URL, so the app never
needs a hard-coded address.

Lifecycle:  PENDING ─► PROCESSING ─► GRANTED | COMPLETED | REJECTED
               └──────────────► EXPIRED (timeout / manual)

`claim()` moves PENDING → PROCESSING atomically, so a session (and its nonce)
can be used by exactly one verification request.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import update
from sqlmodel import Session, select

from app.core.config import settings
from app.db.database import get_engine
from app.db.models import AuthSession, SessionPurpose, SessionStatus
from app.db.types import utcnow

logger = logging.getLogger(__name__)

QR_PAYLOAD_VERSION = 1
CHALLENGE_TYPES = ("BLINK_TWICE", "TURN_LEFT", "TURN_RIGHT")
TERMINAL_STATUSES = {SessionStatus.GRANTED, SessionStatus.COMPLETED,
                     SessionStatus.REJECTED, SessionStatus.EXPIRED}


# ── Base URL for the QR code ────────────────────────────────────────────

def _lan_ip() -> str | None:
    """This machine's LAN IP (no packets are sent; UDP connect only picks a route)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def resolve_base_url(request_base_url: str) -> str:
    """
    PUBLIC_BASE_URL if configured; otherwise the URL the portal used to reach
    us, with localhost swapped for the LAN IP so a phone on the same Wi-Fi can
    connect. (The app falls back to localhost for `adb reverse` setups.)
    """
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")
    parts = urlsplit(request_base_url)
    host, port = parts.hostname or "localhost", parts.port
    if host in ("localhost", "127.0.0.1", "::1"):
        host = _lan_ip() or host
    netloc = f"{host}:{port}" if port else host
    return f"{parts.scheme or 'http'}://{netloc}"


def build_qr_payload(session: AuthSession, base_url: str) -> dict:
    payload = {
        "v": QR_PAYLOAD_VERSION,
        "base_url": base_url,
        "session_id": session.session_id,
        "purpose": session.purpose.value,
        "nonce": session.nonce,
    }
    if session.challenge_id:
        payload["challenge"] = {
            "id": session.challenge_id,
            "type": session.challenge_type,
            "timeout_s": settings.CHALLENGE_TIMEOUT_SECONDS,
        }
    return payload


# ── CRUD ────────────────────────────────────────────────────────────────

def create(db: Session, purpose: SessionPurpose = SessionPurpose.AUTH,
           pensioner_id: int | None = None, officer_id: int | None = None) -> AuthSession:
    now = utcnow()
    session = AuthSession(
        session_id=secrets.token_urlsafe(32),
        purpose=purpose,
        pensioner_id=pensioner_id,
        nonce=secrets.token_urlsafe(16),
        created_by_officer=officer_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.SESSION_EXPIRY_SECONDS),
    )
    if purpose is not SessionPurpose.AUTH:
        session.challenge_id = secrets.token_urlsafe(8)
        session.challenge_type = secrets.choice(CHALLENGE_TYPES)
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("Session created: %s purpose=%s", session.session_id, purpose.value)
    return session


def get(db: Session, session_id: str) -> AuthSession | None:
    """Returns the session (auto-marking it EXPIRED if its time is up), or None."""
    session = db.get(AuthSession, session_id)
    if session is None:
        return None
    if session.status in (SessionStatus.PENDING, SessionStatus.PROCESSING) and utcnow() > session.expires_at:
        if session.status is SessionStatus.PENDING:
            session.status = SessionStatus.EXPIRED
            db.add(session)
            db.commit()
            db.refresh(session)
    return session


def is_expired(session: AuthSession) -> bool:
    return session.status is SessionStatus.EXPIRED or utcnow() > session.expires_at


def claim(db: Session, session_id: str) -> bool:
    """Atomically PENDING → PROCESSING. False if already used, expired or unknown."""
    now = utcnow()
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.session_id == session_id)
        .where(AuthSession.status == SessionStatus.PENDING)
        .values(status=SessionStatus.PROCESSING, used_at=now)
    )
    db.commit()
    return result.rowcount == 1


def finish(db: Session, session: AuthSession, status: SessionStatus, *,
           outcome: str | None = None, reason_code: str | None = None,
           reason: str | None = None, certificate_id: int | None = None,
           bpm: float | None = None, device_id: str | None = None,
           commit: bool = True) -> AuthSession:
    session.status = status
    session.outcome = outcome
    session.reason_code = reason_code
    session.reason = reason
    session.completed_at = utcnow()
    if certificate_id is not None:
        session.certificate_id = certificate_id
    if bpm is not None:
        session.bpm = bpm
    if device_id is not None:
        session.device_id = device_id
    db.add(session)
    if commit:
        db.commit()
        db.refresh(session)
    logger.info("Session %s → %s (%s)", session.session_id, status.value, reason_code or outcome or "")
    return session


def expire(db: Session, session_id: str) -> bool:
    session = db.get(AuthSession, session_id)
    if session is None:
        return False
    if session.status not in TERMINAL_STATUSES:
        session.status = SessionStatus.EXPIRED
        db.add(session)
        db.commit()
    return True


def expire_stale(db: Session) -> int:
    """Marks timed-out PENDING sessions as EXPIRED. Sessions are kept for audit."""
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.status == SessionStatus.PENDING)
        .where(AuthSession.expires_at < utcnow())
        .values(status=SessionStatus.EXPIRED)
    )
    db.commit()
    return result.rowcount or 0


def find_pending_for_pensioner(db: Session, pensioner_id: int, purpose: SessionPurpose) -> list[AuthSession]:
    stmt = (select(AuthSession)
            .where(AuthSession.pensioner_id == pensioner_id)
            .where(AuthSession.purpose == purpose)
            .where(AuthSession.status == SessionStatus.PENDING))
    return list(db.exec(stmt).all())


# ── Background maintenance ──────────────────────────────────────────────

async def maintenance_loop(interval_seconds: int = 60) -> None:
    """Expires stale sessions and applies the certificate-deadline freeze rule."""
    from app.services import pensioners  # local import avoids a cycle

    logger.info("Maintenance loop started (interval=%ds)", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                with Session(get_engine()) as db:
                    n = expire_stale(db)
                    if n:
                        logger.info("Expired %d stale sessions", n)
                    pensioners.apply_deadline_freeze(db)
            except Exception:
                logger.exception("Maintenance pass failed")
    except asyncio.CancelledError:
        logger.info("Maintenance loop stopped")
