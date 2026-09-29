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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
