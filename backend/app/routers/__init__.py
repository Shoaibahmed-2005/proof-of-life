from fastapi import APIRouter

from app.routers import health, session, auth, ws

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(session.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# WebSocket routes are included without a prefix since they use
# the full path /ws/{session_id} directly
api_router.include_router(ws.router, tags=["websocket"])
