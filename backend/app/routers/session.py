"""
Session management router.

The portal calls POST /sessions to get a session and renders `qr_payload` as
the QR code. The phone reads the backend base URL, purpose, nonce and challenge
from it. An empty body keeps the original AUTH (login demo) behaviour.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.core.deps import DbSession, MaybeOfficer
from app.db.models import AuthSession, Pensioner, PensionerStatus, SessionPurpose
from app.schemas.session import ChallengeInfo, SessionCreate, SessionResponse, SessionStatusResponse
from app.services import pensioners as pensioner_service
from app.services import session as sessions
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def to_response(session: AuthSession, qr_payload: dict | None = None) -> SessionResponse:
    challenge = None
    if session.challenge_id:
        challenge = ChallengeInfo(id=session.challenge_id, type=session.challenge_type,
                                  timeout_s=settings.CHALLENGE_TIMEOUT_SECONDS)
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        status=session.status,
        purpose=session.purpose,
        pensioner_id=session.pensioner_id,
        challenge=challenge,
        outcome=session.outcome,
        reason_code=session.reason_code,
        reason=session.reason,
        certificate_id=session.certificate_id,
        qr_payload=qr_payload,
    )


def _resolve_pensioner(db, body: SessionCreate) -> Pensioner:
    pensioner = None
    if body.pensioner_id is not None:
        pensioner = db.get(Pensioner, body.pensioner_id)
    elif body.ppo_number:
        pensioner = pensioner_service.get_by_ppo(db, body.ppo_number)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter the pension ID (PPO number)")
    if pensioner is None or pensioner.status is PensionerStatus.REMOVED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pensioner found with that pension ID")
    return pensioner


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new session (AUTH, ENROLLMENT or LIFE_CERTIFICATE)",
)
async def create_session(request: Request, db: DbSession, officer: MaybeOfficer,
                         body: SessionCreate | None = None) -> SessionResponse:
    body = body or SessionCreate()
    pensioner_id = None

    if body.purpose is SessionPurpose.ENROLLMENT:
        if officer is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Officer login required to register a pensioner")
        pensioner = _resolve_pensioner(db, body)
        if pensioner.status is not PensionerStatus.PENDING_ENROLLMENT:
            raise HTTPException(status.HTTP_409_CONFLICT, "This pensioner is already registered")
        pensioner_id = pensioner.id

    elif body.purpose is SessionPurpose.LIFE_CERTIFICATE:
        if body.consent is not True:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Please read and accept the consent notice before scanning")
        pensioner = _resolve_pensioner(db, body)
        if pensioner.status is PensionerStatus.PENDING_ENROLLMENT:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This pensioner has not completed registration yet")
        pensioner_id = pensioner.id

    # Only one live QR per pensioner and purpose: older ones stop working.
    if pensioner_id is not None:
        for old in sessions.find_pending_for_pensioner(db, pensioner_id, body.purpose):
            sessions.expire(db, old.session_id)

    session = sessions.create(db, body.purpose, pensioner_id,
                              officer.id if officer else None)
    base_url = sessions.resolve_base_url(str(request.base_url))
    return to_response(session, sessions.build_qr_payload(session, base_url))


@router.get("/{session_id}", response_model=SessionResponse, summary="Get session status")
async def get_session(session_id: str, db: DbSession) -> SessionResponse:
    """Polling fallback when WebSockets are unavailable; includes the result once decided."""
    session = sessions.get(db, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Session '{session_id}' not found")
    return to_response(session)


@router.delete("/{session_id}", response_model=SessionStatusResponse, summary="Expire a session")
async def expire_session(session_id: str, db: DbSession) -> SessionStatusResponse:
    """Manually expire an active session."""
    if not sessions.expire(db, session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Session '{session_id}' not found")
    session = sessions.get(db, session_id)
    return SessionStatusResponse(session_id=session_id, status=session.status)
