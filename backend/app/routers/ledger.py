"""
Audit ledger, verifiable credentials and the treasury view (build-prompt §5.5–5.6).

Public (hashes / DIDs only, no personal data):
  GET  /ledger                         hash-chained entries, newest first
  GET  /ledger/verify                  recompute the whole chain
  GET  /credentials/issuer             the backend's issuer did:key
  GET  /certificates/{id}/credential   the signed credential of an issued certificate
  POST /credentials/verify             check a credential: signature, ledger record, chain
Officer:
  GET  /treasury/summary               entitlements released vs frozen, rejections by reason
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import CertificateStatus, LedgerEntry, LifeCertificate
from app.db.types import utcnow
from app.services import credentials
from app.services.certificates import certificate_record
from app.services.entitlement import treasury_summary
from app.services.ledger import hash_data, ledger

router = APIRouter()


class LedgerEntryOut(BaseModel):
    seq: int
    created_at: datetime
    event_type: str
    ref: str | None
    data_hash: str
    prev_hash: str
    entry_hash: str


class LedgerPage(BaseModel):
    total: int
    head: str | None  # latest entry_hash: the value to anchor on a public chain
    entries: list[LedgerEntryOut]


class ChainStatus(BaseModel):
    valid: bool
    entries_checked: int
    first_bad_entry: int | None
    message: str
    head: str | None
    checked_at: datetime


class CredentialVerifyRequest(BaseModel):
    credential: dict[str, Any]


def _out(e: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(seq=e.id, created_at=e.created_at, event_type=e.event_type, ref=e.ref,
                          data_hash=e.data_hash, prev_hash=e.prev_hash, entry_hash=e.entry_hash)


def _head(db) -> str | None:
    last = db.exec(select(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(1)).first()
    return last.entry_hash if last else None


@router.get("/ledger", response_model=LedgerPage, tags=["ledger"], summary="Audit ledger entries (public)")
def list_ledger(db: DbSession, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
                event_type: str | None = None) -> LedgerPage:
    stmt = select(LedgerEntry)
    count = select(func.count()).select_from(LedgerEntry)
    if event_type:
        stmt = stmt.where(LedgerEntry.event_type == event_type)
        count = count.where(LedgerEntry.event_type == event_type)
    entries = db.exec(stmt.order_by(LedgerEntry.id.desc()).offset(offset).limit(limit)).all()
    return LedgerPage(total=db.exec(count).one(), head=_head(db), entries=[_out(e) for e in entries])


@router.get("/ledger/verify", response_model=ChainStatus, tags=["ledger"], summary="Verify chain integrity (public)")
def verify_ledger(db: DbSession) -> ChainStatus:
    result = ledger.verify_chain(db)
    return ChainStatus(valid=result.valid, entries_checked=result.entries_checked,
                       first_bad_entry=result.first_bad_entry, message=result.message,
                       head=_head(db), checked_at=utcnow())


@router.get("/credentials/issuer", tags=["credentials"], summary="The backend's issuer DID")
def issuer() -> dict[str, str]:
    return {"did": credentials.issuer_did()}


@router.get("/certificates/{certificate_id}/credential", tags=["credentials"],
            summary="Signed credential for an issued life certificate (public)")
def get_credential(certificate_id: int, db: DbSession) -> dict[str, Any]:
    cert = db.get(LifeCertificate, certificate_id)
    cred = credentials.load(cert) if cert else None
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No credential for this certificate")
    return cred


@router.post("/credentials/verify", tags=["credentials"], summary="Verify a credential (public)")
def verify_credential(body: CredentialVerifyRequest, db: DbSession) -> dict[str, Any]:
    cred = body.credential
    checks: dict[str, dict[str, Any]] = {}

    ok, msg = credentials.verify_signature(cred)
    checks["signature"] = {"ok": ok, "detail": msg}

    ours = cred.get("issuer") == credentials.issuer_did()
    checks["issuer"] = {"ok": ours, "detail": "Issued by this portal" if ours else "Unknown issuer"}

    try:
        valid_from = datetime.fromisoformat(str(cred["validFrom"]).replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(str(cred["validUntil"]).replace("Z", "+00:00"))
        in_window = valid_from <= utcnow() <= valid_until
    except (KeyError, ValueError):
        in_window = False
    checks["validity_period"] = {"ok": in_window,
                                 "detail": f"valid from {cred.get('validFrom')} until {cred.get('validUntil')}"}

    # The credential's hash must belong to an issued certificate whose ledger entry
    # hashes exactly that certificate record (which includes the credential hash).
    chash = credentials.credential_hash(cred)
    cert = db.exec(select(LifeCertificate).where(LifeCertificate.credential_hash == chash)).first()
    recorded = False
    detail = "Credential hash not found on the ledger"
    if cert is not None:
        entry = db.exec(select(LedgerEntry).where(LedgerEntry.entry_hash == cert.ledger_hash)).first()
        recorded = entry is not None and entry.data_hash == hash_data(
            {**certificate_record(cert), **({"reviewed_by": cert.reviewed_by} if cert.reviewed_by else {})})
        detail = f"Recorded in ledger entry #{entry.id}" if recorded else "Ledger record does not match"
    checks["ledger_record"] = {"ok": recorded, "detail": detail, "credential_hash": chash}

    active = cert is not None and cert.status is CertificateStatus.ISSUED
    checks["certificate_status"] = {"ok": active, "detail": cert.status.value if cert else "Unknown certificate"}

    chain = ledger.verify_chain(db)
    checks["ledger_chain"] = {"ok": chain.valid, "detail": chain.message}

    return {"valid": all(c["ok"] for c in checks.values()), "checks": checks,
            "subject": cred.get("credentialSubject", {}).get("id")}


@router.get("/treasury/summary", tags=["treasury"], summary="Pensions released vs frozen (officer)")
def get_treasury_summary(db: DbSession, officer: CurrentOfficer, year: int | None = None) -> dict[str, Any]:
    return treasury_summary(db, year)
