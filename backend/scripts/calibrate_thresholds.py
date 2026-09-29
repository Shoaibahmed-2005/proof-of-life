"""
Calibrate the face-match thresholds (FACE_T_LOW / FACE_T_HIGH) on OUR scans.

The backend appends every life-certificate face comparison to
data/match_scores.csv. Workflow:

  1. Registered person A submits life certificates 10+ times → label them:
       python scripts/calibrate_thresholds.py label --last 10 --as genuine
  2. Other people (B, C, ...) submit using A's pension ID 10+ times → label:
       python scripts/calibrate_thresholds.py label --last 10 --as impostor
     (or label one attempt: label --session <session_id> --as impostor)
  3. See the distributions and the suggested thresholds:
       python scripts/calibrate_thresholds.py report
  4. Put the suggested values in backend/.env and restart the backend.

Vary lighting, distance, glasses and time of day across the genuine scans,
so the thresholds reflect real conditions rather than one perfect setup.

Scan speed / liveness thresholds (MIN_SNR_DB and the stability gate) use the
per-scan diagnostics every app result carries (stored in the database):

  python scripts/calibrate_thresholds.py scans                      # per-phone report + diagnosis
  python scripts/calibrate_thresholds.py label-scans --last 5 --as genuine   # real person
  python scripts/calibrate_thresholds.py label-scans --last 3 --as photo     # printed photo / screen

With genuine and photo scans labelled, the report shows which MIN_SNR_DB
values would let genuine scans pass while still rejecting every photo.

Run from the backend/ folder.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.score_log import FIELDS  # noqa: E402

MIN_SAMPLES = 10


def default_csv() -> Path:
    return settings.DATA_DIR / "match_scores.csv"


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def suggest_thresholds(genuine: list[float], impostor: list[float], margin: float = 0.02) -> dict:
    """
    T_high: the lowest score that no impostor reached (highest impostor + margin),
            so an impostor like the ones we tested is never auto-approved.
    T_low:  below the weakest genuine scans (lowest genuine − margin), so a
            genuine pensioner is never rejected outright: at worst they go to review.
    If the two distributions overlap, T_low < T_high still holds, and the overlap
    region is sent to officer review.
    """
    g_min, i_max = min(genuine), max(impostor)
    t_high = round(min(0.99, i_max + margin), 3)
    t_low = round(max(0.0, min(g_min - margin, t_high - 0.05)), 3)
    return {
        "t_high": t_high,
        "t_low": t_low,
        "separated": g_min > i_max,
        "genuine_auto_approve_rate": sum(s >= t_high for s in genuine) / len(genuine),
        "impostor_reject_rate": sum(s < t_low for s in impostor) / len(impostor),
    }


def cmd_label(args) -> int:
    path = Path(args.csv)
    rows = load_rows(path)
    if not rows:
        print(f"No scores yet in {path}")
        return 1
    if args.session:
        targets = [r for r in rows if r["session_id"] == args.session]
    else:
        unlabelled = [r for r in rows if not r["label"]]
        targets = unlabelled[-args.last:] if args.last else []
    if not targets:
        print("Nothing matched; use --last N or --session ID")
        return 1
    for r in targets:
        r["label"] = args.label
    save_rows(path, rows)
    print(f"Labelled {len(targets)} attempt(s) as {args.label}:")
    for r in targets:
        print(f"  {r['timestamp']}  pensioner {r['pensioner_id']}  score {r['score']}  ({r['band']})")
    return 0


def _describe(name: str, scores: list[float]) -> None:
    if not scores:
        print(f"  {name:9}: none")
        return
    print(f"  {name:9}: n={len(scores):3}  min={min(scores):.3f}  "
          f"median={statistics.median(scores):.3f}  max={max(scores):.3f}")


def cmd_report(args) -> int:
    rows = load_rows(Path(args.csv))
    genuine = [float(r["score"]) for r in rows if r["label"] == "genuine"]
    impostor = [float(r["score"]) for r in rows if r["label"] == "impostor"]
    unlabelled = sum(1 for r in rows if not r["label"])

    print(f"Scores file: {args.csv}")
    print(f"Current settings: FACE_T_LOW={settings.FACE_T_LOW}  FACE_T_HIGH={settings.FACE_T_HIGH}\n")
    _describe("genuine", genuine)
    _describe("impostor", impostor)
    if unlabelled:
        print(f"  ({unlabelled} unlabelled attempts ignored)")

    if not genuine or not impostor:
        print("\nNeed both genuine and impostor attempts before thresholds can be suggested.")
        return 1

    print("\n  threshold  genuine≥t  impostor≥t")
    for t in [x / 100 for x in range(20, 100, 5)]:
        g = sum(s >= t for s in genuine) / len(genuine)
        i = sum(s >= t for s in impostor) / len(impostor)
        print(f"     {t:.2f}     {g:6.0%}     {i:6.0%}")

    s = suggest_thresholds(genuine, impostor)
    print("\nSuggested (put in backend/.env):")
    print(f"  FACE_T_HIGH={s['t_high']}")
    print(f"  FACE_T_LOW={s['t_low']}")
    print(f"  → genuine auto-approved: {s['genuine_auto_approve_rate']:.0%}, "
          f"impostors rejected outright: {s['impostor_reject_rate']:.0%} (the rest go to review)")
    if not s["separated"]:
        print("  ! Genuine and impostor scores overlap: expect more officer reviews. "
              "Check lighting, face alignment and the model.")
    if len(genuine) < MIN_SAMPLES or len(impostor) < MIN_SAMPLES:
        print(f"  ! Fewer than {MIN_SAMPLES} samples in a group: collect more before the demo.")
    return 0


# ── Scan diagnostics (MIN_SNR_DB / stability gate) ────────────────────

SCAN_LABELS = ("genuine", "photo", "video", "")


def _scan_rows():
    from sqlmodel import Session, select

    from app.db.database import get_engine, init_db
    from app.db.models import ScanDiagnostic
    init_db()
    with Session(get_engine()) as db:
        return list(db.exec(select(ScanDiagnostic).order_by(ScanDiagnostic.id)).all())


def _med(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _f(v, fmt="{:.1f}"):
    return "—" if v is None else fmt.format(v)


def diagnose(rows) -> list[str]:
    """Plain-language reading of one phone's scans: camera, lighting, or thresholds."""
    notes = []
    passes = [r for r in rows if r.liveness_passed]
    fails = [r for r in rows if r.liveness_passed is False]
    fps = _med([r.avg_fps for r in rows])
    luma = _med([r.mean_luma for r in rows])
    if fps is not None and fps < 20:
        notes.append(f"CAMERA: median {fps:.0f} fps (want ~30). The camera/phone delivers too few frames; "
                     "scans are noisier and slower. Check fps_range and try brighter light (some cameras "
                     "drop fps in dim light).")
    if luma is not None and luma < 70:
        notes.append(f"LIGHTING: face brightness {luma:.0f}/255 is dim. Try brighter, even light on the face.")
    if any(r.ae_locked is False for r in rows):
        notes.append("CAMERA: exposure lock not supported on this phone; auto-exposure changes add noise.")
    face = sum(r.gate_sec_face or 0 for r in rows)
    if rows and face / len(rows) > 5:
        notes.append("POSITIONING: the face was often not detected (see gate_sec_face). "
                     "Hold the phone at eye level, 30-40 cm away, face fully visible.")
    for r in fails:
        min_snr = r.min_snr_db if r.min_snr_db is not None else 0
        if (r.gate_sec_snr or 0) > (r.gate_sec_stable or 0) and r.best_snr_db is not None:
            if r.best_snr_db >= min_snr - 1.0:
                notes.append(f"THRESHOLD?: scan {r.session_id[:8]} reached {r.best_snr_db:.1f} dB, just under "
                             f"MIN_SNR_DB {min_snr:.1f}. Collect photo scans before lowering it.")
            else:
                notes.append(f"SIGNAL: scan {r.session_id[:8]} peaked at {r.best_snr_db:.1f} dB, far below "
                             f"{min_snr:.1f}: camera/lighting, not the threshold.")
        elif (r.gate_sec_stable or 0) > 0 and r.final_spread_bpm is not None:
            if r.final_spread_bpm <= 6 and (r.best_snr_db or -99) >= min_snr:
                notes.append(f"THRESHOLD?: scan {r.session_id[:8]} readings spread {r.final_spread_bpm:.1f} BPM "
                             "with good SNR: the ±BPM tolerance may be tight (RPPG_STABLE_TOLERANCE_BPM).")
            else:
                notes.append(f"NOISE: scan {r.session_id[:8]} readings never agreed (spread "
                             f"{r.final_spread_bpm:.1f} BPM): motion, lighting or camera noise.")
    if passes and not fails and not notes:
        notes.append("OK: every scan passed; no change needed.")
    return notes


