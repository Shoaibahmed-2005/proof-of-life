"""
WebSocket Connection Manager.

Channels:
- one per session_id: the portal page that shows the QR code listens here
  (ACCESS_GRANTED, MEASURING, CHALLENGE_ISSUED, CERTIFICATE_ISSUED, ...).
- EVENTS_CHANNEL: officer dashboards listen here for system-wide events
  (new review items, registrations captured, status changes).

Several sockets may listen on the same channel (e.g. a page reopened in a new tab).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "__events__"


class ConnectionManager:
    """Manager for active WebSocket connections, grouped by channel."""

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}

    @property
    def active_sessions(self) -> list[str]:
        """Channels (session IDs) with at least one listener."""
        return [c for c, s in self._channels.items() if s and c != EVENTS_CHANNEL]

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept and register a WebSocket connection on a channel."""
        await websocket.accept()
        self._channels.setdefault(channel, set()).add(websocket)
        logger.info("WebSocket connected: channel=%s", channel)

    def disconnect(self, channel: str, websocket: WebSocket | None = None) -> None:
        """Remove one socket (or every socket if none given) from a channel."""
        sockets = self._channels.get(channel)
        if not sockets:
            return
        if websocket is None:
            sockets.clear()
        else:
            sockets.discard(websocket)
        if not sockets:
            self._channels.pop(channel, None)
        logger.info("WebSocket disconnected: channel=%s", channel)

    def is_connected(self, channel: str) -> bool:
        return bool(self._channels.get(channel))

    async def send_to_session(self, channel: str, data: dict[str, Any]) -> bool:
        """
        Send a JSON message to every socket on a channel.
        Returns True if at least one socket received it.
        """
        sockets = list(self._channels.get(channel, ()))
        if not sockets:
            logger.info("No listener for channel=%s (event=%s)", channel, data.get("event"))
            return False
        delivered = False
        for ws in sockets:
            try:
                await ws.send_json(data)
                delivered = True
            except Exception:
                logger.warning("Dropping dead socket on channel=%s", channel)
                self.disconnect(channel, ws)
        if delivered:
            logger.info("Sent event=%s to channel=%s", data.get("event", "unknown"), channel)
        return delivered

    async def publish(self, session_id: str | None, data: dict[str, Any]) -> None:
        """Send to the session's channel (if any) and to the officer events channel."""
        if session_id:
            await self.send_to_session(session_id, data)
        await self.send_to_session(EVENTS_CHANNEL, data)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        for channel in list(self._channels):
            await self.send_to_session(channel, data)


# Singleton instance shared across the application
manager = ConnectionManager()
