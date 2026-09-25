import os
import sys
import shutil

# Ensure backend folder is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import models
import crud
from database import engine, SessionLocal

def main(reset: bool = False):
    print("=" * 65)
    print("CDTRS Database Setup & Clean Seeding (Finance, HR, Technical)")
    print("=" * 65)

    if reset:
        print("\n1. Dropping existing tables and clearing uploaded documents...")
        models.Base.metadata.drop_all(bind=engine)
        for udir in [os.path.join(BASE_DIR, "uploads"), os.path.join(os.path.dirname(BASE_DIR), "uploads")]:
            if os.path.exists(udir):
                for item in os.listdir(udir):
                    ipath = os.path.join(udir, item)
                    try:
                        if os.path.isdir(ipath):
                            shutil.rmtree(ipath)
                        else:
                            os.unlink(ipath)
                    except Exception:
                        pass

    # 1. Ensure all tables exist in database
    print("\n1. Creating database tables...")
    models.Base.metadata.create_all(bind=engine)
    print("[OK] All database tables ready.")

    # 2. Seed departments, employees, and user accounts
    print("\n2. Seeding departments and accounts from data/seed_data.json...")
    db = SessionLocal()
    try:
        crud.seed_data(db)
        print("[OK] Seed data inserted / verified successfully.")

        # 3. Print list of available accounts
        users = crud.get_users(db)
        print("\n" + "=" * 65)
        print("AVAILABLE LOCAL SYSTEM & EMPLOYEE ACCOUNTS")
        print("=" * 65)
        print(f"{'Username':<18} | {'Role':<18} | {'Default Password'}")
        print("-" * 65)
        
        # Default passwords of the accounts defined in data/seed_data.json.
        import json
        seed_file = os.path.join(BASE_DIR, "data", "seed_data.json")
        passwords = {}
        if os.path.exists(seed_file):
            with open(seed_file, "r", encoding="utf-8") as fh:
                seed = json.load(fh)
            for spec in seed.get("system_users", []) + seed.get("employees", []):
                passwords[spec.get("username")] = spec.get("default_password", "")
        for u in users:
            pwd = passwords.get(u.username) or "(not a seeded account)"
            role_val = u.role.value if hasattr(u.role, "value") else str(u.role)
            print(f"{u.username:<18} | {role_val:<18} | {pwd}")
        print("=" * 65)
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv or "-r" in sys.argv
    main(reset=reset_flag)
