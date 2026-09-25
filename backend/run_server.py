"""
backend/run_server.py
---------------------
Start the CDTRS backend with the settings in backend/.env:

    HOST=0.0.0.0     # 0.0.0.0 = reachable from other PCs on the LAN; 127.0.0.1 = this PC only
    PORT=8000

From the backend folder:   python run_server.py
(or double-click start_backend.bat in the project folder)

Options override .env:     python run_server.py --port 8123 --host 127.0.0.1
Test server (no mail):      python run_server.py --port 8123 --host 127.0.0.1 --no-mail
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> None:
    # Relative paths in .env (UPLOAD_DIR=./uploads, ...) are relative to backend/.
    os.chdir(BACKEND_DIR)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")

    parser = argparse.ArgumentParser(description="Start the CDTRS backend.")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "info"))
    parser.add_argument("--no-mail", action="store_true",
                        help="no mailbox sync and no e-mails (MAIL_CHANNEL=off) - for test servers")
    args = parser.parse_args()
    if args.no_mail:
        os.environ["MAIL_CHANNEL"] = "off"

    import uvicorn

    shown = "this PC's IP address" if args.host in ("0.0.0.0", "::") else args.host
    print(f"CDTRS backend starting on {args.host}:{args.port}")
    print(f"  Clients connect to  http://{shown}:{args.port}/api/v1  (frontend/.env CDTRS_API_URL)")
    print("  Press Ctrl+C to stop.\n", flush=True)
    # No auto-reload: it would start a second process and load the OCR models twice.
    uvicorn.run("main:app", host=args.host, port=args.port, log_level=args.log_level,
                ws_ping_interval=20, ws_ping_timeout=60)


if __name__ == "__main__":
    main()
