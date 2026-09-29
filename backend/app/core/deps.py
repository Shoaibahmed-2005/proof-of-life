"""Shared FastAPI dependencies: database session and officer authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from app.core.security import decode_officer_token
from app.db.database import get_db
from app.db.models import Officer

DbSession = Annotated[Session, Depends(get_db)]


def _officer_from_header(db: Session, authorization: str | None) -> Officer | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    officer_id = decode_officer_token(authorization.split(" ", 1)[1].strip())
    return db.get(Officer, officer_id) if officer_id is not None else None


def optional_officer(db: DbSession, authorization: Annotated[str | None, Header()] = None) -> Officer | None:
    return _officer_from_header(db, authorization)


def require_officer(db: DbSession, authorization: Annotated[str | None, Header()] = None) -> Officer:
    officer = _officer_from_header(db, authorization)
    if officer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Officer login required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return officer


CurrentOfficer = Annotated[Officer, Depends(require_officer)]
MaybeOfficer = Annotated[Officer | None, Depends(optional_officer)]
