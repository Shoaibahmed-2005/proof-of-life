"""
Issuing a life certificate: one code path for automatic approvals and for
officer approvals from the review queue.

  certificate ISSUED → signed credential (subject = pensioner's did:key)
                     → SHA-256 of the credential stored on the certificate
                     → ledger entry CERTIFICATE_ISSUED carrying that hash
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.db.models import Device, LedgerEntry, LifeCertificate, Pensioner
from app.services import credentials
from app.services.did import did_from_pem
from app.services.ledger import LedgerEvent, ledger


def ensure_did(db: Session, pensioner: Pensioner) -> str | None:
    """The pensioner's did:key, derived from their active device key (set at registration approval)."""
    if pensioner.did:
        return pensioner.did
    device = db.exec(select(Device).where(Device.pensioner_id == pensioner.id)
                     .where(Device.active == True)).first()  # noqa: E712
    if device is None:
        return None
    pensioner.did = did_from_pem(device.public_key_pem)
    db.add(pensioner)
    return pensioner.did


def certificate_record(cert: LifeCertificate) -> dict[str, Any]:
    """The certificate facts that are hashed into the ledger (no personal data)."""
    return {
        "certificate_id": cert.id, "pensioner_id": cert.pensioner_id, "year": cert.year,
        "status": cert.status.value, "match_score": cert.match_score,
        "session_id": cert.session_id, "created_at": cert.created_at.isoformat(),
        "credential_hash": cert.credential_hash,
    }


def record_issuance(db: Session, cert: LifeCertificate, pensioner: Pensioner,
                    reviewed_by: int | None = None) -> LedgerEntry:
    """Signs the credential and writes the CERTIFICATE_ISSUED ledger entry (commits)."""
    did = ensure_did(db, pensioner)
    if did is not None:
        credential = credentials.issue_life_certificate(cert, did, reviewed_by is not None)
        cert.credential_json = json.dumps(credential, separators=(",", ":"))
        cert.credential_hash = credentials.credential_hash(credential)
    record = certificate_record(cert)
    if reviewed_by is not None:
        record["reviewed_by"] = reviewed_by
    entry = ledger.append(db, LedgerEvent.CERTIFICATE_ISSUED, record, ref=f"certificate:{cert.id}")
    cert.ledger_hash = entry.entry_hash
    db.add(cert)
    db.commit()
    return entry
