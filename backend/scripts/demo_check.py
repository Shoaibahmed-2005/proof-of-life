"""
Demo check: runs the five demo scenarios (build-prompt §3.3) against a RUNNING
backend, the way the portal and the phone do, and checks every outcome.

It uses the phone simulator (software key, key_security_level=SOFTWARE), so it
tests the backend + portal path end to end, not the phone's camera. A fresh
pensioner ("Demo Check <time>") and a fresh simulated device are used on each
run, so it never touches the real demo pensioners.

  cd backend
  python run.py                                   # in another terminal
  python scripts/demo_check.py                    # add --slow to watch it on the portal

Open the portal's Records / Review Queue / Treasury / Audit Ledger pages while
it runs to see the live updates. Exit code 0 = all scenarios behaved as expected.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_spec = importlib.util.spec_from_file_location("simulate_phone", HERE / "simulate_phone.py")
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)  # type: ignore[union-attr]

from app.core.config import settings  # noqa: E402

API = settings.API_V1_STR


class Check:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def expect(self, label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail and not ok else ''}")
        if not ok:
            self.failures.append(label)


def phone(client: httpx.Client, qr: dict, telemetry_interval: float, **kw) -> dict:
    """What the phone does after scanning `qr`: live telemetry, then the signed result."""
    args = argparse.Namespace(person="A", device="demo-check", similarity=0.92, bpm=72.0, snr=7.5,
                              no_pulse=False, challenge_fail=False, multiple_faces=False, legacy=False,
                              telemetry_interval=telemetry_interval)
    for k, v in kw.items():
        setattr(args, k, v)
    sim.stream_telemetry(str(client.base_url).rstrip("/"), qr, args)
    return client.post(f"{API}/auth/verify", json=sim.build_request(qr, args)).json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default="officer")
    parser.add_argument("--password", default="officer123")
    parser.add_argument("--slow", action="store_true", help="Pause between scenarios and stream slower")
    args = parser.parse_args(argv)
    pause = 3.0 if args.slow else 0.0
    interval = 0.8 if args.slow else 0.05
    c = Check()
    stamp = time.strftime("%H%M%S")
    device = f"demo-check-{stamp}"

    with httpx.Client(base_url=args.base_url, timeout=20) as client:
        try:
            client.get(f"{API}/health").raise_for_status()
        except httpx.HTTPError as e:
            print(f"Backend not reachable at {args.base_url}: {e}\nStart it with: python run.py")
            return 2
        token = client.post(f"{API}/officers/login",
                            json={"username": args.username, "password": args.password}).json()["access_token"]
        officer = {"Authorization": f"Bearer {token}"}

        def life_certificate(ppo: str, **kw) -> dict:
            s = client.post(f"{API}/sessions", json={"purpose": "LIFE_CERTIFICATE", "ppo_number": ppo,
                                                     "consent": True}).json()
            return phone(client, s["qr_payload"], interval, device=device, **kw)

        def status_of(ppo: str) -> str:
            return client.get(f"{API}/pensioners/lookup", params={"ppo_number": ppo}).json()["status"]

        # S1: officer registers A; A scans; officer approves.
        print("S1  Register A (officer-assisted)")
        ppo = f"PPO-CHK-{stamp}"
        p = client.post(f"{API}/pensioners", headers=officer, json={
            "name": f"Demo Check {stamp}", "ppo_number": ppo, "service_number": f"JC-{stamp}",
            "bank_last4": "0000", "monthly_pension_amount": 30000}).json()
        s = client.post(f"{API}/sessions", headers=officer,
                        json={"purpose": "ENROLLMENT", "pensioner_id": p["id"]}).json()
        c.expect("QR carries base URL, nonce and a random challenge",
                 all(k in s["qr_payload"] for k in ("base_url", "nonce", "challenge")))
        r = phone(client, s["qr_payload"], interval, device=device)
        c.expect("phone result: face registered (CAPTURED)", r.get("outcome") == "CAPTURED", str(r))
        r = client.post(f"{API}/enroll/complete", headers=officer, json={"pensioner_id": p["id"]})
        c.expect("officer approval", r.status_code == 200, r.text[:200])
        c.expect("A is Active", status_of(ppo) == "ACTIVE")
        time.sleep(pause)

        print("S2  A submits a life certificate")
        r = life_certificate(ppo, person="A")
        c.expect("certificate issued", r.get("outcome") == "ISSUED", str(r))
        time.sleep(pause)

        print("S3  B pretends to be A (same phone)")
        r = life_certificate(ppo, person="B")
        c.expect("rejected: face does not match", r.get("reason_code") == "FACE_MISMATCH", str(r))
        time.sleep(pause)

        print("S4  Photo of A (no pulse)")
        r = life_certificate(ppo, person="A", no_pulse=True)
        c.expect("rejected: no pulse", r.get("reason_code") == "NO_PULSE", str(r))
        time.sleep(pause)

        print("S5  Video of A (can't follow the random challenge)")
        r = life_certificate(ppo, person="A", challenge_fail=True)
        c.expect("rejected: challenge failed", r.get("reason_code") == "CHALLENGE_FAILED", str(r))
        c.expect(f"A is Frozen after {settings.MAX_FAILED_ATTEMPTS} failed attempts", status_of(ppo) == "FROZEN")
        time.sleep(pause)

        print("Finale  officer restores A; ledger and treasury")
        frozen = client.get(f"{API}/reviews/frozen", headers=officer).json()
        c.expect("A is in Review Queue > Frozen pensions", any(f["pensioner"]["id"] == p["id"] for f in frozen))
        r = client.post(f"{API}/reviews/frozen/{p['id']}/restore", headers=officer,
                        json={"reason": "Demo check: attacks explained, pensioner verified in person"})
        c.expect("officer restore", r.status_code == 200 and status_of(ppo) == "ACTIVE", r.text[:200])
        v = client.get(f"{API}/ledger/verify").json()
        c.expect("audit ledger chain verifies", v.get("valid") is True, v.get("message", ""))
        t = client.get(f"{API}/treasury/summary", headers=officer)
        c.expect("treasury summary loads", t.status_code == 200, t.text[:200])

        print("Extra  someone else in view (app aborts with MULTIPLE_FACES)")
        r = life_certificate(ppo, person="A", multiple_faces=True)
        c.expect("rejected: more than one face, not counted", r.get("reason_code") == "MULTIPLE_FACES"
                 and status_of(ppo) == "ACTIVE", str(r))

    print()
    if c.failures:
        print(f"{len(c.failures)} check(s) FAILED: " + "; ".join(c.failures))
        return 1
    print(f"All checks passed. Test pensioner: {ppo} (Records page).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
