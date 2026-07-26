"""
WebSocket router.

Provides a persistent real-time connection between the React frontend
and the backend. The frontend connects with its session ID and listens
for events like ACCESS_GRANTED.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.connection_manager import manager
from app.services.session import session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time frontend communication.

    Flow:
    1. Frontend connects with a session_id obtained from POST /sessions.
    2. Server validates the session exists and is not expired.
    3. Connection is kept alive; server pushes events (ACCESS_GRANTED, etc.).
    4. On disconnect, the connection is cleaned up.
    """
    # Validate that the session exists
    session = session_manager.get_session(session_id)
    if session is None:
        await websocket.close(code=4004, reason="Session not found")
        logger.warning(
            "WebSocket rejected: session_id=%s not found", session_id
        )
        return

    if session.is_expired:
        await websocket.close(code=4001, reason="Session expired")
        logger.warning(
            "WebSocket rejected: session_id=%s expired", session_id
        )
        return

    # Accept the connection and register it
    await manager.connect(websocket, session_id)

    try:
        # Send an initial confirmation event
        await websocket.send_json({
            "event": "CONNECTED",
            "session_id": session_id,
            "message": "WebSocket connection established. Waiting for authentication.",
        })

        # Keep the connection alive and listen for client messages
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"event": "pong"})
            elif msg_type == "status":
                # Allow client to poll session status over WS
                current = session_manager.get_session(session_id)
                status = current.status.value if current else "UNKNOWN"
                await websocket.send_json({
                    "event": "STATUS",
                    "session_id": session_id,
                    "status": status,
                })
            else:
                await websocket.send_json({
                    "event": "ERROR",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: session_id=%s", session_id)
    except Exception:
        logger.exception(
            "WebSocket error for session_id=%s", session_id
        )
    finally:
        manager.disconnect(session_id)
