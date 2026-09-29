"""
Jeevan Suraksha backend — application entrypoint.

Pension life-certificate system on the IoB liveness engine: sessions and QR
payloads, verification of Titan M2-signed biometric payloads, pensioner
records, the officer review queue, the audit ledger and WebSocket push.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import get_engine, init_db
from app.db.models import Officer
from app.routers import api_router
from app.services import pensioners
from app.services import session as sessions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def seed_demo_officer() -> None:
    """Creates the demo officer from .env if there are no officers yet."""
    with Session(get_engine()) as db:
        if db.exec(select(Officer)).first() is None:
            db.add(Officer(username=settings.DEMO_OFFICER_USERNAME,
                           full_name=settings.DEMO_OFFICER_NAME,
                           password_hash=hash_password(settings.DEMO_OFFICER_PASSWORD)))
            db.commit()
            logger.info("Seeded demo officer '%s'", settings.DEMO_OFFICER_USERNAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # ── Startup ─────────────────────────────────────────────────────────
    logger.info("Starting %s...", settings.PROJECT_NAME)
    if settings.SECRET_KEY == "secret-key-change-me-in-production":
        logger.warning(
            "[SECURITY] SECRET_KEY is set to the default development value. "
            "Set a strong random key in your .env file before deploying to production."
        )
    init_db()
    seed_demo_officer()
    with Session(get_engine()) as db:
        sessions.expire_stale(db)
        pensioners.apply_deadline_freeze(db)
    maintenance = asyncio.create_task(sessions.maintenance_loop(interval_seconds=60))
    logger.info("Database ready at %s", settings.database_url)
    yield
    # ── Shutdown ────────────────────────────────────────────────────────
    maintenance.cancel()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend for the Jeevan Suraksha pension life-certificate portal: sessions, "
                "Titan M2 signature verification, liveness and face-match decisions, "
                "officer review, and a hash-chained audit ledger.",
    version="2.0.0",
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
    v1 = settings.API_V1_STR
    return {
        "project": settings.PROJECT_NAME,
        "version": "2.0.0",
        "docs": "/docs",
        "api": v1,
        "endpoints": {
            "health": f"{v1}/health",
            "sessions": f"{v1}/sessions",
            "verify": f"{v1}/auth/verify",
            "officer_login": f"{v1}/officers/login",
            "pensioners": f"{v1}/pensioners",
            "enroll_complete": f"{v1}/enroll/complete",
            "reviews": f"{v1}/reviews",
            "websocket": f"{v1}/ws/{{session_id}}",
            "events_websocket": f"{v1}/ws/events?token=...",
            "telemetry_websocket": f"{v1}/ws/telemetry/{{session_id}}?nonce=...",
        },
    }
