"""
Authentication & Verification router.

Receives the cryptographically-signed biometric payload from the Pixel 7,
verifies the Titan M2 ECDSA signature, validates the BPM, and pushes
an ACCESS_GRANTED event to the React frontend over WebSocket.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.auth import BiometricPayload, VerifyRequest, VerifyResponse
from app.services.connection_manager import manager
from app.services.crypto import (
    SignatureVerificationError,
    InvalidPublicKeyError,
    verify_signature,
)
from app.services.liveness import validate_liveness, SpoofingDetectedError
from app.services.session import SessionStatus, session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a signed biometric payload",
)
async def verify_biometric(request: VerifyRequest) -> VerifyResponse:
    """
    Main verification endpoint.

    Receives the Pixel 7's signed payload and performs:
    1. ECDSA signature verification against the provided public key.
    2. Payload deserialization and schema validation.
    3. Session existence and status check (must be PENDING).
    4. BPM biological plausibility check (40–220 BPM).
    5. Timestamp freshness check (within session window).
    6. On success: updates session → GRANTED and pushes ACCESS_GRANTED via WS.
    """
    session_id = "unknown"

    try:
        # ── Step 1: Verify the cryptographic signature ──────────────────
        try:
            verify_signature(
                payload_b64=request.payload,
                signature_b64=request.signature,
                public_key_b64=request.public_key,
            )
        except InvalidPublicKeyError as e:
            logger.warning("Invalid public key: %s", e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid public key: {e}",
            )
        except SignatureVerificationError as e:
            logger.warning("Signature verification failed: %s", e)
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason="Cryptographic signature verification failed",
            )

        # ── Step 2: Decode and parse the payload ────────────────────────
        try:
            payload_bytes = base64.b64decode(request.payload)
            payload_dict = json.loads(payload_bytes)
            payload = BiometricPayload(**payload_dict)
            session_id = payload.session_id
        except Exception as e:
            logger.warning("Payload decode failed: %s", e)
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason=f"Invalid payload format: {e}",
            )

        # ── Step 3: Validate session exists and is PENDING ──────────────
        session = session_manager.get_session(session_id)
        if session is None:
            logger.warning("Session not found: %s", session_id)
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason="Session not found or expired",
            )

        if session.status != SessionStatus.PENDING:
            logger.warning(
                "Session %s is in status %s, expected PENDING",
                session_id,
                session.status.value,
            )
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason=f"Session is already {session.status.value}",
            )

        if session.is_expired:
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason="Session has expired",
            )

        # ── Step 4: Validate Liveness & Anti-Spoofing Parameters ──────────
        try:
            validate_liveness(
                bpm=payload.bpm,
                snr=payload.snr,
                variance=payload.variance,
            )
        except SpoofingDetectedError as e:
            logger.warning("Liveness validation failed for session %s: %s", session_id, e)
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason=str(e),
            )

        # ── Step 5: Validate timestamp freshness ────────────────────────
        now = datetime.now(timezone.utc)
        payload_age = (now - payload.timestamp).total_seconds()
        if abs(payload_age) > settings.SESSION_EXPIRY_SECONDS:
            logger.warning(
                "Payload timestamp too old: %.1fs (max %ds)",
                payload_age,
                settings.SESSION_EXPIRY_SECONDS,
            )
            return VerifyResponse(
                status="ACCESS_DENIED",
                session_id=session_id,
                reason="Payload timestamp is too old",
            )

        # ── Step 6: All checks passed — grant access ────────────────────
        session_manager.update_status(
            session_id=session_id,
            status=SessionStatus.GRANTED,
            bpm=payload.bpm,
            device_id=payload.device_id,
        )

        # Push ACCESS_GRANTED to the React frontend via WebSocket
        ws_sent = await manager.send_to_session(session_id, {
            "event": "ACCESS_GRANTED",
            "session_id": session_id,
            "bpm": payload.bpm,
            "device_id": payload.device_id,
            "granted_at": now.isoformat(),
        })

        if ws_sent:
            logger.info(
                "ACCESS_GRANTED pushed via WebSocket for session %s",
                session_id,
            )
        else:
            logger.warning(
                "ACCESS_GRANTED: session %s has no active WebSocket (will be available via polling)",
                session_id,
            )

        return VerifyResponse(
            status="ACCESS_GRANTED",
            session_id=session_id,
            reason=None,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during verification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during verification",
        )
