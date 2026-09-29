"""
Pensioner status rules.

ACTIVE ─(MAX_FAILED_ATTEMPTS rejections, or no certificate by the deadline)─► FROZEN
FROZEN ─(officer approves a life certificate in the review queue)──────────► ACTIVE

A pension is frozen, never cancelled. Every status change is written to the ledger.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import CertificateStatus, LifeCertificate, Pensioner, PensionerStatus
from app.db.types import utcnow
from app.services.ledger import LedgerEvent, ledger

logger = logging.getLogger(__name__)


def get_by_ppo(db: Session, ppo_number: str) -> Pensioner | None:
    return db.exec(select(Pensioner).where(Pensioner.ppo_number == ppo_number.strip())).first()


def set_status(db: Session, pensioner: Pensioner, status: PensionerStatus,
               reason: str | None, reason_code: str, officer_id: int | None = None) -> None:
    """Changes status, writes a ledger entry and commits."""
    if pensioner.status is status:
        return
    old = pensioner.status
    pensioner.status = status
    pensioner.status_reason = reason
    db.add(pensioner)
    data = {"pensioner_id": pensioner.id, "from": old.value, "to": status.value,
            "reason_code": reason_code, "at": utcnow().isoformat()}
    if officer_id is not None:
        data["officer_id"] = officer_id
    ledger.append(db, LedgerEvent.STATUS_CHANGED, data, ref=f"pensioner:{pensioner.id}")
    logger.info("Pensioner %s status %s → %s (%s)", pensioner.id, old.value, status.value, reason_code)


def record_failure(db: Session, pensioner: Pensioner) -> bool:
    """Counts a failed life-certificate attempt. Returns True if this froze the pension."""
    pensioner.failed_attempts += 1
    db.add(pensioner)
    if pensioner.status is PensionerStatus.ACTIVE and pensioner.failed_attempts >= settings.MAX_FAILED_ATTEMPTS:
        set_status(db, pensioner, PensionerStatus.FROZEN,
                   f"{pensioner.failed_attempts} failed life-certificate attempts", "REPEATED_FAILURES")
        return True
    db.commit()
    return False


def record_success(db: Session, pensioner: Pensioner) -> None:
    pensioner.failed_attempts = 0
    db.add(pensioner)
    if pensioner.status is PensionerStatus.FROZEN:
        set_status(db, pensioner, PensionerStatus.ACTIVE, None, "CERTIFICATE_APPROVED")
    else:
        db.commit()


def restore(db: Session, pensioner: Pensioner, officer_id: int, reason: str) -> None:
    """Officer lifts a freeze after resolving it (e.g. verified the pensioner in person)."""
    pensioner.failed_attempts = 0
    set_status(db, pensioner, PensionerStatus.ACTIVE, None, "OFFICER_RESTORED", officer_id=officer_id)
    pensioner.status_reason = f"Restored by officer: {reason}"
    db.add(pensioner)
    db.commit()


def deadline_for_year(year: int) -> date:
    month, day = (int(x) for x in settings.CERTIFICATE_DEADLINE.split("-"))
    return date(year, month, day)


def has_certificate(db: Session, pensioner_id: int, year: int) -> bool:
    stmt = (select(LifeCertificate.id)
            .where(LifeCertificate.pensioner_id == pensioner_id)
            .where(LifeCertificate.year == year)
            .where(LifeCertificate.status == CertificateStatus.ISSUED))
    return db.exec(stmt).first() is not None


def apply_deadline_freeze(db: Session, now: datetime | None = None) -> int:
    """
    After the yearly deadline, freezes ACTIVE pensioners with no issued
    certificate for the year. Pensioners registered after the deadline are
    exempt until next year. Returns the number frozen.
    """
    now = now or utcnow()
    deadline = deadline_for_year(now.year)
    if now.date() <= deadline:
        return 0
    frozen = 0
    for p in db.exec(select(Pensioner).where(Pensioner.status == PensionerStatus.ACTIVE)).all():
        if p.created_at.date() > deadline:
            continue
        if not has_certificate(db, p.id, now.year):
            set_status(db, p, PensionerStatus.FROZEN,
                       f"No life certificate submitted by {deadline.isoformat()}", "DEADLINE_MISSED")
            frozen += 1
    return frozen
