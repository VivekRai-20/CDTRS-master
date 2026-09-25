# CDTRS: Centralised Document Tracking and Routing System

CDTRS records every official document that reaches the office (letters, notes,
circulars, e-mails with attachments) and routes it to the right people. It tracks
each person's work on the document until the Director's Secretary (DS) closes it.

- **Intake:** the DS registers documents by uploading a scan or PDF, or by syncing
  the DS mailbox (Outlook or the office mail server).
- **OCR:** an offline engine reads each document, including handwriting. It finds
  the Director's handwritten instructions and suggests the departments that should
  handle it. Nothing leaves the PC.
- **Routing:** the DS first sends the document to the Director for review. With the
  Director's remark, the DS then routes it to one or more departments, HODs,
  employees or the TSO. This order is skipped only when the DS has verified that the
  paper already carries the Director's instruction. Each workstream moves through
  its own stages.
- **Work tracking:** every person has their own work item, with free-text progress,
  attachments, HOD review, deadlines, reminders and notifications (in the app and by
  e-mail).
- **Work contexts:** one account can hold several roles, such as Employee in one
  department and HOD of another. The user switches between them.

```
 Desktop app (PySide6)  ──HTTP/WebSocket──►  Backend (FastAPI)  ──►  PostgreSQL
   frontend\  +  main.py                     backend\                database "cdtrs"
                                               │
                                               └──►  OCR engine (OCR_new\, offline)
                                                     PaddleOCR + TrOCR handwriting
```

---

## Requirements

| | |
|---|---|
| Operating system | Windows 10/11 (64-bit) |
| Python | 3.12 (64-bit) |
| Python packages | Exactly the versions in `imp.txt` (the installed package list, in the project folder); `requirements.txt` pins them. **No other packages are used.** |
| Database | PostgreSQL (the server PC runs PostgreSQL 18) |
| Memory | 8 GB minimum on the server (the OCR uses up to about 3 GB per page) |
| Internet | Not needed to run CDTRS. It is needed only once, to download the handwriting model, and for Outlook mail if you use it |

All packages are installed already on the server PC. On a new PC:

```
py -3.12 -m pip install -r requirements.txt
```

Client PCs that only run the desktop app need just `frontend\requirements.txt`.

---

## Quick start (server PC)

The project folder is `C:\CDTRS-main`.

**1. Create the database** (once). Use pgAdmin, or run this in a Command Prompt:

```
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE cdtrs;"
```

**2. Backend settings** (once). Copy `backend\.env.example` to `backend\.env`, then set:

- `DATABASE_URL`: `postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs`
- `SECRET_KEY`: a long random value. Generate one with:

  ```
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

- `HOST`: `0.0.0.0` so other PCs can connect, or `127.0.0.1` for this PC only
- `PORT`: `8000`

**3. Start the backend.** Double-click **`start_backend.bat`** and keep the window
open. On the first start it creates the tables and the demo departments and accounts.
It then loads the OCR engine in the background, which takes 20–60 seconds. To check
it is running, open http://127.0.0.1:8000/health.

**4. Desktop app settings** (once per PC). Copy `frontend\.env.example` to
`frontend\.env`. Set `CDTRS_API_URL`:

- On the server itself: `http://127.0.0.1:8000/api/v1`
- On other PCs: `http://<server-ip>:8000/api/v1`

**5. Start the app.** Double-click **`start_frontend.bat`** and log in.

