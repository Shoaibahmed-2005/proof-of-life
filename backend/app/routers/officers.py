"""Officer login (simple demo authentication)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.core.security import create_officer_token, verify_password
from app.db.models import Officer
from app.schemas.pensioner import LoginResponse, OfficerLogin, OfficerOut

router = APIRouter()


@router.post("/login", response_model=LoginResponse, summary="Officer login")
def login(body: OfficerLogin, db: DbSession) -> LoginResponse:
    officer = db.exec(select(Officer).where(Officer.username == body.username.strip())).first()
    if officer is None or not verify_password(body.password, officer.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    token, exp = create_officer_token(officer.id)
    return LoginResponse(access_token=token, expires_at=exp, officer=OfficerOut.model_validate(officer))


@router.get("/me", response_model=OfficerOut, summary="Current officer")
def me(officer: CurrentOfficer) -> OfficerOut:
    return OfficerOut.model_validate(officer)
