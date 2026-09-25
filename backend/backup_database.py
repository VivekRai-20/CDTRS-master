"""
backend/backup_database.py
--------------------------
Back up the CDTRS database and the uploaded documents.

    python backup_database.py                 # backups go to <project>/backups/
    python backup_database.py --dest D:\\cdtrs_backups --keep 30
    (or double-click scripts\\backup_database.bat)

Creates, with the date and time in the name:
    cdtrs_db_YYYYmmdd_HHMM.dump       the whole database (pg_dump custom format)
    cdtrs_uploads_YYYYmmdd_HHMM.zip   backend/uploads (the documents themselves)

Only the newest --keep backups of each kind are kept (default 14).

The database password is read from DATABASE_URL in backend/.env.  pg_dump
comes with PostgreSQL (C:\\Program Files\\PostgreSQL\\<version>\\bin); it is found
automatically.

Restore (replaces the current data - stop the backend first):
    pg_restore --clean --if-exists -h localhost -U postgres -d cdtrs cdtrs_db_YYYYmmdd_HHMM.dump
and unzip the uploads archive into backend/uploads.

Schedule it daily with Windows Task Scheduler: "Create Basic Task" ->
Daily -> Start a program -> scripts\\backup_database.bat.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


def find_pg_dump() -> str | None:
    found = shutil.which("pg_dump")
    if found:
        return found
    patterns = [
        r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe",
        r"C:\Program Files (x86)\PostgreSQL\*\bin\pg_dump.exe",
        "/usr/lib/postgresql/*/bin/pg_dump",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    def version(path: str) -> float:
        try:
            return float(Path(path).parents[1].name)
        except ValueError:
            return 0.0

    return max(candidates, key=version) if candidates else None


def prune(folder: Path, pattern: str, keep: int) -> None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink()
        print(f"  removed old backup {old.name}")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", default=str(PROJECT_DIR / "backups"), help="backup folder")
    parser.add_argument("--keep", type=int, default=14, help="how many backups of each kind to keep")
    parser.add_argument("--no-uploads", action="store_true", help="only back up the database")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL", "")
    parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    if parsed.scheme not in ("postgresql", "postgres") or not parsed.path.strip("/"):
        print(f"DATABASE_URL in backend/.env is not a PostgreSQL address: {url!r}")
        return 1
    pg_dump = find_pg_dump()
    if not pg_dump:
        print("pg_dump was not found. It is installed with PostgreSQL; add its bin folder to PATH.")
        return 1

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    db_file = dest / f"cdtrs_db_{stamp}.dump"
    env = dict(os.environ, PGPASSWORD=unquote(parsed.password or ""))
    command = [pg_dump, "-Fc", "-h", parsed.hostname or "localhost", "-p", str(parsed.port or 5432),
               "-U", unquote(parsed.username or "postgres"), "-f", str(db_file), parsed.path.strip("/")]
    print(f"Backing up database '{parsed.path.strip('/')}' ...")
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pg_dump failed:\n{result.stderr.strip()}")
        if db_file.exists():
            db_file.unlink()
        return 1
    print(f"  {db_file}  ({db_file.stat().st_size / 1e6:.1f} MB)")

    if not args.no_uploads:
        uploads = Path(os.getenv("UPLOAD_DIR", "./uploads"))
        uploads = uploads if uploads.is_absolute() else BACKEND_DIR / uploads
        if uploads.is_dir():
            print(f"Backing up uploaded documents from {uploads} ...")
            archive = shutil.make_archive(str(dest / f"cdtrs_uploads_{stamp}"), "zip", root_dir=str(uploads))
            print(f"  {archive}  ({Path(archive).stat().st_size / 1e6:.1f} MB)")

    prune(dest, "cdtrs_db_*.dump", args.keep)
    prune(dest, "cdtrs_uploads_*.zip", args.keep)
    print("Backup finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
