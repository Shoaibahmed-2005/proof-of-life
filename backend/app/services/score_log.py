"""
Face-match score log for threshold calibration (build-prompt §5.3).

Every LIFE_CERTIFICATE face comparison is appended to DATA_DIR/match_scores.csv.
Label rows as genuine / impostor with scripts/calibrate_thresholds.py, then run
its `report` command to choose FACE_T_LOW / FACE_T_HIGH.
No personal data: pensioner ids and scores only.
"""

from __future__ import annotations

import csv
import threading

from app.core.config import settings
from app.db.types import utcnow

FIELDS = ["timestamp", "session_id", "pensioner_id", "score", "anchor_score",
          "band", "model_version", "label"]
_lock = threading.Lock()


def forget_pensioner(pensioner_id: int) -> int:
    """Blanks the pensioner id on this pensioner's score rows (scores stay for calibration)."""
    path = settings.DATA_DIR / "match_scores.csv"
    with _lock:
        if not path.exists():
            return 0
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        changed = 0
        for r in rows:
            if r.get("pensioner_id") == str(pensioner_id):
                r["pensioner_id"] = ""
                changed += 1
        if changed:
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        return changed


def log_score(session_id: str, pensioner_id: int, score: float, anchor_score: float,
              band: str, model_version: str) -> None:
    if not settings.SCORE_LOG_ENABLED:
        return
    path = settings.DATA_DIR / "match_scores.csv"
    with _lock:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "timestamp": utcnow().isoformat(timespec="seconds"),
                "session_id": session_id,
                "pensioner_id": pensioner_id,
                "score": f"{score:.4f}",
                "anchor_score": f"{anchor_score:.4f}",
                "band": band,
                "model_version": model_version,
                "label": "",
            })
