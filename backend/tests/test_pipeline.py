"""End-to-end tests of sessions, enrollment and the verification pipeline."""

import base64
import json
import struct
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.db import database
from app.db.models import AuthSession, BiometricTemplate, LedgerEntry, Pensioner
from app.services import face_match
from app.services.ledger import ledger
from tests.conftest import Phone, create_pensioner, new_session, random_unit, register, with_cosine

TEMPLATE = random_unit(7)


def db():
    return Session(database.get_engine())


def reason(r):
    return r.json()["reason_code"]


# ── Legacy AUTH flow (existing login demo keeps working) ────────────────

def test_legacy_auth_flow_with_fractional_bpm(client):
    s = client.post("/api/v1/sessions").json()
    assert s["purpose"] == "AUTH" and s["qr_payload"]["session_id"] == s["session_id"]
    phone = Phone(client)
    legacy = {"session_id": s["session_id"], "bpm": 72.4,
              "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "device_id": "pixel", "snr": 4.2, "variance": 2.0}
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        assert ws.receive_json()["event"] == "CONNECTED"
        r = phone.submit(legacy)
        assert r.json()["status"] == "ACCESS_GRANTED", r.text
        ev = ws.receive_json()
        assert ev["event"] == "ACCESS_GRANTED" and ev["bpm"] == 72.4
    again = phone.submit(legacy)
    assert again.json()["status"] == "ACCESS_DENIED" and reason(again) == "SESSION_ALREADY_USED"


def test_legacy_auth_denial_is_pushed_and_session_not_stuck(client):
    s = client.post("/api/v1/sessions").json()
    legacy = {"session_id": s["session_id"], "bpm": 72.4,
              "timestamp": datetime.now(timezone.utc).isoformat(),
              "device_id": "pixel", "snr": 2.8, "variance": 2.0}
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        r = Phone(client).submit(legacy)
        assert r.json()["status"] == "ACCESS_DENIED"
        assert ws.receive_json()["event"] == "REJECTED"
    assert client.get(f"/api/v1/sessions/{s['session_id']}").json()["status"] == "REJECTED"


# ── Officer auth ────────────────────────────────────────────────────────

def test_officer_login_and_protection(client, officer_headers):
    bad = client.post("/api/v1/officers/login", json={"username": "officer", "password": "nope"})
    assert bad.status_code == 401
    assert client.get("/api/v1/pensioners").status_code == 401
    assert client.get("/api/v1/reviews").status_code == 401
    assert client.get("/api/v1/pensioners", headers=officer_headers).status_code == 200
    assert client.get("/api/v1/officers/me", headers=officer_headers).json()["username"] == "officer"


def test_pensioner_validation(client, officer_headers):
    r = client.post("/api/v1/pensioners", headers=officer_headers, json={
        "name": "X Y", "ppo_number": "PPO-1", "service_number": "S1", "bank_last4": "12a4"})
    assert r.status_code == 422
    create_pensioner(client, officer_headers, ppo="PPO-DUP-1")
    dup = client.post("/api/v1/pensioners", headers=officer_headers, json={
        "name": "X Y", "ppo_number": "PPO-DUP-1", "service_number": "S1", "bank_last4": "1234"})
    assert dup.status_code == 409


# ── Enrollment ──────────────────────────────────────────────────────────

def test_enrollment_flow(client, officer_headers):
    p = create_pensioner(client, officer_headers)
    assert p["status"] == "PENDING_ENROLLMENT"

    assert client.post("/api/v1/sessions", json={"purpose": "ENROLLMENT", "pensioner_id": p["id"]}
                       ).status_code == 401
    s = new_session(client, "ENROLLMENT", officer_headers, pensioner_id=p["id"])
    qr = s["qr_payload"]
    assert qr["base_url"] == "http://192.0.2.10:8000"
    assert qr["purpose"] == "ENROLLMENT" and qr["nonce"] and qr["challenge"]["type"] in (
        "BLINK_TWICE", "TURN_LEFT", "TURN_RIGHT")

    # Life certificate is refused until registration completes
    assert client.post("/api/v1/sessions", json={"purpose": "LIFE_CERTIFICATE",
                                                 "ppo_number": p["ppo_number"], "consent": True}
                       ).status_code == 409

    phone = Phone(client)
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        r = phone.submit(phone.payload_for(qr, reference_template=TEMPLATE))
        assert r.json()["outcome"] == "CAPTURED", r.text
        ev = ws.receive_json()
        assert ev["event"] == "ENROLLMENT_CAPTURED" and ev["key_type"] == "STRONGBOX"

    detail = client.get(f"/api/v1/pensioners/{p['id']}", headers=officer_headers).json()
    assert detail["status"] == "PENDING_ENROLLMENT" and detail["has_template"]
    assert detail["device"]["active"] is False

    r = client.post("/api/v1/enroll/complete", headers=officer_headers, json={"pensioner_id": p["id"]})
    assert r.status_code == 200 and r.json()["pensioner"]["status"] == "ACTIVE"
    detail = client.get(f"/api/v1/pensioners/{p['id']}", headers=officer_headers).json()
    assert detail["device"]["active"] is True and detail["device"]["key_type"] == "STRONGBOX"

    # Cannot enroll again once active
    assert client.post("/api/v1/sessions", headers=officer_headers,
                       json={"purpose": "ENROLLMENT", "pensioner_id": p["id"]}).status_code == 409


def test_enrollment_rejects_failed_liveness(client, officer_headers):
    p = create_pensioner(client, officer_headers)
    s = new_session(client, "ENROLLMENT", officer_headers, pensioner_id=p["id"])
    phone = Phone(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], reference_template=TEMPLATE,
                                       liveness_passed=False))
    assert r.json()["outcome"] == "REJECTED" and reason(r) == "NO_PULSE"
    assert client.post("/api/v1/enroll/complete", headers=officer_headers,
                       json={"pensioner_id": p["id"]}).status_code == 409


