"""Pydantic schemas for biometric authentication and verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import KeyType, SessionPurpose


class ScanDiagnostics(BaseModel):
    """Per-scan measurements from the app (Milestone 2 diagnostics). All optional."""
    scan_seconds: Optional[float] = None
    avg_fps: Optional[float] = None
    min_fps: Optional[float] = None
    frames: Optional[int] = None
    face_lost_count: Optional[int] = None
    best_snr_db: Optional[float] = None
    final_spread_bpm: Optional[float] = None
    mean_luma: Optional[float] = None
    skin_fraction: Optional[float] = None
    estimates: Optional[int] = None
    min_snr_db: Optional[float] = None
    gate_sec_window: Optional[float] = None
    gate_sec_stable: Optional[float] = None
    gate_sec_snr: Optional[float] = None
    gate_sec_face: Optional[float] = None
    last_gate: Optional[str] = Field(default=None, max_length=40)
    ae_locked: Optional[bool] = None
    fps_range: Optional[str] = Field(default=None, max_length=40)
    device_model: Optional[str] = Field(default=None, max_length=80)


class BiometricPayload(BaseModel):
    """
    The JSON the phone builds and signs inside Titan M2 (StrongBox).

    Legacy app (purpose omitted → AUTH):
        {session_id, bpm, timestamp, device_id, snr, variance}

    Current app (build-prompt §4.4), purpose ENROLLMENT or LIFE_CERTIFICATE:
        {session_id, purpose, nonce, timestamp, device_id,
         bpm, snr, liveness_passed, challenge_id, challenge_passed,
         face_embedding | reference_template, frames_used, app_version,
         model_version, key_security_level, consent}
    """
    session_id: str
    purpose: SessionPurpose = SessionPurpose.AUTH
    nonce: Optional[str] = None
    timestamp: datetime
    device_id: str
    bpm: float = Field(..., ge=0, description="Heart rate in beats per minute")
    snr: Optional[float] = Field(default=None, description="rPPG signal-to-noise ratio (dB for current app)")
    variance: Optional[float] = Field(default=None, description="Legacy: head micro-motion variance")
    liveness_passed: Optional[bool] = None
    challenge_id: Optional[str] = None
    challenge_passed: Optional[bool] = None
    face_embedding: Optional[list[float]] = Field(default=None, description="LIFE_CERTIFICATE probe embedding")
    reference_template: Optional[list[float]] = Field(default=None, description="ENROLLMENT averaged template")
    frames_used: Optional[int] = Field(default=None, ge=0)
    app_version: Optional[str] = None
    model_version: Optional[str] = None
    key_security_level: Optional[KeyType] = None
    consent: Optional[bool] = None
    diagnostics: Optional[ScanDiagnostics] = None
    # The app stopped the scan itself: more than one face in view, or it could
    # not capture enough clear face frames for the embedding.
    abort_reason: Optional[Literal["MULTIPLE_FACES", "FACE_NOT_CAPTURED"]] = None

    @field_validator("timestamp")
    @classmethod
    def _assume_utc(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    @field_validator("key_security_level", mode="before")
    @classmethod
    def _normalise_key_level(cls, v):
        if v is None:
            return None
        v = str(v).strip().upper()
        return v if v in KeyType.__members__ else KeyType.UNKNOWN.value

    @model_validator(mode="after")
    def _required_for_purpose(self) -> "BiometricPayload":
        if self.purpose is SessionPurpose.AUTH:
            return self
        if self.abort_reason is not None:
            # The app stopped the scan: only what identifies the attempt is needed,
            # so the rejection still reaches the portal.
            required = ["nonce"]
        else:
            required = ["nonce", "snr", "liveness_passed", "challenge_id", "challenge_passed",
                        "frames_used", "app_version"]
            # No pulse or a failed challenge is rejected before the face is compared,
            # so the face data is only required for an attempt that passed both.
            if self.liveness_passed and self.challenge_passed:
                required.append("face_embedding" if self.purpose is SessionPurpose.LIFE_CERTIFICATE
                                else "reference_template")
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(f"Missing fields for {self.purpose.value}: {', '.join(missing)}")
        return self


class VerifyRequest(BaseModel):
    """
    Sent by the phone. `payload` is the Base64 of the exact JSON bytes that were
    signed; the signature is DER ECDSA-SHA256 (P-256) over those bytes.
    """
    payload: str = Field(..., description="Base64-encoded JSON of BiometricPayload")
    signature: str = Field(..., description="Base64-encoded ECDSA-SHA256 signature over the payload bytes")
    public_key: str = Field(..., description="Base64-encoded DER public key (SubjectPublicKeyInfo)")
    attestation_chain: Optional[list[str]] = Field(
        default=None,
        description="Optional base64-encoded DER certificates for Android Key Attestation",
    )


class VerifyResponse(BaseModel):
    """
    `status` keeps the legacy values for AUTH (ACCESS_GRANTED / ACCESS_DENIED).
    For ENROLLMENT / LIFE_CERTIFICATE, `outcome` carries the result:
    CAPTURED, ISSUED, UNDER_REVIEW or REJECTED.
    """
    status: str = Field(..., description="ACCESS_GRANTED or ACCESS_DENIED")
    session_id: str
    reason: Optional[str] = Field(default=None, description="Human-readable reason, if not approved")
    reason_code: Optional[str] = None
    purpose: Optional[SessionPurpose] = None
    outcome: Optional[str] = None
    certificate_id: Optional[int] = None
