"""
Session Manager.

Manages the lifecycle of authentication sessions. Each session is created
when the React frontend requests a QR code, and transitions through
statuses as the Pixel 7 scans, verifies, and authenticates.

Lifecycle:  PENDING  →  VERIFIED  →  GRANTED
                ↘          ↘          ↘
                      EXPIRED (timeout or manual)
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """Status of an authentication session."""
    PENDING = "PENDING"      # Created, waiting for Pixel 7 to scan
    VERIFIED = "VERIFIED"    # Pixel 7 scanned, payload received
    GRANTED = "GRANTED"      # Signature + BPM valid, access granted
    EXPIRED = "EXPIRED"      # Timed out or manually expired


@dataclass
class SessionData:
    """Internal representation of a session."""
    session_id: str
    created_at: datetime
    status: SessionStatus = SessionStatus.PENDING
    bpm: int | None = None
    device_id: str | None = None
    granted_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def expires_at(self) -> datetime:
        """Calculate the expiry time based on creation time."""
        from datetime import timedelta
        return self.created_at + timedelta(seconds=settings.SESSION_EXPIRY_SECONDS)

    @property
    def is_expired(self) -> bool:
        """Check if the session has expired by time or explicit status."""
        if self.status == SessionStatus.EXPIRED:
            return True
        return datetime.now(timezone.utc) > self.expires_at


class SessionManager:
    """In-memory session store with background cleanup."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}
        self._cleanup_task: asyncio.Task | None = None

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_session(self) -> SessionData:
        """Create a new session with a cryptographically random ID."""
        session_id = secrets.token_urlsafe(32)
        session = SessionData(
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session_id] = session
        logger.info("Session created: %s", session_id)
        return session

    def get_session(self, session_id: str) -> SessionData | None:
        """
        Retrieve a session by ID.

        Returns None if the session does not exist or has expired.
        Automatically marks timed-out sessions as EXPIRED.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        # Auto-expire if the time window has passed
        if session.status not in (SessionStatus.EXPIRED, SessionStatus.GRANTED):
            if session.is_expired:
                session.status = SessionStatus.EXPIRED
                logger.info("Session auto-expired: %s", session_id)

        return session

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        bpm: int | None = None,
        device_id: str | None = None,
    ) -> SessionData | None:
        """Update a session's status and optional metadata."""
        session = self.get_session(session_id)
        if session is None:
            return None

        session.status = status
        if bpm is not None:
            session.bpm = bpm
        if device_id is not None:
            session.device_id = device_id
        if status == SessionStatus.GRANTED:
            session.granted_at = datetime.now(timezone.utc)

        logger.info("Session %s status → %s", session_id, status.value)
        return session

    def expire_session(self, session_id: str) -> bool:
        """Explicitly expire a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.status = SessionStatus.EXPIRED
        logger.info("Session manually expired: %s", session_id)
        return True

    # ── Background Cleanup ──────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove all expired sessions from the store. Returns count removed."""
        expired_ids = [
            sid for sid, s in self._sessions.items()
            if s.is_expired and s.status in (SessionStatus.EXPIRED, SessionStatus.GRANTED)
        ]
        for sid in expired_ids:
            del self._sessions[sid]

        if expired_ids:
            logger.info("Cleaned up %d expired sessions", len(expired_ids))
        return len(expired_ids)

    async def start_cleanup_loop(self, interval_seconds: int = 60) -> None:
        """Run periodic cleanup of expired sessions."""
        logger.info("Session cleanup loop started (interval=%ds)", interval_seconds)
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                self.cleanup_expired()
        except asyncio.CancelledError:
            logger.info("Session cleanup loop stopped")

    def start_background_cleanup(self, interval_seconds: int = 60) -> None:
        """Launch the cleanup loop as a background asyncio task."""
        self._cleanup_task = asyncio.create_task(
            self.start_cleanup_loop(interval_seconds)
        )

    def stop_background_cleanup(self) -> None:
        """Cancel the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Session cleanup task cancelled")

    # ── Debug / Introspection ───────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """Number of non-expired sessions."""
        return sum(1 for s in self._sessions.values() if not s.is_expired)

    @property
    def total_count(self) -> int:
        """Total sessions in the store (including expired)."""
        return len(self._sessions)


# Singleton instance shared across the application
session_manager = SessionManager()