def test_templates_are_encrypted_at_rest(client, officer_headers):
    register(client, officer_headers, Phone(client), TEMPLATE)
    with db() as d:
        row = d.exec(select(BiometricTemplate)).first()
        plain = struct.pack(f"<{len(TEMPLATE)}f", *face_match.l2_normalize(TEMPLATE))
        assert plain[:32] not in row.anchor_template
        assert face_match.cosine(face_match.decrypt_vector(row.anchor_template), TEMPLATE) > 0.9999


# ── Life certificate: three outcomes ────────────────────────────────────

def lc(client, ppo="PPO-DEF-0001"):
    return new_session(client, "LIFE_CERTIFICATE", ppo_number=ppo)


def test_strong_match_issues_certificate_and_updates_template(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.9, 1)))
        body = r.json()
        assert body["status"] == "ACCESS_GRANTED" and body["outcome"] == "ISSUED", r.text
        ev = ws.receive_json()
        assert ev["event"] == "CERTIFICATE_ISSUED" and ev["ledger_hash"] and ev["match_score"] == pytest.approx(0.9, abs=1e-3)

    with db() as d:
        t = d.exec(select(BiometricTemplate)).first()
        assert t.update_count == 1
        anchor = face_match.decrypt_vector(t.anchor_template)
        current = face_match.decrypt_vector(t.current_template)
        assert face_match.cosine(anchor, TEMPLATE) > 0.9999          # anchor never changes
        assert face_match.cosine(current, TEMPLATE) < 0.9999         # current moved a little
    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": p["ppo_number"]}).json()
    assert pub["certificate_this_year"] == "ISSUED"


def test_borderline_goes_to_review_then_officer_approves(client, officer_headers):
    phone = Phone(client)
    register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.6, 2)))
    assert r.json()["outcome"] == "UNDER_REVIEW" and reason(r) == "BORDERLINE_MATCH"

    queue = client.get("/api/v1/reviews", headers=officer_headers).json()
    assert len(queue) == 1 and queue[0]["match_score"] == pytest.approx(0.6, abs=1e-3)
    cert_id = queue[0]["id"]

    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        d = client.post(f"/api/v1/reviews/{cert_id}/decision", headers=officer_headers,
                        json={"decision": "APPROVE", "reason": "Verified by video call; lighting poor"})
        assert d.status_code == 200 and d.json()["certificate"]["status"] == "ISSUED"
        assert ws.receive_json()["event"] == "CERTIFICATE_ISSUED"
    assert client.get("/api/v1/reviews", headers=officer_headers).json() == []
    with db() as dbs:
        assert dbs.exec(select(BiometricTemplate)).first().update_count == 0  # no update on reviewed pass
    again = client.post(f"/api/v1/reviews/{cert_id}/decision", headers=officer_headers,
                        json={"decision": "REJECT", "reason": "changed my mind"})
    assert again.status_code == 409


