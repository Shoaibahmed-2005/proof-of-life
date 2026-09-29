"""Tests for the calibration, simulator and seed scripts."""

import json

from scripts import calibrate_thresholds as cal
from scripts import seed_demo, simulate_phone
from tests.conftest import new_session


def test_suggest_thresholds_separated():
    genuine = [0.78, 0.81, 0.84, 0.86, 0.9, 0.74, 0.88, 0.8, 0.83, 0.79]
    impostor = [0.12, 0.2, 0.31, 0.25, 0.4, 0.18, 0.22, 0.28, 0.35, 0.3]
    s = cal.suggest_thresholds(genuine, impostor)
    assert s["separated"]
    assert s["t_low"] < s["t_high"]
    assert s["t_high"] > max(impostor)          # no tested impostor auto-approves
    assert s["t_low"] < min(genuine)            # no tested genuine scan is rejected outright
    assert s["genuine_auto_approve_rate"] == 1.0


def test_suggest_thresholds_overlap_sends_overlap_to_review():
    genuine = [0.55, 0.7, 0.8]
    impostor = [0.3, 0.6]
    s = cal.suggest_thresholds(genuine, impostor)
    assert not s["separated"] and s["t_low"] < s["t_high"]


def test_label_and_report_cli(tmp_path, capsys):
    path = tmp_path / "scores.csv"
    rows = [dict(timestamp="t", session_id=f"s{i}", pensioner_id="1", score=f"{sc}",
                 anchor_score=f"{sc}", band="X", model_version="m", label="")
            for i, sc in enumerate([0.8, 0.82, 0.85, 0.2, 0.25])]
    cal.save_rows(path, rows)
    assert cal.main(["--csv", str(path), "label", "--last", "2", "--as", "impostor"]) == 0
    assert cal.main(["--csv", str(path), "label", "--last", "3", "--as", "genuine"]) == 0
    assert cal.main(["--csv", str(path), "report"]) == 0
    out = capsys.readouterr().out
    assert "FACE_T_HIGH=" in out and "FACE_T_LOW=" in out


def test_score_log_written_by_pipeline(client, officer_headers):
    """The backend itself logs life-certificate scores for calibration."""
    from app.core.config import settings
    from tests.conftest import Phone, random_unit, register, with_cosine
    t = random_unit(1)
    phone = Phone(client)
    register(client, officer_headers, phone, t)
    s = new_session(client, "LIFE_CERTIFICATE", ppo_number="PPO-DEF-0001")
    phone.submit(phone.payload_for(s["qr_payload"], face_embedding=with_cosine(t, 0.8, 2)))
    rows = cal.load_rows(settings.DATA_DIR / "match_scores.csv")
    assert len(rows) == 1 and float(rows[0]["score"]) == 0.8 and rows[0]["band"] == "APPROVE"


def test_simulator_builds_valid_requests(client, officer_headers):
    """The simulator's signed requests pass the real pipeline (enroll → certify → impostor)."""
    from tests.conftest import create_pensioner

    def run(qr, **kw):
        args = type("A", (), dict(person="A", device="pixel-sim", similarity=0.92, bpm=72.0, legacy=False,
                                  snr=7.5, no_pulse=False, challenge_fail=False) | kw)
        return client.post("/api/v1/auth/verify", json=simulate_phone.build_request(qr, args)).json()

    p = create_pensioner(client, officer_headers)
    s = new_session(client, "ENROLLMENT", officer_headers, pensioner_id=p["id"])
    assert run(s["qr_payload"])["outcome"] == "CAPTURED"
    client.post("/api/v1/enroll/complete", headers=officer_headers, json={"pensioner_id": p["id"]})
    lc = lambda: new_session(client, "LIFE_CERTIFICATE", ppo_number=p["ppo_number"])["qr_payload"]
    assert run(lc())["outcome"] == "ISSUED"
    assert run(lc(), person="B")["reason_code"] == "FACE_MISMATCH"
    assert run(lc(), no_pulse=True)["reason_code"] == "NO_PULSE"
    assert run(lc(), challenge_fail=True)["reason_code"] == "CHALLENGE_FAILED"
    assert run(lc(), similarity=0.6)["outcome"] == "UNDER_REVIEW"


def test_seed_demo(client, officer_headers):
    assert seed_demo.seed() == 0
    people = client.get("/api/v1/pensioners", headers=officer_headers).json()
    statuses = sorted(p["status"] for p in people)
    assert statuses.count("ACTIVE") == 4 and statuses.count("FROZEN") == 1
    assert statuses.count("PENDING_ENROLLMENT") == 1
    assert len(client.get("/api/v1/reviews", headers=officer_headers).json()) == 1
    from app.db.database import get_engine
    from app.services.ledger import ledger
    from sqlmodel import Session
    with Session(get_engine()) as d:
        assert ledger.verify_chain(d).valid
    assert seed_demo.seed() == 0  # second run is a no-op


def test_reset_demo_moves_data_and_starts_clean(client, officer_headers, capsys):
    from app.core.config import settings
    from app.db import database
    from scripts import reset_demo
    from tests.conftest import create_pensioner

    create_pensioner(client, officer_headers)
    assert reset_demo.reset(confirm=False, seed=False) == 0          # dry run changes nothing
    assert len(client.get("/api/v1/pensioners", headers=officer_headers).json()) == 1

    database.get_engine().dispose()   # release the SQLite file (Windows locks it)
    database.set_engine(None)
    assert reset_demo.reset(confirm=True, seed=False) == 0
    backups = list((settings.DATA_DIR / "backups").iterdir())
    assert len(backups) == 1 and (backups[0] / "iob.db").exists()     # moved, not deleted
    assert client.get("/api/v1/pensioners", headers=officer_headers).json() == []
    # the demo officer still logs in on the fresh database
    assert client.post("/api/v1/officers/login", json={"username": "officer",
                                                        "password": "officer123"}).status_code == 200
