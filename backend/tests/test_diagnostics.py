"""Step 2: scan diagnostics stored with every result, gate settings in the QR, calibration report."""

from datetime import datetime, timezone

from app.db.models import ScanDiagnostic
from scripts import calibrate_thresholds as cal
from tests.conftest import Phone

GOOD = dict(scan_seconds=12.4, avg_fps=29.6, min_fps=27.1, frames=370, face_lost_count=0, best_snr_db=7.2,
            final_spread_bpm=1.1, mean_luma=132, skin_fraction=0.71, estimates=16, min_snr_db=3.0,
            gate_sec_window=9.5, gate_sec_stable=1.2, gate_sec_snr=0.0, gate_sec_face=0.4,
            last_gate="READY", ae_locked=True, fps_range="[30,30]", device_model="Google Pixel 7")


def m2_payload(s, passed=True, **diag):
    return {"session_id": s["session_id"], "purpose": "AUTH", "nonce": s["qr_payload"]["nonce"],
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_id": "d", "bpm": 72.0 if passed else 0.0, "snr": 6.0 if passed else 1.5,
            "liveness_passed": passed, "frames_used": 290, "app_version": "2.1",
            "diagnostics": {**GOOD, **diag}}


def test_qr_carries_all_gate_settings(client):
    live = client.post("/api/v1/sessions").json()["qr_payload"]["liveness"]
    assert live == {"min_snr_db": 3.0, "window_s": 10.0, "stable_count": 5,
                    "stable_tolerance_bpm": 3.0, "timeout_s": 30.0}


def test_diagnostics_stored_for_pass_and_fail(client, officer_headers):
    phone = Phone(client)
    s1 = client.post("/api/v1/sessions").json()
    assert phone.submit(m2_payload(s1)).json()["status"] == "ACCESS_GRANTED"
    s2 = client.post("/api/v1/sessions").json()
    r = phone.submit(m2_payload(s2, passed=False, best_snr_db=1.9, last_gate="SNR_BELOW_MIN", scan_seconds=30.2))
    assert r.json()["reason_code"] == "NO_PULSE"

    rows = client.get("/api/v1/diagnostics", headers=officer_headers).json()
    assert [x["outcome"] for x in rows] == ["REJECTED", "GRANTED"]
    assert rows[0]["best_snr_db"] == 1.9 and rows[0]["reason_code"] == "NO_PULSE"
    assert rows[1]["avg_fps"] == 29.6 and rows[1]["device_model"] == "Google Pixel 7"
    csv_text = client.get("/api/v1/diagnostics.csv", headers=officer_headers).text
    assert csv_text.splitlines()[0].startswith("id,") and len(csv_text.splitlines()) == 3
    assert client.get("/api/v1/diagnostics").status_code == 401


def test_payload_without_diagnostics_still_works(client):
    phone = Phone(client)
    s = client.post("/api/v1/sessions").json()
    p = m2_payload(s)
    p.pop("diagnostics")
    assert phone.submit(p).json()["status"] == "ACCESS_GRANTED"


def row(**kw):
    base = {**GOOD, "session_id": "abcdefgh1234", "liveness_passed": True}
    base.update(kw)
    return ScanDiagnostic(**base)


def test_diagnosis_distinguishes_camera_light_and_thresholds():
    slow_camera = cal.diagnose([row(avg_fps=14.8)])
    assert any(n.startswith("CAMERA") for n in slow_camera)
    dim = cal.diagnose([row(mean_luma=45)])
    assert any(n.startswith("LIGHTING") for n in dim)
    near_threshold = cal.diagnose([row(liveness_passed=False, best_snr_db=2.6, gate_sec_snr=20, gate_sec_stable=2)])
    assert any(n.startswith("THRESHOLD?") and "Collect photo scans" in n for n in near_threshold)
    weak_signal = cal.diagnose([row(liveness_passed=False, best_snr_db=-1.0, gate_sec_snr=20, gate_sec_stable=2)])
    assert any(n.startswith("SIGNAL") for n in weak_signal)
    tight_tolerance = cal.diagnose([row(liveness_passed=False, best_snr_db=5.0, final_spread_bpm=4.2,
                                        gate_sec_snr=0, gate_sec_stable=20)])
    assert any("tolerance may be tight" in n for n in tight_tolerance)
    assert cal.diagnose([row()]) == ["OK: every scan passed; no change needed."]


def test_scans_report_and_labels(client, officer_headers, capsys):
    phone = Phone(client)
    for passed, snr in ((True, 7.0), (True, 6.1), (False, 1.2)):
        s = client.post("/api/v1/sessions").json()
        phone.submit(m2_payload(s, passed=passed, best_snr_db=snr))
    assert cal.main(["label-scans", "--last", "1", "--as", "photo"]) == 0
    assert cal.main(["label-scans", "--last", "3", "--as", "genuine"]) == 0  # relabels all three
    assert cal.main(["label-scans", "--last", "1", "--as", "photo"]) == 0
    assert cal.main(["scans"]) == 0
    out = capsys.readouterr().out
    assert "Google Pixel 7: 3 scans, 2 stable" in out
    assert "keep MIN_SNR_DB ≥ 1.7" in out
