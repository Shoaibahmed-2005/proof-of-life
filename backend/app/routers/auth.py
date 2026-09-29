"""
Authentication & Verification router.

Receives the payload signed inside the phone's Titan M2 (StrongBox), runs the
verification pipeline (services/verification.py) and pushes the result to the
portal over WebSocket.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.deps import DbSession
from app.schemas.auth import VerifyRequest, VerifyResponse
from app.services.connection_manager import manager
from app.services.verification import InvalidPublicKey, verify

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a signed biometric payload",
)
async def verify_biometric(request: VerifyRequest, db: DbSession) -> VerifyResponse:
    """
    Main verification endpoint. See services/verification.py for the ordered
    fail-fast checks (signature → schema → session/nonce → device binding →
    freshness → liveness → challenge → face match → decision).
    """
    try:
        result = verify(db, request)
    except InvalidPublicKey as e:
        logger.warning("Invalid public key: %s", e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid public key: {e}")
    except Exception:
        logger.exception("Unexpected error during verification")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "Internal server error during verification")

    for session_id, event in result.events:
        await manager.publish(session_id, event)
    return result.response
