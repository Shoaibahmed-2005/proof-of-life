"""
Seed DUMMY demo data (fictional pensioners) so the portal's Records, Review
Queue, Treasury and Ledger pages have something to show besides the live demo.

- Never uses real people, Aadhaar numbers or real account numbers.
- Seeded pensioners use synthetic faces and simulator keys (see
  simulate_phone.py: --person <PPO> --device sim-<PPO>), marked SOFTWARE.
- Only runs if there are no pensioners yet (use --force to add anyway).

Run from the backend/ folder:  python scripts/seed_demo.py
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.database import get_engine, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    BiometricTemplate, CertificateStatus, Device, KeyType, LifeCertificate, Officer, Pensioner,
    PensionerStatus,
)
from app.db.types import utcnow  # noqa: E402
from app.services import face_match  # noqa: E402
from app.services.did import did_from_pem  # noqa: E402
from app.services.ledger import LedgerEvent, ledger  # noqa: E402
from app.services.certificates import certificate_record, record_issuance  # noqa: E402
from scripts.simulate_phone import load_key, person_face  # noqa: E402

# name, PPO, service no., bank last 4, monthly amount, scenario
PENSIONERS = [
    ("Subedar Kiran Deshmukh (Retd.)", "PPO-DEMO-1001", "JC-410231", "1187", 41500, "issued"),
    ("Naik Arjun Pillai (Retd.)", "PPO-DEMO-1002", "NK-552910", "2043", 28750, "issued"),
    ("Havildar Suresh Negi (Retd.)", "PPO-DEMO-1003", "HV-338104", "7719", 31200, "active"),
    ("Petty Officer Joseph Mathew (Retd.)", "PPO-DEMO-1004", "PO-120877", "5530", 36900, "review"),
    ("Sergeant Balwant Gill (Retd.)", "PPO-DEMO-1005", "SG-778215", "9024", 33400, "frozen"),
    ("Lance Naik Meera Rawat (Retd.)", "PPO-DEMO-1006", "LN-640553", "3361", 26100, "pending"),
]


def seed(force: bool = False) -> int:
    init_db()
    with Session(get_engine()) as db:
        if not force and db.exec(select(Pensioner)).first() is not None:
            print("Pensioners already exist; nothing seeded (use --force to add anyway).")
            return 0
        officer = db.exec(select(Officer)).first()
        year = utcnow().year
        for name, ppo, service_no, last4, amount, scenario in PENSIONERS:
            if db.exec(select(Pensioner).where(Pensioner.ppo_number == ppo)).first():
                continue
            p = Pensioner(name=name, ppo_number=ppo, service_number=service_no, bank_last4=last4,
                          monthly_pension_amount=amount, registered_by=officer.id if officer else None,
                          status=PensionerStatus.PENDING_ENROLLMENT)
            db.add(p)
            db.commit()
            db.refresh(p)
            if scenario == "pending":
                print(f"  {ppo}  {scenario}")
                continue

            face = person_face(ppo)
            enc = face_match.encrypt_vector(face)
            db.add(BiometricTemplate(pensioner_id=p.id, anchor_template=enc, current_template=enc,
                                     embedding_dim=len(face), model_version=settings.FACE_MODEL_VERSION))
            key = load_key(f"sim-{ppo}")
            der = key.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
            pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            db.add(Device(pensioner_id=p.id, public_key_pem=pem, key_type=KeyType.SOFTWARE,
                          device_id=f"simulator:sim-{ppo}", active=True))
            p.status = PensionerStatus.ACTIVE
            p.did = did_from_pem(pem)
            db.add(p)
            ledger.append(db, LedgerEvent.REGISTRATION_APPROVED, {
                "pensioner_id": p.id, "seeded": True, "key_type": "SOFTWARE",
                "key_fingerprint": base64.b16encode(der[-16:]).decode(), "at": utcnow().isoformat(),
            }, ref=f"pensioner:{p.id}")

            def add_cert(status, score, code=None, reason=None, bpm=74.0, snr=7.1, passed=True):
                cert = LifeCertificate(pensioner_id=p.id, year=year, status=status, match_score=score,
                                       anchor_score=score, bpm=bpm, snr=snr, challenge_type="BLINK_TWICE",
                                       challenge_passed=passed, key_type=KeyType.SOFTWARE,
                                       session_id=f"seed-{ppo}-{status.value}-{score}",
                                       reason_code=code, reason=reason)
                db.add(cert)
                db.flush()
                if status is CertificateStatus.ISSUED:
                    record_issuance(db, cert, p)  # signed credential + ledger entry
                    return
                event = {CertificateStatus.ISSUED: LedgerEvent.CERTIFICATE_ISSUED,
                         CertificateStatus.UNDER_REVIEW: LedgerEvent.CERTIFICATE_UNDER_REVIEW,
                         CertificateStatus.REJECTED: LedgerEvent.CERTIFICATE_REJECTED}[status]
                entry = ledger.append(db, event, certificate_record(cert), ref=f"certificate:{cert.id}")
                cert.ledger_hash = entry.entry_hash
                db.add(cert)
                db.commit()

            if scenario == "issued":
                add_cert(CertificateStatus.ISSUED, 0.86)
            elif scenario == "review":
                add_cert(CertificateStatus.UNDER_REVIEW, 0.61, "BORDERLINE_MATCH",
                         "Face match is borderline; sent for officer review")
            elif scenario == "frozen":
                add_cert(CertificateStatus.REJECTED, 0.12, "FACE_MISMATCH",
                         "Face does not match the registered pensioner")
                add_cert(CertificateStatus.REJECTED, None, "NO_PULSE",
                         "No pulse detected: the scan did not find a stable heartbeat.", bpm=0, snr=1.1,
                         passed=None)
                add_cert(CertificateStatus.REJECTED, None, "CHALLENGE_FAILED",
                         "Challenge failed: the requested action was not performed in time", passed=False)
                p.status = PensionerStatus.FROZEN
                p.status_reason = "3 failed life-certificate attempts"
                p.failed_attempts = 3
                db.add(p)
                ledger.append(db, LedgerEvent.STATUS_CHANGED, {
                    "pensioner_id": p.id, "from": "ACTIVE", "to": "FROZEN",
                    "reason_code": "REPEATED_FAILURES", "seeded": True, "at": utcnow().isoformat(),
                }, ref=f"pensioner:{p.id}")
            db.commit()
            print(f"  {ppo}  {scenario}")
    print("Demo data seeded.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true")
    raise SystemExit(seed(parser.parse_args().force))
