"""
Jeevan Suraksha backend — application entrypoint.

Pension life-certificate system on the IoB liveness engine: sessions and QR
payloads, verification of Titan M2-signed biometric payloads, pensioner
records, the officer review queue, the audit ledger and WebSocket push.

Run:  python run.py          (listens on 0.0.0.0:8000 so phones on the Wi-Fi can connect)
"""

from contextlib import asynccontextmanager
import asyncio
import logging
import os
import urllib.request

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.core import network
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


def _lan_self_check(port: int) -> None:
    """Warns if the backend can't be reached on its own LAN address (e.g. bound to 127.0.0.1)."""
    if settings.PUBLIC_BASE_URL:
        return
    ip = network.lan_ip()
    if not ip:
        return
    url = f"http://{ip}:{port}{settings.API_V1_STR}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            ok = r.status == 200
    except Exception as e:  # noqa: BLE001 - any failure means phones can't connect either
        ok = False
        logger.warning("LAN self-check failed for %s: %s", url, e)
    if ok:
        logger.info("LAN self-check OK: phones on this Wi-Fi can use http://%s:%d", ip, port)
    else:
        logger.warning(
            "!! Phones on the Wi-Fi will NOT reach this backend at http://%s:%d. "
            "Start it with `python run.py` (listens on 0.0.0.0), not plain `uvicorn app.main:app`.", ip, port)


async def _delayed_self_check(port: int) -> None:
    await asyncio.sleep(1.5)  # let the server start accepting connections
    await asyncio.to_thread(_lan_self_check, port)


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
    port = int(os.environ.get("JS_BIND_PORT", "8000"))
    print(network.startup_report(port, settings.PUBLIC_BASE_URL), flush=True)
    self_check = asyncio.create_task(_delayed_self_check(port)) if settings.LAN_SELF_CHECK else None
    yield
    # ── Shutdown ────────────────────────────────────────────────────────
    maintenance.cancel()
    if self_check:
        self_check.cancel()
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
# The portal may be opened from other devices on the Wi-Fi (http://<laptop-ip>:5173),
# so private-network origins are allowed as well as the configured list.
LAN_ORIGIN_REGEX = (r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
                    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$")
if settings.BACKEND_CORS_ORIGINS or settings.CORS_ALLOW_LAN:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_origin_regex=LAN_ORIGIN_REGEX if settings.CORS_ALLOW_LAN else None,
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
