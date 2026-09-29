"""
Officer review queue (build-prompt §3.2, §5.3):
- borderline life certificates (approve / reject with a reason), and
- frozen pensions (restore once the officer has resolved the case).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import CertificateStatus, LifeCertificate, Pensioner, PensionerStatus
from app.db.types import utcnow
from app.schemas.pensioner import (
    CertificateOut, FrozenItem, PensionerOut, RestoreRequest, ReviewDecision,
    ReviewDecisionResponse, ReviewItem,
)
from app.services import certificates
from app.services import pensioners as pensioner_service
from app.services.connection_manager import manager
from app.services.ledger import LedgerEvent, ledger

router = APIRouter()


@router.get("", response_model=list[ReviewItem], summary="Certificates waiting for review (officer)")
def list_reviews(db: DbSession, officer: CurrentOfficer) -> list[ReviewItem]:
    stmt = (select(LifeCertificate, Pensioner)
            .join(Pensioner, Pensioner.id == LifeCertificate.pensioner_id)
            .where(LifeCertificate.status == CertificateStatus.UNDER_REVIEW)
            .order_by(LifeCertificate.created_at))
    return [
        ReviewItem(**CertificateOut.model_validate(cert).model_dump(),
                   pensioner_name=p.name, ppo_number=p.ppo_number, pensioner_status=p.status)
        for cert, p in db.exec(stmt).all()
    ]


@router.get("/frozen", response_model=list[FrozenItem], summary="Frozen pensions (officer)")
def list_frozen(db: DbSession, officer: CurrentOfficer) -> list[FrozenItem]:
    items = []
    for p in db.exec(select(Pensioner).where(Pensioner.status == PensionerStatus.FROZEN)
                     .order_by(Pensioner.name)).all():
        certs = db.exec(select(LifeCertificate).where(LifeCertificate.pensioner_id == p.id)
                        .order_by(LifeCertificate.created_at.desc()).limit(5)).all()
        items.append(FrozenItem(pensioner=PensionerOut.model_validate(p),
                                recent_certificates=[CertificateOut.model_validate(c) for c in certs]))
    return items


@router.post("/frozen/{pensioner_id}/restore", response_model=PensionerOut,
             summary="Lift a freeze after resolving the case (officer)")
async def restore_frozen(pensioner_id: int, body: RestoreRequest, db: DbSession,
                         officer: CurrentOfficer) -> PensionerOut:
    pensioner = db.get(Pensioner, pensioner_id)
    if pensioner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pensioner not found")
    if pensioner.status is not PensionerStatus.FROZEN:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Pension is {pensioner.status.value}, not frozen")
    pensioner_service.restore(db, pensioner, officer.id, body.reason.strip())
    db.refresh(pensioner)
    await manager.publish(None, {
        "event": "STATUS_CHANGED", "pensioner_id": pensioner.id,
        "pension_status": pensioner.status.value, "reason_code": "OFFICER_RESTORED",
        "at": utcnow().isoformat(),
    })
    return PensionerOut.model_validate(pensioner)


@router.post("/{certificate_id}/decision", response_model=ReviewDecisionResponse,
             summary="Approve or reject a certificate under review (officer)")
async def decide(certificate_id: int, body: ReviewDecision, db: DbSession,
                 officer: CurrentOfficer) -> ReviewDecisionResponse:
    cert = db.get(LifeCertificate, certificate_id)
    if cert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    if cert.status is not CertificateStatus.UNDER_REVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Certificate is already {cert.status.value}")
    pensioner = db.get(Pensioner, cert.pensioner_id)

    approve = body.decision == "APPROVE"
    cert.status = CertificateStatus.ISSUED if approve else CertificateStatus.REJECTED
    cert.reason_code = "OFFICER_APPROVED" if approve else "OFFICER_REJECTED"
    cert.reason = body.reason.strip()
    cert.reviewed_by = officer.id
    cert.reviewed_at = utcnow()
    db.add(cert)
    # Borderline or reviewed passes never update the face template (§5.4).
    if approve:
        pensioner_service.record_success(db, pensioner)
    else:
        pensioner_service.record_failure(db, pensioner)

    if approve:
        # Same issuance path as automatic approvals: signed credential + its hash on the ledger.
        certificates.record_issuance(db, cert, pensioner, reviewed_by=officer.id)
    else:
        entry = ledger.append(db, LedgerEvent.REVIEW_DECISION, {
            "certificate_id": cert.id, "pensioner_id": cert.pensioner_id, "year": cert.year,
            "decision": body.decision, "reviewed_by": officer.id, "at": cert.reviewed_at.isoformat(),
        }, ref=f"certificate:{cert.id}")
        cert.ledger_hash = entry.entry_hash
        db.add(cert)
        db.commit()
    db.refresh(cert)
    db.refresh(pensioner)

    await manager.publish(cert.session_id, {
        "event": "CERTIFICATE_ISSUED" if approve else "REJECTED",
        "session_id": cert.session_id, "pensioner_id": cert.pensioner_id,
        "certificate_id": cert.id, "year": cert.year, "reviewed": True,
        "reason_code": cert.reason_code, "reason": cert.reason,
        "ledger_hash": cert.ledger_hash, "credential_hash": cert.credential_hash,
        "pension_status": pensioner.status.value,
        "at": utcnow().isoformat(),
    })
    return ReviewDecisionResponse(certificate=CertificateOut.model_validate(cert),
                                  pensioner_status=pensioner.status)