def test_impostor_rejected_face_mismatch(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=random_unit(999)))
        assert r.json()["outcome"] == "REJECTED" and reason(r) == "FACE_MISMATCH"
        ev = ws.receive_json()
        assert ev["event"] == "REJECTED" and ev["reason"] == "Face does not match the registered pensioner"
    with db() as d:
        assert d.get(Pensioner, p["id"]).failed_attempts == 1


@pytest.mark.parametrize("override,code", [
    ({"liveness_passed": False}, "NO_PULSE"),
    ({"snr": 1.2}, "NO_PULSE"),
    ({"bpm": 250.0}, "NO_PULSE"),
    ({"challenge_passed": False}, "CHALLENGE_FAILED"),
    ({"challenge_id": "wrong-challenge"}, "CHALLENGE_MISMATCH"),
    ({"consent": False}, "CONSENT_MISSING"),
    ({"clock_offset_s": -600}, "STALE_PAYLOAD"),
    ({"model_version": "other-model"}, "MODEL_MISMATCH"),
    ({"face_embedding": [0.1] * 192}, "INVALID_EMBEDDING"),
])
def test_life_certificate_failures(client, officer_headers, override, code):
    phone = Phone(client)
    register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    fields = {"face_embedding": with_cosine(TEMPLATE, 0.95, 3), **override}
    payload = phone.payload_for(s["qr_payload"], **fields)
    r = phone.submit(payload)
    assert r.json()["outcome"] == "REJECTED" and reason(r) == code, r.text
    # Every rejection is recorded as a certificate attempt with its reason (treasury view)
    detail = client.get("/api/v1/pensioners/1", headers=officer_headers).json()
    assert detail["certificates"][0]["reason_code"] == code


def test_other_phone_rejected_device_mismatch(client, officer_headers):
    register(client, officer_headers, Phone(client), TEMPLATE)
    other = Phone(client)
    for _ in range(4):  # more than MAX_FAILED_ATTEMPTS
        s = lc(client)
        r = other.submit(other.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 4)))
        assert reason(r) == "DEVICE_MISMATCH"
    # A stranger's phone cannot freeze someone else's pension
    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": "PPO-DEF-0001"}).json()
    assert pub["status"] == "ACTIVE"
    assert [c["reason_code"] for c in pub["certificates"]].count("DEVICE_MISMATCH") == 4


def test_session_checks_before_consuming(client, officer_headers):
    phone = Phone(client)
    register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    good = phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 5))

    bad_nonce = dict(good, nonce="guessed")
    assert reason(phone.submit(bad_nonce)) == "NONCE_MISMATCH"
    assert reason(phone.submit(dict(good, purpose="ENROLLMENT", reference_template=TEMPLATE))) == "PURPOSE_MISMATCH"
    assert reason(phone.submit(good, tamper=True)) == "INVALID_SIGNATURE"
    assert reason(phone.submit(dict(good, session_id="nope"))) == "SESSION_NOT_FOUND"
    # None of those consumed the session: the genuine request still succeeds
    assert phone.submit(good).json()["outcome"] == "ISSUED"
    # ...exactly once
    assert reason(phone.submit(good)) == "SESSION_ALREADY_USED"


