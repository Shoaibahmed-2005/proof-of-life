"""
Start the backend so phones on the same Wi-Fi can reach it.

    python run.py            (from backend/, with the venv active)

Always listens on 0.0.0.0 (every network adapter). Plain
`uvicorn app.main:app` listens on 127.0.0.1 only, which works over USB
(`adb reverse`) but NOT over Wi-Fi: that was a common cause of
"other phones can't connect".

Options: --port 8000 (or PORT in the environment), --reload for development.
"""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # Work from backend/ wherever this is started from (imports, .env, data/).
    backend_dir = Path(__file__).resolve().parent
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    os.environ["JS_BIND_HOST"] = "0.0.0.0"
    os.environ["JS_BIND_PORT"] = str(args.port)
    uvicorn.run("app.main:app", host="0.0.0.0", port=args.port, reload=args.reload)