def cmd_scans(args) -> int:
    rows = _scan_rows()
    if not rows:
        print("No scan diagnostics yet. Scan with the Milestone 2+ app first.")
        return 1
    by_device: dict[str, list] = {}
    for r in rows:
        by_device.setdefault(r.device_model or "unknown", []).append(r)
    print(f"{len(rows)} scans from {len(by_device)} phone(s)\n")
    for device, rs in by_device.items():
        passes = [r for r in rs if r.liveness_passed]
        print(f"== {device}: {len(rs)} scans, {len(passes)} stable ({100 * len(passes) // len(rs)}%)")
        print(f"   time to verify (passes): median {_f(_med([r.scan_seconds for r in passes]))} s   "
              f"fps: median {_f(_med([r.avg_fps for r in rs]))} (min {_f(min((r.min_fps for r in rs if r.min_fps), default=None))})"
              f"   range {rs[-1].fps_range}   AE lock: {sum(1 for r in rs if r.ae_locked)}/{len(rs)}")
        print(f"   best SNR: passes {_f(_med([r.best_snr_db for r in passes]))} dB, "
              f"fails {_f(_med([r.best_snr_db for r in rs if r.liveness_passed is False]))} dB   "
              f"light {_f(_med([r.mean_luma for r in rs]), '{:.0f}')}/255   "
              f"face lost {sum(r.face_lost_count or 0 for r in rs)}x")
        print("   time blocked by gate (median s): window {} · stable {} · snr {} · face {}".format(
            *(_f(_med([getattr(r, g) for r in rs])) for g in
              ("gate_sec_window", "gate_sec_stable", "gate_sec_snr", "gate_sec_face"))))
        for note in diagnose(rs):
            print("   - " + note)
        print()

    genuine = [r.best_snr_db for r in rows if r.label == "genuine" and r.best_snr_db is not None]
    photo = [r.best_snr_db for r in rows if r.label in ("photo", "video") and r.best_snr_db is not None]
    if genuine and photo:
        print("MIN_SNR_DB from labelled scans (best SNR each scan reached):")
        print("  MIN_SNR_DB  genuine would pass  photo/video would pass")
        for t in [x / 2 for x in range(0, 17)]:
            g = sum(v >= t for v in genuine) / len(genuine)
            ph = sum(v >= t for v in photo) / len(photo)
            print(f"     {t:4.1f}          {g:5.0%}               {ph:5.0%}")
        safe = max(photo) + 0.5
        print(f"  Photos/videos peaked at {max(photo):.1f} dB → keep MIN_SNR_DB ≥ {safe:.1f}. "
              f"Genuine scans: min {min(genuine):.1f}, median {statistics.median(genuine):.1f} dB.")
        if min(genuine) < safe:
            print("  ! Some genuine scans are below the safe level: improve lighting/camera rather than lowering it.")
    else:
        print("Label scans (label-scans --as genuine / --as photo) to get a data-based MIN_SNR_DB table.")
    return 0