| Username | Password | Role(s) |
|---|---|---|
| `exec_user` | `cdtrs@ds` | DS (Director's Secretary) |
| `director` | `cdtrs@director` | Director |
| `hod_eng` | `cdtrs@hod` | HOD Engineering & Innovation, HOD Customer Experience |
| `emp_rahul` | `cdtrs@emp` | Employee Engineering, HOD Product Strategy |
| `tso_user` | `cdtrs@tso` | TSO, Employee Engineering |
| `corp` | `cdtrs@admin` | Administrator |

These are **demo accounts**. Before real use, follow
[DATA_MANAGEMENT_GUIDE.md](DATA_MANAGEMENT_GUIDE.md): import your real departments and
staff, and remove the demo data. [ARCHITECTURE.md](ARCHITECTURE.md) lists all 17 demo
accounts.

**6. Handwriting model** (once, optional but recommended). This needs internet and
downloads about 250 MB:

```
cd /d C:\CDTRS-main\OCR_new
python fineTune\download_base_model.py
```

Restart the backend afterwards. Without this model, handwriting is read by PaddleOCR
only. The printed-text OCR models are already in the project.

---

## Configuration

| File | What it holds | Template |
|---|---|---|
| `backend\.env` | Database, host/port, security key, upload folder, CORS, mail | `backend\.env.example` |
| `frontend\.env` | Address of the backend, request timeout | `frontend\.env.example` |
| `OCR_new\config\config.yaml` | OCR settings: memory limits, handwriting, text-type detection, NER | – |

There is no project-wide `.env`. The `.env` files contain passwords and are never
committed to git.

---

## Everyday operation

| Task | How |
|---|---|
| Start / stop the server | `start_backend.bat` / close its window |
| Start the app | `start_frontend.bat` |
| Back up the database and the uploaded files | `scripts\backup_database.bat` (schedule it daily; see [DATA_MANAGEMENT_GUIDE.md](DATA_MANAGEMENT_GUIDE.md)) |
| Import departments and staff from Excel/CSV | `cd backend` then `python import_from_csv.py --check`, then `python import_from_csv.py` |
| Department routing words | Admin → Department Configuration → *Description* and *Routing keywords* |
| Reset a password | Admin → User Configuration, or `python backend\reset_password.py <user> <new password>` |
| Improve handwriting reading | [OCR_new/fineTune/README.md](OCR_new/fineTune/README.md) |

Duplicate protection: if you upload a file that is already registered, the upload is
refused and the existing document is named. Stored files are never overwritten.

---

## Using CDTRS over the office network

1. On the server, set `HOST=0.0.0.0` in `backend\.env`.
2. Allow the port through Windows Firewall. Run this in an **Administrator** Command
   Prompt:

   ```
   netsh advfirewall firewall add rule name="CDTRS backend" dir=in action=allow protocol=TCP localport=8000
   ```

3. Find the server's IP address with `ipconfig`.
4. On each client PC, set `CDTRS_API_URL=http://<server-ip>:8000/api/v1` in
   `frontend\.env`.

For details and for testing the office mail server, see
[Intranet_testing.md](Intranet_testing.md).

## Mail integration

Set `MAIL_CHANNEL` in `backend\.env` to `outlook` (Microsoft 365 / Outlook.com via
Microsoft Graph) or `intranet` (office IMAP/SMTP server). The DS mailbox is synced
every 30 seconds, or at once with *Sync Now* in the DS Inbox. Notification e-mails go out
through the same channel. See [OUTLOOK_INTEGRATION_GUIDE.md](OUTLOOK_INTEGRATION_GUIDE.md)
and [Intranet_testing.md](Intranet_testing.md). Without mail settings, CDTRS works
normally with manual uploads and in-app notifications.

---

## Tests

No test framework needs installing. The tests use Python's own `unittest` or plain
scripts.

**OCR engine** (no database needed):

```
cd /d C:\CDTRS-main\OCR_new
python -m unittest discover -s testing -t . -v
```

**Backend and app.** These tests log in with the demo accounts and create test
documents, so run them against a **separate test database**, never the live one.

1. Create the test database once:

   ```
   "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE cdtrs_test;"
   ```

2. Start a test backend on port 8123. `--no-mail` stops it from syncing the real
   DS mailbox. It is seeded with the demo accounts from `backend\data\seed_data.json`.
   If you have replaced that file with your real data, see section 2.7 of
   [DATA_MANAGEMENT_GUIDE.md](DATA_MANAGEMENT_GUIDE.md).

   ```
   cd /d C:\CDTRS-main\backend
   set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
   set UPLOAD_DIR=./uploads_test
   python run_server.py --port 8123 --host 127.0.0.1 --no-mail
   ```

3. In another window, point the workflow test at the same database and upload
   folder, then run everything:

   ```
   cd /d C:\CDTRS-main\backend
   set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
   set UPLOAD_DIR=./uploads_test
   python tests\test_full_workflow.py
   python tests\test_api_workflow.py
   python tests\test_context_audit.py
   cd /d C:\CDTRS-main\frontend
   python tests\test_ui_smoke.py
   ```

---

## Project layout

```
C:\CDTRS-main\
├── start_backend.bat / start_frontend.bat   double-click launchers
├── main.py                  desktop app entry point
├── requirements.txt         all pinned packages (= imp.txt versions)
├── scripts\                 find_python.bat, backup_database.bat
├── backend\                 FastAPI server - see backend\readme.md
│   ├── main.py, workflow.py, crud.py, models.py, intelligence.py, ocr_adapter.py, mail\
│   ├── run_server.py, import_from_csv.py, backup_database.py, reset_db.py, ...
│   ├── data\seed_data.json, data\import_templates\
│   └── uploads\             stored documents (not in git)
├── frontend\                PySide6 desktop app (pages, components, services, repositories)
├── OCR_new\                 offline OCR engine - see OCR_new\README.md
│   ├── models\              PaddleOCR (in git), embeddings (in git), handwriting (downloaded)
│   └── fineTune\            teach it your handwriting - see OCR_new\fineTune\README.md
└── backups\                 created by the backup script (not in git)
```

## Documentation

| Document | For |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How documents, branches, work items and work contexts fit together; rules the code enforces |
| [backend/readme.md](backend/readme.md) | Backend setup, settings, database tables, full API list |
| [DATA_MANAGEMENT_GUIDE.md](DATA_MANAGEMENT_GUIDE.md) | Moving from demo to real data, CSV import, routing keywords, backups |
| [Intranet_testing.md](Intranet_testing.md) | LAN setup and office mail server testing |
| [OUTLOOK_INTEGRATION_GUIDE.md](OUTLOOK_INTEGRATION_GUIDE.md) | Connecting an Outlook / Microsoft 365 mailbox |
| [OCR_Integration_Handover.md](OCR_Integration_Handover.md) | How the OCR is wired into CDTRS, and its status |
| [OCR_new/README.md](OCR_new/README.md) | The OCR engine: pipeline, configuration, standalone use |
| [OCR_new/fineTune/README.md](OCR_new/fineTune/README.md) | Fine-tuning handwriting recognition on your own labelled scans |

## Troubleshooting

| Problem | What to do |
|---|---|
| The app says it cannot reach the server | Check that the `start_backend.bat` window is open. Check `CDTRS_API_URL` in `frontend\.env`, the firewall rule, and that http://<server>:8000/health opens |
| `password authentication failed for user "postgres"` | Fix the password in `DATABASE_URL` in `backend\.env` |
| The backend window shows `[SECURITY WARN] SECRET_KEY` | Set a random `SECRET_KEY` in `backend\.env` |
| The first OCR after starting is slow | The OCR engine is still loading (20–60 s). Later documents are faster |
| Handwriting is read poorly | Run `fineTune\download_base_model.py` once, then fine-tune on your own scans |
| Python not found by the `.bat` files | Install Python 3.12, or set `CDTRS_PYTHON` to the full path of `python.exe` |