def test_new_qr_invalidates_older_one(client, officer_headers):
    phone = Phone(client)
    register(client, officer_headers, phone, TEMPLATE)
    first, second = lc(client), lc(client)
    r = phone.submit(phone.payload_for(first["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 6)))
    assert reason(r) == "SESSION_EXPIRED"
    r = phone.submit(phone.payload_for(second["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 6)))
    assert r.json()["outcome"] == "ISSUED"


def test_consent_required_to_create_life_certificate_session(client, officer_headers):
    register(client, officer_headers, Phone(client), TEMPLATE)
    r = client.post("/api/v1/sessions", json={"purpose": "LIFE_CERTIFICATE", "ppo_number": "PPO-DEF-0001"})
    assert r.status_code == 400
    r = client.post("/api/v1/sessions", json={"purpose": "LIFE_CERTIFICATE",
                                              "ppo_number": "NOPE-0000", "consent": True})
    assert r.status_code == 404


# ── Freeze and recovery ─────────────────────────────────────────────────

def test_repeated_failures_freeze_then_officer_restores(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    for i in range(3):
        s = lc(client)
        r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=random_unit(500 + i)))
        assert reason(r) == "FACE_MISMATCH"
    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": p["ppo_number"]}).json()
    assert pub["status"] == "FROZEN"

    # Even a strong genuine match does not auto-release a frozen pension
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 9)))
    assert r.json()["outcome"] == "UNDER_REVIEW" and reason(r) == "FROZEN_REVIEW"
    cert_id = client.get("/api/v1/reviews", headers=officer_headers).json()[0]["id"]
    d = client.post(f"/api/v1/reviews/{cert_id}/decision", headers=officer_headers,
                    json={"decision": "APPROVE", "reason": "Pensioner verified in person"})
    assert d.json()["pensioner_status"] == "ACTIVE"


def test_deadline_freeze(client, officer_headers):
    from app.services.pensioners import apply_deadline_freeze
    p = register(client, officer_headers, Phone(client), TEMPLATE)
    with db() as d:
        # created "now" (2026) → pretend it was registered in 2025 and it's now December
        pen = d.get(Pensioner, p["id"])
        pen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        d.add(pen)
        d.commit()
        assert apply_deadline_freeze(d, now=datetime(2026, 11, 30, 12, tzinfo=timezone.utc)) == 0
        assert apply_deadline_freeze(d, now=datetime(2026, 12, 1, 9, tzinfo=timezone.utc)) == 1
        d.refresh(pen)
        assert pen.status.value == "FROZEN" and "No life certificate" in pen.status_reason


# ── Ledger ──────────────────────────────────────────────────────────────

def test_ledger_chain_and_tamper_detection(client, officer_headers):
    phone = Phone(client)
    register(client, officer_headers, phone, TEMPLATE)
    s = lc(client)
    phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.9, 1)))
    with db() as d:
        entries = d.exec(select(LedgerEntry).order_by(LedgerEntry.id)).all()
        assert [e.event_type for e in entries] == [
            "REGISTRATION_CAPTURED", "REGISTRATION_APPROVED", "CERTIFICATE_ISSUED"]
        # Hashes only: no names, PPO numbers or templates in any ledger column
        blob = json.dumps([e.model_dump(mode="json") for e in entries])
        assert "Ram Singh" not in blob and "PPO-DEF" not in blob
        assert ledger.verify_chain(d).valid

        entries[1].data_hash = "f" * 64
        d.add(entries[1])
        d.commit()
        result = ledger.verify_chain(d)
        assert not result.valid and result.first_bad_entry == 2


# ── WebSockets ──────────────────────────────────────────────────────────

