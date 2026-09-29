"""Officer review queue for borderline life certificates (build-prompt §3.2, §5.3)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import CertificateStatus, LifeCertificate, Pensioner
from app.db.types import utcnow
from app.schemas.pensioner import CertificateOut, ReviewDecision, ReviewDecisionResponse, ReviewItem
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
        "ledger_hash": cert.ledger_hash, "pension_status": pensioner.status.value,
        "at": utcnow().isoformat(),
    })
    return ReviewDecisionResponse(certificate=CertificateOut.model_validate(cert),
                                  pensioner_status=pensioner.status)
