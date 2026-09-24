"""Drop and rebuild the CDTRS schema, then seed departments, accounts and
work contexts from data/seed_data.json.

    python reset_db.py --confirm            rebuild schema + seed
    python reset_db.py --confirm --wipe-uploads   also clear stored files

Destructive.  Refuses to run without --confirm.
"""

import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import text

import crud
import models
from database import SessionLocal, engine


def drop_everything() -> None:
    """Remove every table and enum type, including ones left behind by earlier
    schema versions that the current metadata no longer knows about."""
    if engine.dialect.name != "postgresql":
        models.Base.metadata.drop_all(bind=engine)
        return
    # Recreating the schema also drops the old enum types, which matters
    # because several enums changed shape in this redesign.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def wipe_uploads() -> None:
    for candidate in (BASE_DIR / "uploads", BASE_DIR.parent / "uploads"):
        if not candidate.exists():
            continue
        for item in candidate.iterdir():
            try:
                shutil.rmtree(item) if item.is_dir() else item.unlink()
            except OSError as exc:
                print(f"  [skip] {item}: {exc}")
        print(f"  cleared {candidate}")


def main() -> None:
    if "--confirm" not in sys.argv:
        print(__doc__)
        print("Refusing to run: pass --confirm to proceed.")
        sys.exit(1)

    print("=" * 66)
    print("CDTRS - full database reset")
    print("=" * 66)

    print("\n[1/4] Dropping existing tables and enum types...")
    drop_everything()
    print("      done.")

    if "--wipe-uploads" in sys.argv:
        print("\n[1b] Clearing uploaded files...")
        wipe_uploads()

    print("\n[2/4] Creating schema...")
    models.Base.metadata.create_all(bind=engine)
    print(f"      {len(models.Base.metadata.tables)} tables created.")

    print("\n[3/4] Seeding departments, accounts and work contexts...")
    db = SessionLocal()
    try:
        crud.seed_data(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n[4/4] Accounts:")
    db = SessionLocal()
    try:
        print(f"      {'Username':<16} {'Role':<10} {'Work contexts'}")
        print("      " + "-" * 62)
        for user in crud.get_users(db):
            contexts = ", ".join(c.label for c in crud.get_user_context_memberships(db, user.id))
            print(f"      {user.username:<16} {user.role.value:<10} {contexts}")
    finally:
        db.close()

    print("\nReset complete.")
    print("=" * 66)


if __name__ == "__main__":
    main()