def test_telemetry_relay_requires_nonce(client, officer_headers):
    register(client, officer_headers, Phone(client), TEMPLATE)
    s = lc(client)
    sid, nonce = s["session_id"], s["qr_payload"]["nonce"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/v1/ws/telemetry/{sid}?nonce=wrong") as bad:
            bad.receive_text()
    with client.websocket_connect(f"/api/v1/ws/{sid}") as portal:
        portal.receive_json()
        with client.websocket_connect(f"/api/v1/ws/telemetry/{sid}?nonce={nonce}") as phone_ws:
            phone_ws.send_text(json.dumps({"type": "measuring", "bpm": 71.23456, "snr": 5.5,
                                           "progress": 0.4, "evil": "<script>"}))
            ev = portal.receive_json()
            assert ev == {"event": "MEASURING", "session_id": sid, "bpm": 71.23, "snr": 5.5, "progress": 0.4}
            phone_ws.send_text(json.dumps({"type": "challenge_issued", "challenge_type": "TURN_LEFT"}))
            assert portal.receive_json()["event"] == "CHALLENGE_ISSUED"


def test_events_channel_requires_officer(client, officer_headers):
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws/events") as ws:
            ws.receive_json()
    token = officer_headers["Authorization"].split()[1]
    phone = Phone(client)
    p = create_pensioner(client, officer_headers)
    s = new_session(client, "ENROLLMENT", officer_headers, pensioner_id=p["id"])
    with client.websocket_connect(f"/api/v1/ws/events?token={token}") as ws:
        assert ws.receive_json()["event"] == "CONNECTED"
        phone.submit(phone.payload_for(s["qr_payload"], reference_template=TEMPLATE))
        assert ws.receive_json()["event"] == "ENROLLMENT_CAPTURED"


def test_session_expiry(client):
    s = client.post("/api/v1/sessions").json()
    with db() as d:
        row = d.get(AuthSession, s["session_id"])
        row.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        d.add(row)
        d.commit()
    assert client.get(f"/api/v1/sessions/{s['session_id']}").json()["status"] == "EXPIRED"
    legacy = {"session_id": s["session_id"], "bpm": 70.0, "timestamp": datetime.now(timezone.utc).isoformat(),
              "device_id": "d", "snr": 5, "variance": 2}
    r = Phone(client).submit(legacy)
    assert r.json()["status"] == "ACCESS_DENIED"


def test_demo_finale_freeze_then_officer_restores_from_queue(client, officer_headers):
    """Demo S3-S5 freeze A; the officer restores A from the review queue; A certifies again."""
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    attacks = [dict(face_embedding=random_unit(77)),                       # S3 face mismatch
               dict(liveness_passed=False),                                # S4 photo
               dict(challenge_passed=False)]                               # S5 video
    for attack in attacks:
        s = lc(client)
        fields = {"face_embedding": with_cosine(TEMPLATE, 0.95, 8), **attack}
        assert phone.submit(phone.payload_for(s["qr_payload"], **fields)).json()["outcome"] == "REJECTED"

    frozen = client.get("/api/v1/reviews/frozen", headers=officer_headers).json()
    assert [f["pensioner"]["id"] for f in frozen] == [p["id"]]
    assert len(frozen[0]["recent_certificates"]) == 3
    assert client.get("/api/v1/reviews/frozen").status_code == 401

    token = officer_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/api/v1/ws/events?token={token}") as ws:
        ws.receive_json()
        r = client.post(f"/api/v1/reviews/frozen/{p['id']}/restore", headers=officer_headers,
                        json={"reason": "Met pensioner in person; attempts were a demo"})
        assert r.status_code == 200 and r.json()["status"] == "ACTIVE" and r.json()["failed_attempts"] == 0
        ev = ws.receive_json()
        assert ev["event"] == "STATUS_CHANGED" and ev["pension_status"] == "ACTIVE"
    assert client.get("/api/v1/reviews/frozen", headers=officer_headers).json() == []
    assert client.post(f"/api/v1/reviews/frozen/{p['id']}/restore", headers=officer_headers,
                       json={"reason": "again"}).status_code == 409

    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 9)))
    assert r.json()["outcome"] == "ISSUED"
    with db() as d:
        events = [e.event_type for e in d.exec(select(LedgerEntry).order_by(LedgerEntry.id)).all()]
        assert events.count("STATUS_CHANGED") == 2  # frozen, then restored
        assert ledger.verify_chain(d).valid


# ── Milestone 2 app on the AUTH flow ────────────────────────────────────

def m2_auth_payload(s, **overrides):
    """What the Milestone 2 app signs for an AUTH session."""
    p = {"session_id": s["session_id"], "purpose": "AUTH", "nonce": s["qr_payload"]["nonce"],
         "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "device_id": "pixel", "bpm": 71.5, "snr": 6.2, "liveness_passed": True,
         "frames_used": 290, "app_version": "2.0-m2"}
    p.update(overrides)
    return p


def test_qr_carries_min_snr(client):
    s = client.post("/api/v1/sessions").json()
    assert s["qr_payload"]["liveness"]["min_snr_db"] == 3.0
    assert s["qr_payload"]["base_url"].startswith("http")


