"""
WebSocket router.

- /ws/{session_id}             portal page showing the QR code: receives the
                               session's live events (MEASURING, CHALLENGE_ISSUED,
                               CERTIFICATE_ISSUED, UNDER_REVIEW, REJECTED, ...).
- /ws/events?token=<officer>   officer dashboards: every event, system-wide.
- /ws/telemetry/{session_id}?nonce=<nonce>
                               the phone streams scan progress; relayed to the
                               portal as MEASURING / CHALLENGE_* events.
- /ws/telemetry                legacy phone telemetry (log + ack only).
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.core.security import decode_officer_token
from app.db.database import get_engine
from app.db.models import Officer, SessionStatus
from app.services import session as sessions
from app.services.connection_manager import EVENTS_CHANNEL, manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Phone message "type" → portal event name
TELEMETRY_EVENTS = {
    "scan_started": "SCAN_STARTED",
    "measuring": "MEASURING",
    "stable_reading": "STABLE_READING",
    "challenge_issued": "CHALLENGE_ISSUED",
    "challenge_passed": "CHALLENGE_PASSED",
    "challenge_failed": "CHALLENGE_FAILED",
    "face_lost": "FACE_LOST",
    "multiple_faces": "MULTIPLE_FACES",
}
NUMERIC_FIELDS = ("bpm", "snr", "progress")
TEXT_FIELDS = ("challenge_type", "message")
MEASURING_MIN_INTERVAL_S = 0.5


def _clean_telemetry(data: dict) -> dict:
    """Whitelist and sanitise the fields relayed from the phone."""
    out = {}
    for key in NUMERIC_FIELDS:
        v = data.get(key)
        if isinstance(v, (int, float)) and math.isfinite(v):
            out[key] = round(float(v), 2)
    if isinstance(data.get("stable"), bool):
        out["stable"] = data["stable"]
    for key in TEXT_FIELDS:
        v = data.get(key)
        if isinstance(v, str):
            out[key] = v[:120]
    return out


@router.websocket("/ws/telemetry")
async def telemetry_endpoint(websocket: WebSocket) -> None:
    """Legacy phone telemetry (not tied to a session): log and acknowledge."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                telemetry = json.loads(data)
            except json.JSONDecodeError as exc:
                logger.warning("[Telemetry] Invalid JSON received: %s", exc)
                continue

            bpm = telemetry.get("bpm", 0.0)
            snr = telemetry.get("snr", 0.0)
            liveness_status = telemetry.get("liveness_status", 1)
            status_label = {0: "SPOOF", 1: "ANALYZING", 2: "HUMAN"}.get(liveness_status, "UNKNOWN")
            logger.info("[Telemetry] BPM: %.1f | SNR: %.2f | Liveness: %s (%s)",
                        bpm, snr, status_label, liveness_status)

            await websocket.send_text(json.dumps({
                "ack": True,
                "server_ts": datetime.now(timezone.utc).isoformat(),
            }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[Telemetry] WebSocket exception: %s", e)


@router.websocket("/ws/telemetry/{session_id}")
async def session_telemetry_endpoint(websocket: WebSocket, session_id: str, nonce: str = "") -> None:
    """Phone → portal live progress for one session. The QR nonce authenticates the phone."""
    with Session(get_engine()) as db:
        session = sessions.get(db, session_id)
        valid = (session is not None and session.status is SessionStatus.PENDING
                 and nonce == session.nonce)
    if not valid:
        await websocket.close(code=4003, reason="Unknown session or bad nonce")
        return

    await websocket.accept()
    last_measuring = 0.0
    try:
        while True:
            try:
                data = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                continue
            event_name = TELEMETRY_EVENTS.get(str(data.get("type", "")).lower())
            relay = event_name is not None
            if event_name == "MEASURING":
                now = time.monotonic()
                relay = now - last_measuring >= MEASURING_MIN_INTERVAL_S  # at most 2/s to the portal
                if relay:
                    last_measuring = now
            if relay:
                await manager.send_to_session(session_id, {
                    "event": event_name, "session_id": session_id, **_clean_telemetry(data),
                })
            # Always acknowledge, even when a message is throttled or unknown.
            await websocket.send_text(json.dumps({"ack": True, "relayed": relay}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("[Telemetry] error for session_id=%s", session_id)


@router.websocket("/ws/events")
async def events_endpoint(websocket: WebSocket, token: str = "") -> None:
    """System-wide events for logged-in officers (review queue, registrations, status)."""
    officer_id = decode_officer_token(token) if token else None
    with Session(get_engine()) as db:
        officer = db.get(Officer, officer_id) if officer_id is not None else None
    if officer is None:
        await websocket.close(code=4003, reason="Officer login required")
        return

    await manager.connect(websocket, EVENTS_CHANNEL)
    try:
        await websocket.send_json({"event": "CONNECTED", "channel": "events"})
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Events WebSocket error")
    finally:
        manager.disconnect(EVENTS_CHANNEL, websocket)


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for the portal page that shows the session's QR code.

    1. Portal connects with a session_id obtained from POST /sessions.
    2. Server validates the session exists and has not expired.
    3. Server pushes events until the portal disconnects.
    """
    with Session(get_engine()) as db:
        session = sessions.get(db, session_id)
        if session is None:
            await websocket.close(code=4004, reason="Session not found")
            logger.warning("WebSocket rejected: session_id=%s not found", session_id)
            return
        if session.status is SessionStatus.EXPIRED:
            await websocket.close(code=4001, reason="Session expired")
            logger.warning("WebSocket rejected: session_id=%s expired", session_id)
            return
        status, outcome = session.status.value, session.outcome

    await manager.connect(websocket, session_id)
    try:
        await websocket.send_json({
            "event": "CONNECTED",
            "session_id": session_id,
            "status": status,
            "outcome": outcome,
            "message": "WebSocket connection established. Waiting for the phone.",
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"event": "pong"})
            elif msg_type == "status":
                with Session(get_engine()) as db:
                    current = sessions.get(db, session_id)
                    await websocket.send_json({
                        "event": "STATUS",
                        "session_id": session_id,
                        "status": current.status.value if current else "UNKNOWN",
                        "outcome": current.outcome if current else None,
                    })
            else:
                await websocket.send_json({
                    "event": "ERROR",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: session_id=%s", session_id)
    except Exception:
        logger.exception("WebSocket error for session_id=%s", session_id)
    finally:
        manager.disconnect(session_id, websocket)
