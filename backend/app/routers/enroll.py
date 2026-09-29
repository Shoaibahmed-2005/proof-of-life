"""Officer approval of a captured registration (build-prompt §3.1 step 6)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import (
    AuthSession, BiometricTemplate, Device, Pensioner, PensionerStatus, SessionPurpose, SessionStatus,
)
from app.db.types import utcnow
from app.schemas.pensioner import EnrollComplete, EnrollCompleteResponse, PensionerOut
from app.services.connection_manager import manager
from app.services.did import did_from_pem
from app.services.ledger import LedgerEvent, ledger

router = APIRouter()


@router.post("/complete", response_model=EnrollCompleteResponse,
             summary="Approve a captured registration (officer)")
async def complete_enrollment(body: EnrollComplete, db: DbSession,
                              officer: CurrentOfficer) -> EnrollCompleteResponse:
    pensioner = db.get(Pensioner, body.pensioner_id)
    if pensioner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pensioner not found")
    if pensioner.status is not PensionerStatus.PENDING_ENROLLMENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "This pensioner is already registered")

    template = db.exec(select(BiometricTemplate)
                       .where(BiometricTemplate.pensioner_id == pensioner.id)).first()
    device = db.exec(select(Device).where(Device.pensioner_id == pensioner.id)
                     .where(Device.active == False)  # noqa: E712
                     .order_by(Device.registered_at.desc())).first()
    if template is None or device is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No face scan captured yet. Ask the pensioner to scan the QR code first.")

    device.active = True
    pensioner.status = PensionerStatus.ACTIVE
    pensioner.status_reason = None
    pensioner.failed_attempts = 0
    # The pensioner's decentralized identifier, derived from the bound phone key.
    pensioner.did = did_from_pem(device.public_key_pem)
    db.add(device)
    db.add(pensioner)
    entry = ledger.append(db, LedgerEvent.REGISTRATION_APPROVED, {
        "pensioner_id": pensioner.id, "did": pensioner.did, "approved_by": officer.id,
        "key_type": device.key_type.value, "model_version": template.model_version,
        "at": utcnow().isoformat(),
    }, ref=f"pensioner:{pensioner.id}")
    db.refresh(pensioner)

    last_capture = db.exec(select(AuthSession)
                           .where(AuthSession.pensioner_id == pensioner.id)
                           .where(AuthSession.purpose == SessionPurpose.ENROLLMENT)
                           .where(AuthSession.status == SessionStatus.COMPLETED)
                           .order_by(AuthSession.completed_at.desc())).first()
    await manager.publish(last_capture.session_id if last_capture else None, {
        "event": "ENROLLMENT_APPROVED", "pensioner_id": pensioner.id,
        "session_id": last_capture.session_id if last_capture else None,
        "ledger_hash": entry.entry_hash, "did": pensioner.did, "at": utcnow().isoformat(),
    })
    return EnrollCompleteResponse(pensioner=PensionerOut.model_validate(pensioner),
                                  ledger_hash=entry.entry_hash)
