"""
IOB Backend — Application entrypoint.

Internet of Bodies biometric authentication backend.
Manages WebSocket connections, session lifecycle, and cryptographic
verification of Titan M2-signed biometric payloads.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import api_router
from app.core.config import settings
from app.services.session import session_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # ── Startup ─────────────────────────────────────────────────────────
    logger.info("Starting %s...", settings.PROJECT_NAME)
    session_manager.start_background_cleanup(interval_seconds=60)
    logger.info("Session cleanup task started (60s interval)")
    yield
    # ── Shutdown ────────────────────────────────────────────────────────
    session_manager.stop_background_cleanup()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Biometric authentication backend for the IOB system. "
                "Manages sessions, WebSocket connections, and Titan M2 "
                "cryptographic signature verification.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Configure CORS middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include core routing
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["root"])
def read_root():
    """Root endpoint — API overview."""
    return {
        "project": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "api": settings.API_V1_STR,
        "endpoints": {
            "sessions": f"{settings.API_V1_STR}/sessions",
            "verify": f"{settings.API_V1_STR}/auth/verify",
            "websocket": f"{settings.API_V1_STR}/ws/{{session_id}}",
            "health": f"{settings.API_V1_STR}/health",
        },
    }