def test_m2_app_auth_pass_and_no_pulse(client):
    phone = Phone(client)
    s = client.post("/api/v1/sessions").json()
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        assert phone.submit(m2_auth_payload(s)).json()["status"] == "ACCESS_GRANTED"
        assert ws.receive_json()["event"] == "ACCESS_GRANTED"

    # 30 s timeout without a stable pulse (photo) → the app reports liveness_passed=false
    s = client.post("/api/v1/sessions").json()
    with client.websocket_connect(f"/api/v1/ws/{s['session_id']}") as ws:
        ws.receive_json()
        r = phone.submit(m2_auth_payload(s, bpm=0.0, snr=-99.0, liveness_passed=False))
        assert r.json()["status"] == "ACCESS_DENIED" and reason(r) == "NO_PULSE"
        ev = ws.receive_json()
        assert ev["event"] == "REJECTED" and ev["reason"].startswith("No pulse detected")

    # A stable reading below the backend's own minimum is still refused
    s = client.post("/api/v1/sessions").json()
    assert reason(phone.submit(m2_auth_payload(s, snr=1.0))) == "NO_PULSE"


def test_telemetry_always_acks_even_when_throttled(client, officer_headers):
    s = client.post("/api/v1/sessions").json()
    sid, nonce = s["session_id"], s["qr_payload"]["nonce"]
    with client.websocket_connect(f"/api/v1/ws/telemetry/{sid}?nonce={nonce}") as phone_ws:
        for _ in range(3):  # faster than the 2/s relay limit
            phone_ws.send_text(json.dumps({"type": "measuring", "bpm": 70}))
            assert json.loads(phone_ws.receive_text())["ack"] is True
        phone_ws.send_text(json.dumps({"type": "unknown_type"}))
        assert json.loads(phone_ws.receive_text()) == {"ack": True, "relayed": False}


# ── Milestone 3: one face only ──────────────────────────────────────────

def test_multiple_faces_abort_is_rejected_but_not_counted(client, officer_headers):
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)
    for _ in range(4):  # more than MAX_FAILED_ATTEMPTS
        s = lc(client)
        r = phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(TEMPLATE, 0.95, 3),
                                           liveness_passed=False, abort_reason="MULTIPLE_FACES"))
        assert reason(r) == "MULTIPLE_FACES" and "More than one face" in r.json()["reason"]
    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": p["ppo_number"]}).json()
    assert pub["status"] == "ACTIVE"  # someone walking into the frame must not freeze a pension

    s = client.post("/api/v1/sessions").json()  # practice scan (AUTH) too
    auth = {"session_id": s["session_id"], "purpose": "AUTH", "nonce": s["qr_payload"]["nonce"],
            "timestamp": datetime.now(timezone.utc).isoformat(), "device_id": "d", "bpm": 0.0, "snr": -99.0,
            "liveness_passed": False, "abort_reason": "MULTIPLE_FACES"}
    assert reason(phone.submit(auth)) == "MULTIPLE_FACES"
    bad = dict(auth, abort_reason="SOMETHING_ELSE")
    assert reason(phone.submit(bad)) == "INVALID_PAYLOAD"


def test_app_aborts_and_early_failures_need_no_face_data(client, officer_headers):
    """What the Milestone 4 app sends when it stops early: the rejection must reach the pipeline."""
    phone = Phone(client)
    p = register(client, officer_headers, phone, TEMPLATE)

    # Abort with only the basics (no challenge / face fields): FACE_NOT_CAPTURED, not counted.
    s = lc(client)
    minimal = {k: v for k, v in phone.payload_for(s["qr_payload"]).items()
               if k in ("session_id", "purpose", "nonce", "timestamp", "device_id", "consent",
                        "key_security_level", "app_version", "model_version")}
    r = phone.submit(dict(minimal, bpm=0.0, snr=-99.0, liveness_passed=False, abort_reason="FACE_NOT_CAPTURED"))
    assert reason(r) == "FACE_NOT_CAPTURED", r.text

    # No pulse, no face embedding: reported as NO_PULSE (counted toward freezing).
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], liveness_passed=False, challenge_passed=False, snr=0.5))
    assert reason(r) == "NO_PULSE", r.text

    # Pulse ok, challenge failed, no embedding: CHALLENGE_FAILED.
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"], challenge_passed=False))
    assert reason(r) == "CHALLENGE_FAILED", r.text

    # Everything passed but no embedding: still refused as an invalid payload.
    s = lc(client)
    r = phone.submit(phone.payload_for(s["qr_payload"]))
    assert reason(r) == "INVALID_PAYLOAD", r.text

    pub = client.get("/api/v1/pensioners/lookup", params={"ppo_number": p["ppo_number"]}).json()
    assert pub["status"] == "ACTIVE"  # two counted failures stay below the freeze limit