def cmd_label_scans(args) -> int:
    from sqlmodel import Session, select

    from app.db.database import get_engine, init_db
    from app.db.models import ScanDiagnostic
    init_db()
    with Session(get_engine()) as db:
        stmt = select(ScanDiagnostic).order_by(ScanDiagnostic.id.desc())
        if args.device:
            stmt = stmt.where(ScanDiagnostic.device_model == args.device)
        targets = list(db.exec(stmt.limit(args.last)).all())
        for r in targets:
            r.label = args.label or None
            db.add(r)
        db.commit()
        print(f"Labelled {len(targets)} scan(s) as {args.label or '(none)'}:")
        for r in reversed(targets):
            print(f"  {r.created_at:%H:%M:%S} {r.device_model}  passed={r.liveness_passed}  "
                  f"best_snr={_f(r.best_snr_db)} dB  time={_f(r.scan_seconds)} s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=str(default_csv()), help="Path to match_scores.csv")
    sub = parser.add_subparsers(dest="command", required=True)

    p_label = sub.add_parser("label", help="Label attempts as genuine or impostor")
    p_label.add_argument("--as", dest="label", choices=["genuine", "impostor", ""], required=True)
    group = p_label.add_mutually_exclusive_group(required=True)
    group.add_argument("--last", type=int, help="Label the last N unlabelled attempts")
    group.add_argument("--session", help="Label one attempt by session id")
    p_label.set_defaults(func=cmd_label)

    p_report = sub.add_parser("report", help="Show score distributions and suggested thresholds")
    p_report.set_defaults(func=cmd_report)

    p_scans = sub.add_parser("scans", help="Per-phone scan speed report and diagnosis (camera / light / thresholds)")
    p_scans.set_defaults(func=cmd_scans)

    p_ls = sub.add_parser("label-scans", help="Label the most recent scans (genuine / photo / video)")
    p_ls.add_argument("--as", dest="label", choices=SCAN_LABELS, required=True)
    p_ls.add_argument("--last", type=int, required=True)
    p_ls.add_argument("--device", help="Only scans from this device model")
    p_ls.set_defaults(func=cmd_label_scans)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
