"""Schemas for pensioners, certificates, officers, enrollment and reviews."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import CertificateStatus, KeyType, PensionerStatus


# ── Officers ────────────────────────────────────────────────────────────

class OfficerLogin(BaseModel):
    username: str
    password: str


class OfficerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    officer: OfficerOut


# ── Pensioners ──────────────────────────────────────────────────────────

class PensionerCreate(BaseModel):
    """Details the officer enters after checking the pensioner's physical ID (dummy data only)."""
    name: str = Field(min_length=2, max_length=120)
    ppo_number: str = Field(min_length=4, max_length=40, description="Pension Payment Order number")
    service_number: str = Field(min_length=2, max_length=40)
    bank_last4: str = Field(description="Last 4 digits of the bank account")
    monthly_pension_amount: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("name", "ppo_number", "service_number")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("bank_last4")
    @classmethod
    def _four_digits(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 4 or not v.isdigit():
            raise ValueError("Enter exactly the last 4 digits of the bank account")
        return v


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pensioner_id: int
    year: int
    status: CertificateStatus
    match_score: Optional[float] = None
    anchor_score: Optional[float] = None
    bpm: Optional[float] = None
    snr: Optional[float] = None
    challenge_type: Optional[str] = None
    challenge_passed: Optional[bool] = None
    key_type: Optional[KeyType] = None
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    ledger_hash: Optional[str] = None
    credential_hash: Optional[str] = None
    created_at: datetime


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key_type: KeyType
    active: bool
    registered_at: datetime


class PensionerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    ppo_number: str
    service_number: str
    bank_last4: str
    monthly_pension_amount: int
    status: PensionerStatus
    status_reason: Optional[str] = None
    failed_attempts: int
    did: Optional[str] = None
    registered_by: Optional[int] = None
    created_at: datetime


class PensionerDetail(PensionerOut):
    has_template: bool = False
    template_model_version: Optional[str] = None
    template_updates: int = 0
    device: Optional[DeviceOut] = None
    certificate_this_year: Optional[CertificateStatus] = None
    certificates: list[CertificateOut] = []


class PensionerPublic(BaseModel):
    """What anyone who knows the PPO number may see (Check Status page)."""
    id: int
    name: str
    ppo_number: str
    status: PensionerStatus
    status_reason: Optional[str] = None
    certificate_this_year: Optional[CertificateStatus] = None
    certificates: list[CertificateOut] = []


# ── Enrollment ──────────────────────────────────────────────────────────

class EnrollComplete(BaseModel):
    pensioner_id: int


class EnrollCompleteResponse(BaseModel):
    pensioner: PensionerOut
    ledger_hash: str


# ── Reviews ─────────────────────────────────────────────────────────────

class ReviewItem(CertificateOut):
    pensioner_name: str
    ppo_number: str
    pensioner_status: PensionerStatus


class ReviewDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3, max_length=500)


class ReviewDecisionResponse(BaseModel):
    certificate: CertificateOut
    pensioner_status: PensionerStatus
