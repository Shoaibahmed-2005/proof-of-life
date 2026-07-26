"""
WebSocket Connection Manager.

Manages active WebSocket connections keyed by session ID, enabling
targeted message delivery (e.g., pushing ACCESS_GRANTED to a specific
frontend session).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe manager for active WebSocket connections."""

    def __init__(self) -> None:
        # session_id -> WebSocket
        self._active_connections: dict[str, WebSocket] = {}

    @property
    def active_sessions(self) -> list[str]:
        """Return a list of currently connected session IDs."""
        return list(self._active_connections.keys())

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a WebSocket connection for a session."""
        await websocket.accept()
        self._active_connections[session_id] = websocket
        logger.info("WebSocket connected: session_id=%s", session_id)

    def disconnect(self, session_id: str) -> None:
        """Remove a WebSocket connection for a session."""
        removed = self._active_connections.pop(session_id, None)
        if removed:
            logger.info("WebSocket disconnected: session_id=%s", session_id)

    def is_connected(self, session_id: str) -> bool:
        """Check if a session has an active WebSocket connection."""
        return session_id in self._active_connections

    async def send_to_session(self, session_id: str, data: dict[str, Any]) -> bool:
        """
        Send a JSON message to a specific session's WebSocket.

        Returns True if the message was sent, False if the session
        is not connected.
        """
        websocket = self._active_connections.get(session_id)
        if websocket is None:
            logger.warning(
                "Cannot send to session_id=%s: not connected", session_id
            )
            return False

        try:
            await websocket.send_json(data)
            logger.info(
                "Sent message to session_id=%s: event=%s",
                session_id,
                data.get("event", "unknown"),
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send message to session_id=%s", session_id
            )
            self.disconnect(session_id)
            return False

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        disconnected: list[str] = []
        for session_id, websocket in self._active_connections.items():
            try:
                await websocket.send_json(data)
            except Exception:
                logger.exception(
                    "Broadcast failed for session_id=%s", session_id
                )
                disconnected.append(session_id)

        for sid in disconnected:
            self.disconnect(sid)


# Singleton instance shared across the application
manager = ConnectionManager()
