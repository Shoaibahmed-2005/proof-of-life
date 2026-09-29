"""Pydantic schemas for session management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.db.models import SessionPurpose, SessionStatus

__all__ = ["SessionCreate", "SessionResponse", "SessionStatus", "SessionStatusResponse"]


class SessionCreate(BaseModel):
    """
    Request body for creating a session. An empty body keeps the original
    AUTH behaviour.

    - ENROLLMENT: officer token required; `pensioner_id` of a PENDING_ENROLLMENT pensioner.
    - LIFE_CERTIFICATE: `ppo_number` (what the pensioner types) or `pensioner_id`,
      and `consent: true` (the portal shows the consent notice first).
    """
    purpose: SessionPurpose = SessionPurpose.AUTH
    pensioner_id: Optional[int] = None
    ppo_number: Optional[str] = None
    consent: Optional[bool] = None


class ChallengeInfo(BaseModel):
    id: str
    type: str
    timeout_s: int


class SessionResponse(BaseModel):
    """Returned when a session is created or queried."""
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    created_at: datetime
    expires_at: datetime
    status: SessionStatus
    purpose: SessionPurpose = SessionPurpose.AUTH
    pensioner_id: Optional[int] = None
    challenge: Optional[ChallengeInfo] = None
    # Result fields (filled once the session is decided)
    outcome: Optional[str] = None
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    certificate_id: Optional[int] = None
    # Only on creation: what the portal renders as the QR code
    qr_payload: Optional[dict[str, Any]] = None


class SessionStatusResponse(BaseModel):
    """Lightweight response for status-only queries."""
    session_id: str
    status: SessionStatus
