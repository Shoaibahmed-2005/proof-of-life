"""Milestone 6: did:key, signed credentials, ledger endpoints, entitlement, treasury."""

import copy
import json

from cryptography.hazmat.primitives.asymmetric import ec
from sqlmodel import Session, select

from app.db import database
from app.db.models import LedgerEntry
from app.services import did as didmod
from tests.conftest import Phone, create_pensioner, new_session, random_unit, register, with_cosine

TEMPLATE = random_unit(11)


def issue_one(client, officer_headers, similarity=0.95):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    s = new_session(client, "LIFE_CERTIFICATE", ppo_number=p["ppo_number"])
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, similarity, 3)))
    return phone, p, r.json()


# ── did:key ─────────────────────────────────────────────────────────────

def test_did_key_roundtrip_and_format():
    for _ in range(20):
        key = ec.generate_private_key(ec.SECP256R1()).public_key()
        did = didmod.did_from_public_key(key)
        assert did.startswith("did:key:zDn")  # every P-256 did:key starts like this
        assert didmod.public_key_from_did(did).public_numbers() == key.public_numbers()


def test_base58_known_vectors():
    assert didmod.b58encode(b"hello world") == "StV1DL6CwTryKyV"
    assert didmod.b58encode(b"\x00\x00\x01") == "112"
    assert didmod.b58decode("StV1DL6CwTryKyV") == b"hello world"


def test_registration_assigns_did_from_phone_key(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    detail = client.get(f"/api/v1/pensioners/{p['id']}", headers=officer_headers).json()
    assert detail["did"] == didmod.did_from_public_key(phone.key.public_key())
    assert detail["entitlement"] == "AWAITING_CERTIFICATE"


# ── Credentials ─────────────────────────────────────────────────────────

def test_issued_certificate_has_verifiable_credential(client, officer_headers):
    phone, p, res = issue_one(client, officer_headers)
    assert res["outcome"] == "ISSUED"
    cred = client.get(f"/api/v1/certificates/{res['certificate_id']}/credential").json()

    assert cred["type"] == ["VerifiableCredential", "LifeCertificateCredential"]
    assert cred["credentialSubject"]["id"] == didmod.did_from_public_key(phone.key.public_key())
    assert cred["issuer"] == client.get("/api/v1/credentials/issuer").json()["did"]
    # No personal data in a shareable credential
    blob = json.dumps(cred)
    assert p["name"] not in blob and p["ppo_number"] not in blob and "score" not in blob.lower()

    v = client.post("/api/v1/credentials/verify", json={"credential": cred}).json()
    assert v["valid"], v
    assert all(c["ok"] for c in v["checks"].values())

    # Tampering is detected
    forged = copy.deepcopy(cred)
    forged["credentialSubject"]["lifeCertificateYear"] = 2030
    v = client.post("/api/v1/credentials/verify", json={"credential": forged}).json()
    assert not v["valid"] and not v["checks"]["signature"]["ok"] and not v["checks"]["ledger_record"]["ok"]

    # Claiming a different issuer fails: the signature doesn't match that DID's key
    impostor = copy.deepcopy(cred)
    impostor["issuer"] = didmod.did_from_public_key(ec.generate_private_key(ec.SECP256R1()).public_key())
    v = client.post("/api/v1/credentials/verify", json={"credential": impostor}).json()
    assert not v["valid"] and not v["checks"]["issuer"]["ok"] and not v["checks"]["signature"]["ok"]


def test_ws_event_carries_credential_hash(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    s = new_session(client, "LIFE_CERTIFICATE", ppo_number=p["ppo_number"])
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 4)))
        ev = ws.receive_json()
    assert ev["event"] == "CERTIFICATE_ISSUED"
    assert len(ev["credential_hash"]) == 64 and ev["did"].startswith("did:key:")


