"""Pensioner records: officer registration and listing, public status lookup."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import (
    BiometricTemplate, CertificateStatus, Device, LifeCertificate, Pensioner, PensionerStatus,
)
from app.db.types import utcnow
from app.schemas.pensioner import (
    CertificateOut, DeviceOut, PensionerCreate, PensionerDetail, PensionerOut, PensionerPublic,
    RemoveRequest,
)
from app.services.connection_manager import manager
from app.services import pensioners as pensioner_service
from app.services.entitlement import entitlement_state

router = APIRouter()


def certificates_for(db, pensioner_id: int) -> list[LifeCertificate]:
    stmt = (select(LifeCertificate).where(LifeCertificate.pensioner_id == pensioner_id)
            .order_by(LifeCertificate.created_at.desc()))
    return list(db.exec(stmt).all())


def status_this_year(certs: list[LifeCertificate]) -> CertificateStatus | None:
    """Best status among this year's certificates: ISSUED > UNDER_REVIEW > REJECTED."""
    year = utcnow().year
    statuses = {c.status for c in certs if c.year == year}
    for s in (CertificateStatus.ISSUED, CertificateStatus.UNDER_REVIEW, CertificateStatus.REJECTED):
        if s in statuses:
            return s
    return None


def entitlement_of(pensioner: Pensioner, certs: list[LifeCertificate]) -> str:
    return entitlement_state(pensioner, status_this_year(certs) is CertificateStatus.ISSUED).value


@router.post("", response_model=PensionerOut, status_code=status.HTTP_201_CREATED,
             summary="Register a pensioner's details (officer)")
def create_pensioner(body: PensionerCreate, db: DbSession, officer: CurrentOfficer) -> PensionerOut:
    if pensioner_service.get_by_ppo(db, body.ppo_number):
        raise HTTPException(status.HTTP_409_CONFLICT, "A pensioner with this PPO number already exists")
    pensioner = Pensioner(**body.model_dump(), registered_by=officer.id,
                          status=PensionerStatus.PENDING_ENROLLMENT)
    db.add(pensioner)
    db.commit()
    db.refresh(pensioner)
    return PensionerOut.model_validate(pensioner)


@router.get("", response_model=list[PensionerOut], summary="List pensioners (officer)")
def list_pensioners(db: DbSession, officer: CurrentOfficer,
                    q: str | None = Query(default=None, description="Search name, PPO or service number"),
                    status_filter: PensionerStatus | None = Query(default=None, alias="status"),
                    limit: int = Query(default=200, le=1000)) -> list[PensionerOut]:
    stmt = select(Pensioner)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Pensioner.name.ilike(like), Pensioner.ppo_number.ilike(like),
                              Pensioner.service_number.ilike(like)))
    if status_filter:
        stmt = stmt.where(Pensioner.status == status_filter)
    else:  # removed records are hidden unless asked for (?status=REMOVED)
        stmt = stmt.where(Pensioner.status != PensionerStatus.REMOVED)
    stmt = stmt.order_by(Pensioner.created_at.desc()).limit(limit)
    return [PensionerOut.model_validate(p) for p in db.exec(stmt).all()]


@router.get("/lookup", response_model=PensionerPublic,
            summary="Check status by pension ID (public)")
def lookup(db: DbSession, ppo_number: str = Query(min_length=4)) -> PensionerPublic:
    pensioner = pensioner_service.get_by_ppo(db, ppo_number)
    if pensioner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pensioner found with that pension ID")
    certs = certificates_for(db, pensioner.id)
    return PensionerPublic(
        id=pensioner.id, name=pensioner.name, ppo_number=pensioner.ppo_number,
        status=pensioner.status, status_reason=pensioner.status_reason, did=pensioner.did,
        certificate_this_year=status_this_year(certs),
        entitlement=entitlement_of(pensioner, certs),
        certificates=[CertificateOut.model_validate(c) for c in certs],
    )


@router.post("/{pensioner_id}/remove", response_model=PensionerOut,
             summary="Remove a pensioner: erase face data, device keys and personal details (officer)")
async def remove_pensioner(pensioner_id: int, body: RemoveRequest, db: DbSession,
                           officer: CurrentOfficer) -> PensionerOut:
    pensioner = db.get(Pensioner, pensioner_id)
    if pensioner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pensioner not found")
    if pensioner.status is PensionerStatus.REMOVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This pensioner record is already removed")
    pensioner_service.remove(db, pensioner, officer.id, body.reason.strip())
    db.refresh(pensioner)
    await manager.publish(None, {
        "event": "STATUS_CHANGED", "pensioner_id": pensioner.id,
        "pension_status": PensionerStatus.REMOVED.value, "reason_code": "OFFICER_REMOVED",
        "at": utcnow().isoformat(),
    })
    return PensionerOut.model_validate(pensioner)


@router.get("/{pensioner_id}", response_model=PensionerDetail, summary="Pensioner detail (officer)")
def get_pensioner(pensioner_id: int, db: DbSession, officer: CurrentOfficer) -> PensionerDetail:
    pensioner = db.get(Pensioner, pensioner_id)
    if pensioner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pensioner not found")
    template = db.exec(select(BiometricTemplate)
                       .where(BiometricTemplate.pensioner_id == pensioner_id)).first()
    device = db.exec(select(Device).where(Device.pensioner_id == pensioner_id)
                     .order_by(Device.active.desc(), Device.registered_at.desc())).first()
    certs = certificates_for(db, pensioner_id)
    return PensionerDetail(
        **PensionerOut.model_validate(pensioner).model_dump(),
        has_template=template is not None,
        template_model_version=template.model_version if template else None,
        template_updates=template.update_count if template else 0,
        device=DeviceOut.model_validate(device) if device else None,
        certificate_this_year=status_this_year(certs),
        entitlement=entitlement_of(pensioner, certs),
        certificates=[CertificateOut.model_validate(c) for c in certs],
    )
