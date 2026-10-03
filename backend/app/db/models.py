"""
Database tables (SQLModel on SQLite; swap DATABASE_URL for another engine later).

Privacy rules enforced by this schema:
- No face images are ever stored. Face templates are Fernet-encrypted bytes.
- No Aadhaar numbers. Only the bank account's last 4 digits.
- The audit ledger stores hashes only, never personal data.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel

from app.db.types import UTCDateTime, utcnow


def _ts(nullable: bool = False) -> Column:
    # A fresh Column per field: SQLAlchemy Column objects cannot be shared.
    return Column(UTCDateTime(), nullable=nullable)


# ── Enums ───────────────────────────────────────────────────────────────

class PensionerStatus(str, Enum):
    PENDING_ENROLLMENT = "PENDING_ENROLLMENT"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    REMOVED = "REMOVED"  # officer removed the record: biometric data and personal details erased


class CertificateStatus(str, Enum):
    ISSUED = "ISSUED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"


class SessionPurpose(str, Enum):
    AUTH = "AUTH"                          # original login demo flow
    ENROLLMENT = "ENROLLMENT"              # officer-assisted registration
    LIFE_CERTIFICATE = "LIFE_CERTIFICATE"  # annual proof of life


class SessionStatus(str, Enum):
    PENDING = "PENDING"        # QR shown, waiting for the phone
    PROCESSING = "PROCESSING"  # payload received; consumed (cannot be reused)
    VERIFIED = "VERIFIED"      # legacy value, kept for API compatibility
    GRANTED = "GRANTED"        # AUTH flow succeeded
    COMPLETED = "COMPLETED"    # ENROLLMENT / LIFE_CERTIFICATE decided (see outcome)
    REJECTED = "REJECTED"      # verification failed (see reason)
    EXPIRED = "EXPIRED"


class KeyType(str, Enum):
    STRONGBOX = "STRONGBOX"
    TEE = "TEE"
    SOFTWARE = "SOFTWARE"
    UNKNOWN = "UNKNOWN"


# ── Tables ──────────────────────────────────────────────────────────────

class Officer(SQLModel, table=True):
    __tablename__ = "officers"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    full_name: str
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class Pensioner(SQLModel, table=True):
    __tablename__ = "pensioners"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    ppo_number: str = Field(index=True, unique=True)  # Pension Payment Order number
    service_number: str
    bank_last4: str = Field(max_length=4)
    monthly_pension_amount: int = 0  # rupees; dummy data for the treasury view
    status: PensionerStatus = PensionerStatus.PENDING_ENROLLMENT
    status_reason: Optional[str] = None
    failed_attempts: int = 0
    registered_by: Optional[int] = Field(default=None, foreign_key="officers.id")
    did: Optional[str] = None  # did:key of the bound device (Milestone 6)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class BiometricTemplate(SQLModel, table=True):
    __tablename__ = "biometric_templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    pensioner_id: int = Field(foreign_key="pensioners.id", unique=True, index=True)
    # Fernet-encrypted float32 vectors. anchor_template is written once at
    # registration approval and never overwritten.
    anchor_template: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    current_template: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    embedding_dim: int
    model_version: str
    update_count: int = 0
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: Optional[int] = Field(default=None, primary_key=True)
    pensioner_id: int = Field(foreign_key="pensioners.id", index=True)
    public_key_pem: str
    key_type: KeyType = KeyType.UNKNOWN
    device_id: Optional[str] = None  # Android ID reported by the app (informational)
    active: bool = False  # becomes True when the officer approves the registration
    registered_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class LifeCertificate(SQLModel, table=True):
    __tablename__ = "life_certificates"

    id: Optional[int] = Field(default=None, primary_key=True)
    pensioner_id: int = Field(foreign_key="pensioners.id", index=True)
    year: int = Field(index=True)
    status: CertificateStatus
    match_score: Optional[float] = None   # cosine vs current_template
    anchor_score: Optional[float] = None  # cosine vs anchor_template
    bpm: Optional[float] = None
    snr: Optional[float] = None
    challenge_type: Optional[str] = None
    challenge_passed: Optional[bool] = None
    key_type: Optional[KeyType] = None
    session_id: str = Field(index=True)
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    reviewed_by: Optional[int] = Field(default=None, foreign_key="officers.id")
    reviewed_at: Optional[datetime] = Field(default=None, sa_column=_ts(nullable=True))
    credential_hash: Optional[str] = None  # SHA-256 of the signed verifiable credential
    credential_json: Optional[str] = None  # the signed credential (no personal data: subject is a DID)
    ledger_hash: Optional[str] = None      # ledger entry that recorded the issuance
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    session_id: str = Field(primary_key=True)
    purpose: SessionPurpose = SessionPurpose.AUTH
    pensioner_id: Optional[int] = Field(default=None, foreign_key="pensioners.id", index=True)
    nonce: str
    challenge_id: Optional[str] = None
    challenge_type: Optional[str] = None
    status: SessionStatus = SessionStatus.PENDING
    outcome: Optional[str] = None       # e.g. ISSUED / UNDER_REVIEW / CAPTURED / GRANTED
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    certificate_id: Optional[int] = None
    bpm: Optional[float] = None
    device_id: Optional[str] = None
    consent_at: Optional[datetime] = Field(default=None, sa_column=_ts(nullable=True))
    created_by_officer: Optional[int] = Field(default=None, foreign_key="officers.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    expires_at: datetime = Field(sa_column=_ts())
    used_at: Optional[datetime] = Field(default=None, sa_column=_ts(nullable=True))
    completed_at: Optional[datetime] = Field(default=None, sa_column=_ts(nullable=True))


class ScanDiagnostic(SQLModel, table=True):
    """One row per signed scan result (pass or fail) with the app's measurements.
    Used to tell a slow camera from poor lighting or tight thresholds."""

    __tablename__ = "scan_diagnostics"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    session_id: str = Field(index=True)
    purpose: Optional[str] = None
    pensioner_id: Optional[int] = Field(default=None, index=True)
    outcome: Optional[str] = None          # GRANTED / ISSUED / UNDER_REVIEW / CAPTURED / REJECTED
    reason_code: Optional[str] = None
    liveness_passed: Optional[bool] = None
    bpm: Optional[float] = None
    snr_db: Optional[float] = None
    app_version: Optional[str] = None
    key_type: Optional[str] = None
    device_model: Optional[str] = Field(default=None, index=True)
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
    last_gate: Optional[str] = None
    ae_locked: Optional[bool] = None
    fps_range: Optional[str] = None
    label: Optional[str] = None            # set by calibrate_thresholds.py (genuine / photo / ...)


class LedgerEntry(SQLModel, table=True):
    """Append-only, hash-chained audit log. Holds hashes only — never personal data."""

    __tablename__ = "audit_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    event_type: str = Field(index=True)
    ref: Optional[str] = None  # opaque internal reference, e.g. "certificate:12"
    data_hash: str             # SHA-256 of the canonical event data
    prev_hash: str             # entry_hash of the previous entry ("0"*64 for the first)
    entry_hash: str = Field(unique=True)
