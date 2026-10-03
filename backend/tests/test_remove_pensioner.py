"""Officer removal of a pensioner: biometric data erased, audit chain intact, re-registration works."""

from sqlmodel import Session, select

from app.db import database
from app.db.models import AuthSession, BiometricTemplate, Device, LifeCertificate, Pensioner, SessionStatus
from tests.conftest import Phone, new_session, random_unit, register, with_cosine

TEMPLATE = random_unit(11)
PPO = "PPO-DEF-0001"


def lc(client):
    return new_session(client, "LIFE_CERTIFICATE", ppo_number=PPO)


def test_remove_erases_biometrics_and_allows_reregistration(client, officer_headers):
    phone = Phone(client)
    old = register(client, officer_headers, phone, TEMPLATE, ppo=PPO)
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 1)))
    assert r.json()["outcome"] == "ISSUED", r.text
    pending = lc(client)  # an open QR code at the moment of removal

    r = client.post(f"/api/v1/pensioners/{old['id']}/remove", headers=officer_headers,
                    json={"reason": "Test registration"})
    assert r.status_code == 200, r.text
    removed = r.json()
    assert removed["status"] == "REMOVED"
    assert removed["name"] == "Removed pensioner" and removed["ppo_number"] == f"REMOVED-{old['id']}"

    with Session(database.get_engine()) as db:
        # Face data and the phone binding are gone; personal details erased.
        assert db.exec(select(BiometricTemplate).where(BiometricTemplate.pensioner_id == old["id"])).first() is None
        assert db.exec(select(Device).where(Device.pensioner_id == old["id"])).first() is None
        p = db.get(Pensioner, old["id"])
        assert p.service_number == "" and p.bank_last4 == "" and p.did is None
        assert db.get(AuthSession, pending["session_id"]).status is SessionStatus.EXPIRED
        # The issued certificate stays as an anonymous audit record.
        assert db.exec(select(LifeCertificate).where(LifeCertificate.pensioner_id == old["id"])).first() is not None

    # The old record is not reachable any more.
    assert client.get("/api/v1/pensioners/lookup", params={"ppo_number": PPO}).status_code == 404
    assert client.post("/api/v1/sessions", json={"purpose": "LIFE_CERTIFICATE", "ppo_number": PPO,
                                                  "consent": True}).status_code == 404
    assert client.post("/api/v1/sessions", json={"purpose": "LIFE_CERTIFICATE", "pensioner_id": old["id"],
                                                  "consent": True}).status_code == 404
    listed = client.get("/api/v1/pensioners", headers=officer_headers).json()
    assert all(x["id"] != old["id"] for x in listed)
    assert client.post(f"/api/v1/pensioners/{old['id']}/remove", headers=officer_headers,
                       json={"reason": "again"}).status_code == 409

    # The audit chain still verifies (the removal is an entry on it).
    chain = client.get("/api/v1/ledger/verify").json()
    assert chain["valid"] is True, chain

    # The same person registers again: a new record with a new face template.
    new_face = random_unit(12)
    new = register(client, officer_headers, phone, new_face, ppo=PPO)
    assert new["id"] != old["id"] and new["status"] == "ACTIVE"
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(new_face, 0.95, 2)))
    assert r.json()["outcome"] == "ISSUED", r.text
    # Nothing of the old face is used: the old template no longer matches.
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.99, 3)))
    assert r.json()["reason_code"] == "FACE_MISMATCH", r.text
    assert client.get("/api/v1/ledger/verify").json()["valid"] is True

    summary = client.get("/api/v1/treasury/summary", headers=officer_headers).json()
    assert summary["pensioners"]["removed"] == 1
    assert all(row["pensioner_id"] != old["id"] for row in summary["rows"])


def test_remove_requires_officer(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE, ppo=PPO)
    r = client.post(f"/api/v1/pensioners/{p['id']}/remove", json={"reason": "no auth"})
    assert r.status_code == 401
