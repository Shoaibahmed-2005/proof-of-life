"""
Session management router.

Provides CRUD endpoints for authentication sessions. The React frontend
calls POST /sessions to create a new session (rendered as a QR code),
and can query or expire sessions as needed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.session import SessionCreate, SessionResponse, SessionStatusResponse
from app.services.session import session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new authentication session",
)
async def create_session(_body: SessionCreate | None = None) -> SessionResponse:
    """
    Generate a new session with a cryptographically random ID.

    The frontend will render this session ID as a QR code for the
    Pixel 7 to scan.
    """
    session = session_manager.create_session()
    logger.info("New session created: %s", session.session_id)

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        status=session.status.value,
    )


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get session status",
)
async def get_session(session_id: str) -> SessionResponse:
    """
    Retrieve the current status of a session.

    Useful as a polling fallback when WebSockets are unavailable.
    """
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        status=session.status.value,
    )


@router.delete(
    "/{session_id}",
    response_model=SessionStatusResponse,
    summary="Expire a session",
)
async def expire_session(session_id: str) -> SessionStatusResponse:
    """Manually expire an active session."""
    success = session_manager.expire_session(session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    return SessionStatusResponse(
        session_id=session_id,
        status="EXPIRED",
    )
