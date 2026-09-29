from fastapi import APIRouter

from app.routers import auth, enroll, health, ledger, officers, pensioners, reviews, session, ws

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(session.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(officers.router, prefix="/officers", tags=["officers"])
api_router.include_router(pensioners.router, prefix="/pensioners", tags=["pensioners"])
api_router.include_router(enroll.router, prefix="/enroll", tags=["enrollment"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(ledger.router)  # /ledger, /credentials, /certificates/{id}/credential, /treasury

# WebSocket routes are included without a prefix since they use
# full paths such as /ws/{session_id}
api_router.include_router(ws.router, tags=["websocket"])
