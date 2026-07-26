"""Pydantic schemas for session management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class SessionStatus(str, Enum):
    """Status of an authentication session (mirrors services.session.SessionStatus)."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    GRANTED = "GRANTED"
    EXPIRED = "EXPIRED"


class SessionCreate(BaseModel):
    """Request body for creating a new session. Empty — server generates everything."""
    pass


class SessionResponse(BaseModel):
    """Response returned when a session is created or queried."""
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    created_at: datetime
    expires_at: datetime
    status: SessionStatus


class SessionStatusResponse(BaseModel):
    """Lightweight response for status-only queries."""
    session_id: str
    status: SessionStatus
