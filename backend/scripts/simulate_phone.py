"""
Phone simulator — a development and rehearsal tool, NOT the real app.

Acts like the Android app after a scan: reads the QR payload shown by the
portal, builds the signed payload and posts it to the backend. It uses a
SOFTWARE key stored in data/sim_keys/ (not Titan M2), and reports
key_security_level=SOFTWARE so the portal shows that honestly.

Use it to exercise the portal and backend without a phone:

  # copy the QR JSON from the portal ("Show QR data" link) or /docs, then:
  python scripts/simulate_phone.py --qr "<qr json>" --person A              # enrollment / genuine
  python scripts/simulate_phone.py --qr "<qr json>" --person B              # impostor
  python scripts/simulate_phone.py --qr "<qr json>" --person A --no-pulse   # photo attack
  python scripts/simulate_phone.py --qr "<qr json>" --person A --challenge-fail  # video attack
  python scripts/simulate_phone.py --qr "<qr json>" --person A --similarity 0.6  # borderline

Each --person gets a fixed synthetic face; each --device a fixed key.
Run from the backend/ folder.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

DIM = 128


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def person_face(person: str) -> list[float]:
    rng = random.Random(f"face:{person}")
    return _unit([rng.gauss(0, 1) for _ in range(DIM)])


def probe_with_similarity(base: list[float], similarity: float, seed: str) -> list[float]:
    rng = random.Random(seed)
    other = [rng.gauss(0, 1) for _ in range(DIM)]
    dot = sum(a * b for a, b in zip(base, other))
    orth = _unit([o - dot * b for o, b in zip(other, base)])
    s = math.sqrt(max(0.0, 1 - similarity ** 2))
    return [similarity * b + s * o for b, o in zip(base, orth)]


def load_key(device: str) -> ec.EllipticCurvePrivateKey:
    key_dir = settings.DATA_DIR / "sim_keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    path = key_dir / f"{device}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return key


def build_request(qr: dict, args) -> dict:
    face = person_face(args.person)
    purpose = qr.get("purpose", "AUTH")
    seed = f"{args.person}:{qr['session_id']}"
    payload = {
        "session_id": qr["session_id"],
        "purpose": purpose,
        "nonce": qr.get("nonce"),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": f"simulator:{args.device}",
        "bpm": args.bpm,
        "snr": 1.0 if args.no_pulse else args.snr,
        "liveness_passed": not args.no_pulse,
        "challenge_id": (qr.get("challenge") or {}).get("id"),
        "challenge_passed": not args.challenge_fail,
        "frames_used": 15,
        "app_version": "simulator",
        "model_version": settings.FACE_MODEL_VERSION,
        "key_security_level": "SOFTWARE",
        "consent": True,
    }
    if purpose == "ENROLLMENT":
        payload["reference_template"] = face
    elif purpose == "LIFE_CERTIFICATE":
        payload["face_embedding"] = probe_with_similarity(face, args.similarity, seed)
    elif args.legacy:  # original app's AUTH payload
        payload = {k: payload[k] for k in ("session_id", "timestamp", "device_id", "bpm")}
        payload.update({"snr": 5.0, "variance": 2.0})
    else:  # Milestone 2 app on an AUTH session: rPPG only
        for k in ("challenge_id", "challenge_passed", "model_version", "key_security_level", "consent"):
            payload.pop(k)

    key = load_key(args.device)
    raw = json.dumps(payload).encode()
    der = key.public_key().public_bytes(serialization.Encoding.DER,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    return {
        "payload": base64.b64encode(raw).decode(),
        "signature": base64.b64encode(key.sign(raw, ec.ECDSA(hashes.SHA256()))).decode(),
        "public_key": base64.b64encode(der).decode(),
    }


def stream_telemetry(base: str, qr: dict, args) -> None:
    """Sends scan progress like the app does, so the portal's live status can be checked."""
    import asyncio
    import websockets

    async def run():
        ws_url = (base.replace("http", "ws", 1) + f"{settings.API_V1_STR}/ws/telemetry/"
                  f"{qr['session_id']}?nonce={qr.get('nonce', '')}")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"type": "scan_started"}))
            steps = 6
            for i in range(1, steps + 1):
                await asyncio.sleep(args.telemetry_interval)
                bpm = args.bpm + (steps - i) * 1.5
                snr = 1.0 if args.no_pulse else args.snr * i / steps
                await ws.send(json.dumps({"type": "measuring", "bpm": bpm, "snr": snr,
                                          "progress": i / steps, "stable": i == steps and not args.no_pulse}))
                await ws.recv()

    try:
        asyncio.run(run())
    except Exception as e:  # telemetry is best effort, like in the app
        print(f"(telemetry skipped: {e})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--qr", required=True, help="QR payload JSON from the portal")
    parser.add_argument("--person", default="A", help="Whose face to present (fixed synthetic face)")
    parser.add_argument("--device", default="pixel-sim", help="Which simulated phone key to sign with")
    parser.add_argument("--similarity", type=float, default=0.92,
                        help="Face similarity to the person's registered face (life certificate)")
    parser.add_argument("--bpm", type=float, default=72.0)
    parser.add_argument("--snr", type=float, default=7.5, help="rPPG SNR in dB")
    parser.add_argument("--no-pulse", action="store_true", help="Simulate a photo (liveness fails)")
    parser.add_argument("--challenge-fail", action="store_true", help="Simulate a video replay")
    parser.add_argument("--base-url", help="Override the backend URL from the QR")
    parser.add_argument("--legacy", action="store_true", help="AUTH: send the original app's payload")
    parser.add_argument("--no-telemetry", action="store_true", help="Don't stream live MEASURING events")
    parser.add_argument("--telemetry-interval", type=float, default=0.8, help="Seconds between live events")
    args = parser.parse_args(argv)

    qr = json.loads(args.qr)
    base = (args.base_url or qr.get("base_url") or "http://localhost:8000").rstrip("/")
    if not args.no_telemetry:
        stream_telemetry(base, qr, args)
    body = json.dumps(build_request(qr, args)).encode()
    req = urllib.request.Request(f"{base}{settings.API_V1_STR}/auth/verify", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(json.dumps(json.loads(resp.read()), indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        return 1
    except urllib.error.URLError as e:
        print(f"Cannot reach {base}: {e.reason}. Try --base-url http://localhost:8000")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
