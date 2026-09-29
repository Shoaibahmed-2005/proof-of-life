"""
Audit ledger: append-only, hash-chained, hashes only.

`LedgerBackend` is the interface the rest of the app uses. The local
implementation keeps the chain in the `audit_ledger` table; a Hyperledger
Fabric or Polygon backend can implement the same three methods and anchor
`entry_hash` values on-chain without changing any caller.

Entry hash = SHA-256 over "seq|created_at|event_type|ref|data_hash|prev_hash".
Only `data_hash` (a hash of the event data) is stored, never the data itself.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from sqlmodel import Session, select

from app.db.models import LedgerEntry
from app.db.types import utcnow

GENESIS_HASH = "0" * 64


class LedgerEvent:
    """Event types written to the ledger."""
    REGISTRATION_CAPTURED = "REGISTRATION_CAPTURED"
    REGISTRATION_APPROVED = "REGISTRATION_APPROVED"
    CERTIFICATE_ISSUED = "CERTIFICATE_ISSUED"
    CERTIFICATE_UNDER_REVIEW = "CERTIFICATE_UNDER_REVIEW"
    CERTIFICATE_REJECTED = "CERTIFICATE_REJECTED"
    REVIEW_DECISION = "REVIEW_DECISION"
    STATUS_CHANGED = "STATUS_CHANGED"
    TEMPLATE_UPDATED = "TEMPLATE_UPDATED"


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_data(data: Any) -> str:
    return sha256_hex(canonical_json(data))


def compute_entry_hash(seq: int, created_at_iso: str, event_type: str, ref: str | None,
                       data_hash: str, prev_hash: str) -> str:
    return sha256_hex(f"{seq}|{created_at_iso}|{event_type}|{ref or ''}|{data_hash}|{prev_hash}")


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    entries_checked: int
    first_bad_entry: int | None = None
    message: str = ""


class LedgerBackend(Protocol):
    def append(self, db: Session, event_type: str, data: Any, ref: str | None = None) -> LedgerEntry: ...
    def list(self, db: Session, offset: int = 0, limit: int = 50) -> list[LedgerEntry]: ...
    def verify_chain(self, db: Session) -> ChainVerification: ...


class LocalHashChainLedger:
    """Hash chain stored in the local database."""

    _lock = threading.Lock()  # serialises appends so prev_hash is always the true tip

    def append(self, db: Session, event_type: str, data: Any, ref: str | None = None) -> LedgerEntry:
        """Appends an entry and commits the caller's session (including its pending changes)."""
        with self._lock:
            last = db.exec(select(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(1)).first()
            prev_hash = last.entry_hash if last else GENESIS_HASH
            seq = (last.id if last else 0) + 1
            created_at = utcnow().replace(microsecond=0)
            data_hash = hash_data(data)
            entry = LedgerEntry(
                id=seq,
                created_at=created_at,
                event_type=event_type,
                ref=ref,
                data_hash=data_hash,
                prev_hash=prev_hash,
                entry_hash=compute_entry_hash(seq, created_at.isoformat(), event_type, ref,
                                              data_hash, prev_hash),
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry

    def list(self, db: Session, offset: int = 0, limit: int = 50) -> list[LedgerEntry]:
        stmt = select(LedgerEntry).order_by(LedgerEntry.id.desc()).offset(offset).limit(limit)
        return list(db.exec(stmt).all())

    def verify_chain(self, db: Session) -> ChainVerification:
        entries = db.exec(select(LedgerEntry).order_by(LedgerEntry.id)).all()
        prev_hash = GENESIS_HASH
        for expected_seq, e in enumerate(entries, start=1):
            if e.id != expected_seq:
                return ChainVerification(False, expected_seq - 1, e.id,
                                         f"Entry sequence broken at #{e.id} (expected #{expected_seq})")
            if e.prev_hash != prev_hash:
                return ChainVerification(False, expected_seq - 1, e.id,
                                         f"Entry #{e.id} does not link to the previous entry")
            recomputed = compute_entry_hash(e.id, e.created_at.replace(microsecond=0).isoformat(),
                                            e.event_type, e.ref, e.data_hash, e.prev_hash)
            if recomputed != e.entry_hash:
                return ChainVerification(False, expected_seq - 1, e.id,
                                         f"Entry #{e.id} has been modified")
            prev_hash = e.entry_hash
        return ChainVerification(True, len(entries), None,
                                 f"All {len(entries)} entries verified")


ledger: LedgerBackend = LocalHashChainLedger()
