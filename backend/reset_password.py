#!/usr/bin/env python3
"""
CDTRS User Password Reset Utility
Usage:
    python backend/reset_password.py <username> <new_password>
Example:
    python backend/reset_password.py ds_user MyNewSecretPassword@2026
"""

import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import models
import crud
from database import SessionLocal

def reset_password(username: str, new_password: str):
    if not username or not new_password:
        print("❌ Usage: python backend/reset_password.py <username> <new_password>")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = crud.get_user_by_username(db, username.strip())
        if not user:
            print(f"❌ User '{username}' was not found in the database.")
            users = crud.get_users(db)
            if users:
                print("Available usernames:")
                for u in users:
                    print(f"  - {u.username} ({u.full_name} | Role: {u.role.value if hasattr(u.role, 'value') else u.role})")
            sys.exit(1)

        success = crud.update_user_password(db, user.id, new_password.strip())
        if success:
            print("=" * 60)
            print(f"✅ PASSWORD UPDATED SUCCESSFULLY FOR USER: {user.username}")
            print(f"   Full Name:    {user.full_name}")
            Role_str = user.role.value if hasattr(user.role, 'value') else str(user.role)
            print(f"   Role:         {Role_str}")
            print(f"   New Password: {new_password.strip()}")
            print("=" * 60)
        else:
            print("❌ Failed to update password.")

    except Exception as e:
        print(f"❌ Error updating password: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        # Interactive mode if arguments are omitted
        print("=" * 60)
        print("CDTRS Interactive Password Reset Tool")
        print("=" * 60)
        uname = input("Enter username: ").strip()
        pwd = input("Enter new password: ").strip()
        reset_password(uname, pwd)
    else:
        reset_password(sys.argv[1], sys.argv[2])
