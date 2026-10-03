"""
Pension entitlement as an asset owned by the pensioner's DID (build-prompt §5.5).

For the current year the entitlement is:
  RELEASED              a life certificate was issued this year (and the pension isn't frozen)
  AWAITING_CERTIFICATE  active pension, no certificate yet this year (before the deadline)
  FROZEN                pension frozen (repeated failures or missed deadline)
  NOT_REGISTERED        registration not completed
Payment would be released only in the RELEASED state.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Any

from sqlmodel import Session, select

from app.db.models import CertificateStatus, LifeCertificate, Pensioner, PensionerStatus
from app.db.types import utcnow
from app.services.pensioners import deadline_for_year

# Rejection reasons shown separately on the treasury dashboard; the rest are grouped as OTHER.
HEADLINE_REASONS = ("NO_PULSE", "FACE_MISMATCH", "CHALLENGE_FAILED", "DEVICE_MISMATCH")


class Entitlement(str, Enum):
    RELEASED = "RELEASED"
    AWAITING_CERTIFICATE = "AWAITING_CERTIFICATE"
    FROZEN = "FROZEN"
    NOT_REGISTERED = "NOT_REGISTERED"


def entitlement_state(pensioner: Pensioner, issued_this_year: bool) -> Entitlement:
    if pensioner.status in (PensionerStatus.PENDING_ENROLLMENT, PensionerStatus.REMOVED):
        return Entitlement.NOT_REGISTERED
    if pensioner.status is PensionerStatus.FROZEN:
        return Entitlement.FROZEN
    return Entitlement.RELEASED if issued_this_year else Entitlement.AWAITING_CERTIFICATE


def treasury_summary(db: Session, year: int | None = None) -> dict[str, Any]:
    year = year or utcnow().year
    pensioners = db.exec(select(Pensioner).where(Pensioner.status != PensionerStatus.REMOVED)
                         .order_by(Pensioner.name)).all()
    removed = len(db.exec(select(Pensioner.id).where(Pensioner.status == PensionerStatus.REMOVED)).all())
    certs = db.exec(select(LifeCertificate).where(LifeCertificate.year == year)).all()

    by_pensioner: dict[int, list[LifeCertificate]] = {}
    for c in certs:
        by_pensioner.setdefault(c.pensioner_id, []).append(c)

    entitlements = {e.value: {"count": 0, "monthly_amount": 0} for e in Entitlement}
    status_counts = Counter(p.status.value for p in pensioners)
    rows = []
    for p in pensioners:
        mine = by_pensioner.get(p.id, [])
        issued = any(c.status is CertificateStatus.ISSUED for c in mine)
        state = entitlement_state(p, issued)
        entitlements[state.value]["count"] += 1
        entitlements[state.value]["monthly_amount"] += p.monthly_pension_amount
        latest = max(mine, key=lambda c: c.created_at) if mine else None
        rows.append({
            "pensioner_id": p.id, "name": p.name, "ppo_number": p.ppo_number,
            "status": p.status.value, "entitlement": state.value,
            "monthly_pension_amount": p.monthly_pension_amount, "did": p.did,
            "latest_certificate_status": latest.status.value if latest else None,
            "latest_certificate_at": latest.created_at.isoformat() if latest else None,
        })

    cert_counts = Counter(c.status.value for c in certs)
    rejected = [c for c in certs if c.status is CertificateStatus.REJECTED]
    reasons = Counter(c.reason_code if c.reason_code in HEADLINE_REASONS else "OTHER" for c in rejected)

    return {
        "year": year,
        "deadline": deadline_for_year(year).isoformat(),
        "pensioners": {
            "total": len(pensioners),
            "active": status_counts.get(PensionerStatus.ACTIVE.value, 0),
            "frozen": status_counts.get(PensionerStatus.FROZEN.value, 0),
            "pending_enrollment": status_counts.get(PensionerStatus.PENDING_ENROLLMENT.value, 0),
            "removed": removed,
        },
        "entitlements": entitlements,
        "certificates_this_year": {
            "issued": cert_counts.get(CertificateStatus.ISSUED.value, 0),
            "under_review": cert_counts.get(CertificateStatus.UNDER_REVIEW.value, 0),
            "rejected_attempts": cert_counts.get(CertificateStatus.REJECTED.value, 0),
        },
        "rejections_by_reason": {code: reasons.get(code, 0) for code in (*HEADLINE_REASONS, "OTHER")},
        "rows": rows,
    }