def test_officer_approved_review_also_gets_credential(client, officer_headers):
    _, _, res = issue_one(client, officer_headers, similarity=0.6)
    assert res["outcome"] == "UNDER_REVIEW"
    assert client.get(f"/api/v1/certificates/{res['certificate_id']}/credential").status_code == 404
    client.post(f"/api/v1/reviews/{res['certificate_id']}/decision", headers=officer_headers,
                json={"decision": "APPROVE", "reason": "Confirmed in person"})
    cred = client.get(f"/api/v1/certificates/{res['certificate_id']}/credential").json()
    assert cred["credentialSubject"]["reviewedByOfficer"] is True
    assert client.post("/api/v1/credentials/verify", json={"credential": cred}).json()["valid"]


# ── Ledger endpoints ────────────────────────────────────────────────────

def test_ledger_endpoints_and_tamper(client, officer_headers):
    issue_one(client, officer_headers)
    page = client.get("/api/v1/ledger").json()
    assert page["total"] == 3 and page["head"] == page["entries"][0]["entry_hash"]
    assert [e["event_type"] for e in page["entries"]] == [
        "CERTIFICATE_ISSUED", "REGISTRATION_APPROVED", "REGISTRATION_CAPTURED"]
    assert page["entries"][0]["prev_hash"] == page["entries"][1]["entry_hash"]
    assert client.get("/api/v1/ledger", params={"event_type": "CERTIFICATE_ISSUED"}).json()["total"] == 1
    assert client.get("/api/v1/ledger/verify").json()["valid"] is True

    with Session(database.get_engine()) as d:
        e = d.exec(select(LedgerEntry).where(LedgerEntry.id == 2)).one()
        e.event_type = "REGISTRATION_REVOKED"
        d.add(e)
        d.commit()
    v = client.get("/api/v1/ledger/verify").json()
    assert v["valid"] is False and v["first_bad_entry"] == 2


# ── Treasury / entitlement ──────────────────────────────────────────────

def test_treasury_summary(client, officer_headers):
    assert client.get("/api/v1/treasury/summary").status_code == 401
    phone, p, _ = issue_one(client, officer_headers)                      # A: RELEASED
    create_pensioner(client, officer_headers, ppo="PPO-PENDING-1")          # pending registration
    for i in range(3):                                                      # A then gets frozen
        s = new_session(client, "LIFE_CERTIFICATE", ppo_number=p["ppo_number"])
        phone.submit(phone.payload_for(s["qr_payload"], face_embedding=random_unit(900 + i)))
    t = client.get("/api/v1/treasury/summary", headers=officer_headers).json()
    assert t["pensioners"] == {"total": 2, "active": 0, "frozen": 1, "pending_enrollment": 1}
    assert t["entitlements"]["FROZEN"] == {"count": 1, "monthly_amount": 32000}
    assert t["entitlements"]["NOT_REGISTERED"]["count"] == 1
    assert t["certificates_this_year"] == {"issued": 1, "under_review": 0, "rejected_attempts": 3}
    assert t["rejections_by_reason"]["FACE_MISMATCH"] == 3
    row = next(r for r in t["rows"] if r["pensioner_id"] == p["id"])
    assert row["entitlement"] == "FROZEN" and row["did"].startswith("did:key:")

    client.post(f"/api/v1/reviews/frozen/{p['id']}/restore", headers=officer_headers, json={"reason": "resolved"})
    t = client.get("/api/v1/treasury/summary", headers=officer_headers).json()
    assert t["entitlements"]["RELEASED"] == {"count": 1, "monthly_amount": 32000}
    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": p["ppo_number"]}).json()
    assert pub["entitlement"] == "RELEASED" and pub["did"] == row["did"]


def test_nullable_column_migration(tmp_path):
    """A database created before credential_json existed gets the column added."""
    from sqlalchemy import create_engine, text

    from app.db.database import _add_missing_nullable_columns
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE life_certificates (id INTEGER PRIMARY KEY, credential_hash VARCHAR)"))
    _add_missing_nullable_columns(eng)
    with eng.begin() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(life_certificates)")}
    assert "credential_json" in cols and "ledger_hash" in cols
    eng.dispose()
