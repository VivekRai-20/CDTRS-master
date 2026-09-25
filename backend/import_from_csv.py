"""
backend/import_from_csv.py
--------------------------
Bulk-load your real departments and user accounts from spreadsheets.

1. Copy departments.csv and accounts.csv from backend/data/import_templates/
   into backend/data/import/ and fill them in with Excel (the *_example.csv
   files show filled-in rows):

       departments.csv   name, code, description, keywords
       accounts.csv      username, full_name, role, department, designation,
                         employee_code, email, outlook_email, gov_email,
                         password, contexts

   Save as "CSV UTF-8".  .xlsx files with the same columns also work.

2. Check them (nothing is written), from the backend folder:

       python import_from_csv.py --check

3. Import (backend/.env must point at the database):

       python import_from_csv.py

   Another folder:  python import_from_csv.py D:\\staff_lists --check

Running it again is safe: existing departments and accounts are updated from
the files (never duplicated), listed contexts are switched on again, and
existing passwords are never changed.  The import is all-or-nothing: if
anything fails, nothing is saved.  Department codes and names may be written
in any case.

Column details
  role        ADMIN, DS, DIRECTOR, TSO, HOD or EMPLOYEE (the account's main role)
  department  department code or name (must be in departments.csv or already exist)
  password    first password for NEW accounts (default cdtrs@123); users should
              change it after the first login
  contexts    optional - the "hats" the user can switch between, separated by ";"
              e.g.  EMPLOYEE:ENG; HOD:ENG; HOD:QA
              Without it: EMPLOYEE / HOD get their own department, the others
              get their role.  Only one TSO exists organisation-wide.
  keywords    comma-separated words that route documents to the department
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

ROLES = {"ADMIN", "DS", "DIRECTOR", "TSO", "HOD", "EMPLOYEE"}
TEMPLATES_DIR = BASE_DIR / "data" / "import_templates"
IMPORT_DIR = BASE_DIR / "data" / "import"


def _norm_key(key: str) -> str:
    return str(key or "").strip().lower().replace(" ", "_")


def read_table(path: Path) -> list[dict[str, str]]:
    """Rows of a .csv (UTF-8, with or without BOM) or .xlsx file, keys normalised."""
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return []
        headers = [_norm_key(h) for h in rows[0]]
        out = []
        for values in rows[1:]:
            if not any(v not in (None, "") for v in values):
                continue
            out.append({h: ("" if v is None else str(v)).strip() for h, v in zip(headers, values) if h})
        return out
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [
            {_norm_key(k): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(fh)
            if any((v or "").strip() for v in row.values())
        ]


def _find(folder: Path, stem: str) -> Path | None:
    for ext in (".csv", ".xlsx"):
        candidate = folder / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def build_payload(folder: Path, existing_departments: list[tuple[str, str]] = (),
                  existing_emails: dict[str, str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """seed_data.json-shaped payload plus a list of problems found.

    existing_departments: (name, code) of the departments in the database.
    existing_emails: e-mail (lower case) -> username (lower case) of existing accounts."""
    problems: list[str] = []
    payload: dict[str, Any] = {"departments": [], "system_users": [], "employees": []}
    existing_emails = existing_emails or {}
    known = {v.lower() for pair in existing_departments for v in pair if v}
    code_owner = {code.lower(): name for name, code in existing_departments if code}
    names_in_db = {name.lower() for name, _ in existing_departments}

    dept_file = _find(folder, "departments")
    if dept_file:
        seen_codes: set[str] = set()
        for n, row in enumerate(read_table(dept_file), start=2):
            name, code = row.get("name", ""), row.get("code", "").upper()
            if not name:
                problems.append(f"{dept_file.name} line {n}: name is empty")
                continue
            if code and code in seen_codes:
                problems.append(f"{dept_file.name} line {n}: code {code} is used twice")
            owner = code_owner.get(code.lower()) if code else None
            if owner and owner.lower() != name.lower() and name.lower() not in names_in_db:
                problems.append(f"{dept_file.name} line {n}: code {code} already belongs to department '{owner}'")
            seen_codes.add(code)
            payload["departments"].append({
                "name": name, "code": code or None,
                "description": row.get("description") or None,
                "keywords": row.get("keywords") or None,
            })
            known.update({name.lower(), code.lower()})

    acc_file = _find(folder, "accounts")
    if acc_file:
        seen_users: set[str] = set()
        seen_emails: dict[str, str] = {}
        seen_codes_emp: set[str] = set()
        for n, row in enumerate(read_table(acc_file), start=2):
            where = f"{acc_file.name} line {n}"
            username = row.get("username", "")
            role = row.get("role", "EMPLOYEE").upper() or "EMPLOYEE"
            department = row.get("department", "")
            if not username:
                problems.append(f"{where}: username is empty")
                continue
            if username.lower() in seen_users:
                problems.append(f"{where}: username {username} is used twice")
            seen_users.add(username.lower())
            if role not in ROLES:
                problems.append(f"{where}: role '{role}' must be one of {', '.join(sorted(ROLES))}")
                continue
            email = (row.get("email") or "").lower()
            if email:
                if email in seen_emails:
                    problems.append(f"{where}: e-mail {email} is also used by {seen_emails[email]}")
                elif existing_emails.get(email, username.lower()) != username.lower():
                    problems.append(f"{where}: e-mail {email} already belongs to account "
                                    f"'{existing_emails[email]}'")
                seen_emails[email] = username
            emp_code = (row.get("employee_code") or "").lower()
            if emp_code:
                if emp_code in seen_codes_emp:
                    problems.append(f"{where}: employee_code {row['employee_code']} is used twice")
                seen_codes_emp.add(emp_code)
            if department and department.lower() not in known:
                problems.append(f"{where}: department '{department}' is not in departments.csv or the database")
            if role in ("EMPLOYEE", "HOD") and not department:
                problems.append(f"{where}: {role} accounts need a department")
            contexts = []
            for part in (row.get("contexts") or "").replace(",", ";").split(";"):
                part = part.strip()
                if not part:
                    continue
                ctype, _, dept = part.partition(":")
                ctype, dept = ctype.strip().upper(), dept.strip()
                if ctype not in ROLES:
                    problems.append(f"{where}: context '{part}' - '{ctype}' is not a role")
                    continue
                if dept and dept.lower() not in known:
                    problems.append(f"{where}: context '{part}' - unknown department '{dept}'")
                entry: dict[str, Any] = {"context": ctype}
                if dept:
                    entry["department_code"] = dept
                elif ctype in ("EMPLOYEE", "HOD"):
                    entry["from_user_department"] = True
                contexts.append(entry)
            spec = {
                "username": username,
                "full_name": row.get("full_name") or username,
                "role": role,
                "department": department or None,
                "designation": row.get("designation") or "Staff",
                "employee_code": row.get("employee_code") or None,
                "email": row.get("email") or None,
                "outlook_email": row.get("outlook_email") or None,
                "gov_email": row.get("gov_email") or None,
                "default_password": row.get("password") or "cdtrs@123",
            }
            if contexts:
                spec["contexts"] = contexts
            if role == "EMPLOYEE" and spec["employee_code"]:
                payload["employees"].append(spec)
            else:
                payload["system_users"].append(spec)
                if role == "EMPLOYEE":
                    problems.append(f"{where}: EMPLOYEE without employee_code - "
                                    "added as an account only (no staff-directory record)")

    if not dept_file and not acc_file:
        problems.append(f"No departments.csv / accounts.csv (or .xlsx) in {folder} - copy the templates "
                        f"from {TEMPLATES_DIR} there and fill them in")
    return payload, problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=str(IMPORT_DIR),
                        help="folder with departments.csv and/or accounts.csv")
    parser.add_argument("--check", action="store_true", help="only check the files; change nothing")
    args = parser.parse_args()
    folder = Path(args.folder).resolve()

    import crud
    import models
    from database import SessionLocal, engine

    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        departments = [(d.name, d.code or "") for d in db.query(models.Department).all()]
        emails = {u.email.lower(): u.username.lower() for u in db.query(models.User).all() if u.email}
        payload, problems = build_payload(folder, departments, emails)
        print(f"Read {len(payload['departments'])} department(s), "
              f"{len(payload['system_users']) + len(payload['employees'])} account(s) from {folder}")
        blocking = [p for p in problems if "no staff-directory record" not in p]
        for p in problems:
            print(("  ERROR   " if p in blocking else "  NOTE    ") + p)
        if blocking:
            print("\nNothing was imported. Fix the errors above and run again.")
            sys.exit(1)
        if args.check:
            print("\nThe files look fine. Run again without --check to import them.")
            return
        try:
            crud.apply_seed_payload(db, payload, update_existing=True)
        except Exception as exc:
            print(f"\nImport failed - nothing was saved:\n  {exc}")
            sys.exit(1)
        print("\nImport finished.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
