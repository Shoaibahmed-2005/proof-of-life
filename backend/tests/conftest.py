"""
Test fixtures: a fresh database per test and a simulated phone.

`Phone` mirrors the Android app: it signs the exact JSON bytes with an ECDSA
P-256 key (SHA256withECDSA, DER signature) and sends Base64 payload + SPKI key.
It uses a software key, so it can only stand in for the phone in tests.
"""

from __future__ import annotations

import base64
import json
import math
import random
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import reset_template_cipher
from app.services.credentials import reset_issuer_key
from app.db import database

DIM = 128


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    monkeypatch.setattr(settings, "TEMPLATE_KEY", "")
    monkeypatch.setattr(settings, "ISSUER_KEY_PEM", "")
    monkeypatch.setattr(settings, "LAN_SELF_CHECK", False)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://192.0.2.10:8000")
    # Fixed thresholds for the tests (real values come from calibration).
    monkeypatch.setattr(settings, "FACE_T_HIGH", 0.70)
    monkeypatch.setattr(settings, "FACE_T_LOW", 0.50)
    monkeypatch.setattr(settings, "FACE_ANCHOR_MIN", 0.55)
    monkeypatch.setattr(settings, "MIN_SNR_DB", 3.0)
    monkeypatch.setattr(settings, "MAX_FAILED_ATTEMPTS", 3)
    database.set_engine(None)
    reset_template_cipher()
    reset_issuer_key()
    from app.main import app
    with TestClient(app) as c:
        yield c
    database.get_engine().dispose()
    database.set_engine(None)
    reset_template_cipher()
    reset_issuer_key()


@pytest.fixture()
def officer_headers(client):
    r = client.post("/api/v1/officers/login",
                    json={"username": settings.DEMO_OFFICER_USERNAME,
                          "password": settings.DEMO_OFFICER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Synthetic embeddings ────────────────────────────────────────────────

def unit(vec):
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec]


def random_unit(seed: int, dim: int = DIM) -> list[float]:
    rng = random.Random(seed)
    return unit([rng.gauss(0, 1) for _ in range(dim)])


def with_cosine(base: list[float], target: float, seed: int) -> list[float]:
    """A unit vector whose cosine similarity to `base` is exactly `target`."""
    other = random_unit(seed, len(base))
    dot = sum(a * b for a, b in zip(base, other))
    orth = unit([o - dot * b for o, b in zip(other, base)])
    s = math.sqrt(max(0.0, 1 - target * target))
    return [target * b + s * o for b, o in zip(base, orth)]


# ── Simulated phone ─────────────────────────────────────────────────────

class Phone:
    def __init__(self, client: TestClient, key_level: str = "STRONGBOX") -> None:
        self.client = client
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.key_level = key_level
        self.device_id = f"dev-{id(self) % 100000}"

    @property
    def public_key_b64(self) -> str:
        der = self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return base64.b64encode(der).decode()

    def signed_request(self, payload: dict, tamper: bool = False) -> dict:
        raw = json.dumps(payload).encode()
        sig = self.key.sign(raw, ec.ECDSA(hashes.SHA256()))
        if tamper:
            raw = raw.replace(b'"bpm": ', b'"bpm": 1')
        return {"payload": base64.b64encode(raw).decode(),
                "signature": base64.b64encode(sig).decode(),
                "public_key": self.public_key_b64}

    def payload_for(self, qr: dict, **overrides) -> dict:
        ts = datetime.now(timezone.utc) + timedelta(seconds=overrides.pop("clock_offset_s", 0))
        payload = {
            "session_id": qr["session_id"], "purpose": qr["purpose"], "nonce": qr["nonce"],
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "device_id": self.device_id, "bpm": 72.4, "snr": 6.5, "liveness_passed": True,
            "challenge_id": qr["challenge"]["id"], "challenge_passed": True,
            "frames_used": 15, "app_version": "2.0.0-test", "model_version": settings.FACE_MODEL_VERSION,
            "key_security_level": self.key_level, "consent": True,
        }
        payload.update(overrides)
        return payload

    def submit(self, payload: dict, tamper: bool = False):
        return self.client.post("/api/v1/auth/verify", json=self.signed_request(payload, tamper))


# ── Flow helpers ────────────────────────────────────────────────────────

def create_pensioner(client, headers, ppo="PPO-DEF-0001", name="Havildar Ram Singh (Retd.)") -> dict:
    r = client.post("/api/v1/pensioners", headers=headers, json={
        "name": name, "ppo_number": ppo, "service_number": "JC-123456",
        "bank_last4": "4321", "monthly_pension_amount": 32000})
    assert r.status_code == 201, r.text
    return r.json()


def new_session(client, purpose="LIFE_CERTIFICATE", headers=None, **body) -> dict:
    payload = {"purpose": purpose, **body}
    if purpose == "LIFE_CERTIFICATE":
        payload.setdefault("consent", True)
    r = client.post("/api/v1/sessions", json=payload, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()


def register(client, headers, phone: Phone, template: list[float], ppo="PPO-DEF-0001") -> dict:
    """Creates a pensioner, captures enrollment with `phone`, and approves it."""
    p = create_pensioner(client, headers, ppo=ppo)
    s = new_session(client, "ENROLLMENT", headers, pensioner_id=p["id"])
    r = phone.submit(phone.payload_for(s["qr_payload"], reference_template=template))
    assert r.json()["outcome"] == "CAPTURED", r.text
    r = client.post("/api/v1/enroll/complete", headers=headers, json={"pensioner_id": p["id"]})
    assert r.status_code == 200, r.text
    return r.json()["pensioner"]
