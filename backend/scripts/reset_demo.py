"""
Reset the backend to a clean state for rehearsing the demo.

Moves the current database and score log into data/backups/<timestamp>/
(nothing is deleted, so a mistaken reset can be undone by moving them back).
Keeps data/template.key and the simulator keys.

  python scripts/reset_demo.py            # show what would happen
  python scripts/reset_demo.py --yes      # reset (empty database + demo officer)
  python scripts/reset_demo.py --yes --seed   # reset and add the fictional demo pensioners

Stop the backend first (Windows keeps the database file locked while it runs).
Run from the backend/ folder.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

DB_SUFFIXES = ("", "-wal", "-shm")


def files_to_move() -> list[Path]:
    files = []
    url = settings.database_url
    if url.startswith("sqlite:///"):
        db = Path(url.removeprefix("sqlite:///"))
        files += [Path(f"{db}{s}") for s in DB_SUFFIXES]
    files.append(settings.DATA_DIR / "match_scores.csv")
    return [f for f in files if f.exists()]


def reset(confirm: bool, seed: bool) -> int:
    if not settings.database_url.startswith("sqlite:///"):
        print(f"Refusing to reset a non-SQLite database: {settings.database_url}")
        return 1
    files = files_to_move()
    backup = settings.DATA_DIR / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    print("Files to move:" if files else "No database or score log found (already clean).")
    for f in files:
        print(f"  {f}")
    if not confirm:
        print(f"\nDry run. Re-run with --yes to move them to {backup}")
        return 0

    if files:
        backup.mkdir(parents=True, exist_ok=True)
        for f in files:
            try:
                shutil.move(str(f), backup / f.name)
            except PermissionError:
                print(f"Cannot move {f}: it is in use. Stop the backend (uvicorn) and try again.")
                return 1
        print(f"Moved {len(files)} file(s) to {backup}")

    from app.db.database import init_db
    from app.main import seed_demo_officer
    init_db()
    seed_demo_officer()
    print(f"Fresh database ready. Officer login: {settings.DEMO_OFFICER_USERNAME} / (password from .env)")
    if seed:
        from scripts.seed_demo import seed as seed_pensioners
        seed_pensioners()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Actually reset (otherwise a dry run)")
    parser.add_argument("--seed", action="store_true", help="Add the fictional demo pensioners")
    args = parser.parse_args()
    raise SystemExit(reset(args.yes, args.seed))
