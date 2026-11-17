# CDTRS: Centralised Document Tracking and Routing System

CDTRS records every official document that reaches the office (letters, notes, circulars, e-mails with
attachments), routes it to the right people, and tracks each person's work on it until the Director's
Secretary (DS) closes it. It runs on the office intranet and works fully offline, including the OCR.

This README is the single documentation file of the project. It replaces the earlier `readme.md`,
`ARCHITECTURE.md`, `DATA_MANAGEMENT_GUIDE.md`, `Intranet_testing.md`, `OCR_Integration_Handover.md`,
`OUTLOOK_INTEGRATION_GUIDE.md`, `backend/readme.md`, `OCR_new/README.md`, `OCR_new/fineTune/README.md` and the
small README files in `OCR_new/models/*` and `OCR_new/training/`. Everything below was checked against the code.

```text
API base URL     http://<server>:8000/api/v1          (on the server itself: http://127.0.0.1:8000/api/v1)
Health check     http://<server>:8000/health
Swagger UI       http://<server>:8000/docs            (also /redoc; needs internet for its scripts, see 13.13)
WebSocket        ws://<server>:8000/api/v1/ws
Login            POST /api/v1/auth/login  ->  access_token (JWT, HS256)
Request headers  Authorization: Bearer <access_token>
                 X-Work-Context-Id: <id of the work context in use>
Settings         backend\.env  (template backend\.env.example),  frontend\.env  (template frontend\.env.example)
Project folder   C:\CDTRS-main  (Windows 10/11, Python 3.12 64-bit, PostgreSQL 18, database "cdtrs")
```

## Contents

1. [What CDTRS does](#1-what-cdtrs-does)
2. [Architecture](#2-architecture)
3. [Folder structure](#3-folder-structure)
4. [Requirements and packages](#4-requirements-and-packages)
5. [Setup on a new server PC](#5-setup-on-a-new-server-pc)
6. [Configuration reference (every setting)](#6-configuration-reference-every-setting)
7. [Running CDTRS](#7-running-cdtrs)
8. [Building the desktop app as a Windows .exe](#8-building-the-desktop-app-as-a-windows-exe)
9. [Database](#9-database)
10. [Workflow, roles and work contexts](#10-workflow-roles-and-work-contexts)
11. [Intake, OCR and routing suggestions](#11-intake-ocr-and-routing-suggestions)
12. [Mail integration (POP3/SMTP and Outlook)](#12-mail-integration-pop3smtp-and-outlook)
13. [API reference](#13-api-reference)
14. [Data management and admin scripts](#14-data-management-and-admin-scripts)
15. [The OCR engine (OCR_new) in detail](#15-the-ocr-engine-ocr_new-in-detail)
16. [Fine-tuning the OCR on your own handwriting](#16-fine-tuning-the-ocr-on-your-own-handwriting)
17. [Tests](#17-tests)
18. [Deployment on the office network, backup and restore](#18-deployment-on-the-office-network-backup-and-restore)
19. [Known limitations and loose ends](#19-known-limitations-and-loose-ends)
20. [Troubleshooting](#20-troubleshooting)
21. [Demo accounts and departments](#21-demo-accounts-and-departments)

---

## 1. What CDTRS does

- **Intake.** The DS registers documents by uploading a scan, PDF, Word file or image, or by syncing the DS
  mailbox (office mail server over POP3, or Outlook / Microsoft 365).
- **OCR.** An offline engine (`OCR_new\`) reads each document, including handwriting. It finds the Director's
  handwritten instructions on the letter and suggests the departments that should handle it. Nothing leaves the PC.
- **Routing.** The DS first sends the document to the Director for review. With the Director's remark, the DS then
  routes it to one or more departments (HODs), employees or the TSO. The Director step is skipped only when the DS has
  verified that the paper already carries the Director's instruction.
- **Work tracking.** Every person has their own work item, with free-text progress, attachments, HOD review,
  deadlines, reminders and notifications (in the app and by e-mail).
- **Work contexts.** One account can hold several roles ("hats"), for example Employee in one department and HOD of
  another. The user switches between them in the desktop app.
- **Priority and deadlines.** Documents carry a priority (CRITICAL, HIGH, MEDIUM, LOW) and deadlines; every work item
  has its own deadline. An hourly scan raises reminders for work that is overdue or due within two days.

Roles:

| Role | Who | What they do |
|---|---|---|
| DS | Director's Secretary | Registers documents, sends them to the Director, routes them, closes and reopens them, verifies OCR fields |
| DIRECTOR | The Director | Reviews documents and writes remarks; never closes a document |
| HOD | Head of a department | Assigns work on their own department's workstream, reviews (accepts / returns) each person's work |
| EMPLOYEE | Staff member of a department | Works on assignments: stage, progress, attachments, submission |
| TSO | One officer organisation-wide | Receives work directly from the DS (outside the department structure) |
| ADMIN | System administrator | Accounts, work contexts, departments (with routing keywords), settings, audit log |

The full form of "TSO" is not written anywhere in the code; the role is simply called TSO everywhere.

---

## 2. Architecture

```text
 Desktop app (PySide6)        HTTP /api/v1 + WebSocket /api/v1/ws        Backend (FastAPI, uvicorn)
 main.py + frontend\   ───────────────────────────────────────────────►  backend\  (run_server.py)
 (one per client PC,           address: CDTRS_API_URL                        │
  or the built CDTRS.exe)      in frontend\.env                              ├── PostgreSQL 18, database "cdtrs"   (DATABASE_URL)
                                                                             ├── backend\uploads\  stored files    (UPLOAD_DIR)
                                                                             ├── OCR_new\  imported in-process      (backend\ocr_adapter.py)
                                                                             │     PaddleOCR 2.8.1 + TrOCR handwriting + spaCy + MiniLM embeddings
                                                                             └── Office mail server (optional)
                                                                                   DS mailbox  --POP3-->  CDTRS   (incoming documents)
                                                                                   CDTRS mailbox <--SMTP-- CDTRS  (notification e-mails)
                                                                                   or Microsoft Graph (Outlook) for both
```

- **One server PC** runs PostgreSQL and the backend. Client PCs only talk to the backend port (8000 by default);
  they never connect to PostgreSQL.
- **The backend is the only server.** It holds the register and full history, enforces the workflow rules and the
  per-context visibility, stores files, runs OCR and routing suggestions, syncs the DS mailbox every 30 seconds, sends
  notification e-mails, and pushes live events to the desktop apps over the WebSocket.
- **The desktop app never touches the database and never runs OCR itself.** The intake page sends the file to
  `POST /api/v1/intelligence/analyze`; the OCR models are loaded once, on the server
  (`frontend\services\ocr_adapter.py` is only an HTTP bridge).
- **OCR_new** is imported directly by `backend\ocr_adapter.py`; `backend\main.py` puts `OCR_new\` and the project root
  on `sys.path` itself.

### 2.1 The one idea the workflow follows

A document is **not** a thing with a single status. It has **workstreams**, each workstream has **people**, and each
person has **their own work**.

```text
Document                       coarse lifecycle only: RECEIVED / REGISTERED / IN_REVIEW / IN_WORK / WITH_DS / CLOSED
  │
  ├── DocumentBranch           ONE independent workstream with its OWN stage
  │     ├── DIRECTOR     Review Requested → Under Director Review → Remark Added → Returned to DS
  │     ├── DEPARTMENT   HOD Review → Employee Assignment → Employee Work → HOD Validation → Completed
  │     ├── EMPLOYEE     Assigned → In Progress → Submitted → Completed
  │     └── TSO          Assigned → In Progress → Submitted → Completed
  │     (shared stages: FURTHER_WORK, COMPLETED, CANCELLED)
  │
  └── WorkItem                 ONE PERSON's work, the unit of traceability
        ├── WorkStage          Assigned / Under Work / Waiting / Submitted / Under Review / Returned / Completed / Cancelled
        ├── own deadline, own round
        ├── ProgressUpdate[]   free text, append-only, never a percentage
        │     └── Attachment[] tied to the update it belongs to
        └── WorkItemReview[]   HOD (or DS) accepted / returned this person's work
```

Three branches on one document routinely sit at three different stages. That is the normal case, and nothing in the
system collapses them into one value. The Documents table in the app shows a multi-line "Workstreams" column, for
example:

```text
Engineering HOD: Employee Work
Anil Kumar: Completed
TSO: In Progress
```

### 2.2 Rules the code enforces

| Rule | Where |
|---|---|
| Only the DS opens branches (routes) | `workflow.open_branches` requires a DS context |
| Only the DS closes a document | `workflow.close_document` requires a DS context |
| The Director reviews and remarks, never closes | `DirectorReview` has no decision field |
| Director review is repeatable, every remark is kept | one `DocumentBranch` per review, `review_no` increments |
| Work routing (HOD, employee, TSO) needs a Director review first | Director gate, section 10.4 |
| One work item per person, always | `assign_work_items` creates one row per `user_id` |
| A team groups work items, never replaces them | `WorkTeam` is a label; members keep separate `WorkItem`s |
| Progress is free text | `ProgressUpdate.description`; no numeric column exists |
| Branch stages never leak into the document lifecycle | `recompute_lifecycle` only looks at active/closed |
| Nothing is overwritten | remarks, reviews, progress and stage changes are append-only |
| Authorization comes from the active context, not the job title | `require_context(...)` on every mutation |
| Optimistic concurrency | mutations accept `expected_version`; a stale version gets HTTP 400 "changed by someone else ... Reload it and try again" |
| Closed means closed | changes to a closed document are refused until the DS reopens it |
| OCR and routing suggestions are assistive only | they pre-fill dialogs; they never route anything |

### 2.3 Backend modules

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app: all 84 HTTP routes and the WebSocket, login and work-context dependencies, upload checks (size, type, duplicates), start-up tasks (tables, columns, seeding, OCR warm-up, mailbox-sync loop, hourly reminder loop). Imports pyarrow and pandas first (Windows DLL order). |
| `workflow.py` | **The workflow engine**: routing (branches), Director review and gate, work items and stages, progress, HOD validation, branch and document closure, reopening, visibility, inbox, dashboard, deadline reminders, in-app notifications and their e-mail copies. The single place workflow rules live. |
| `crud.py` | Everything outside the workflow: bcrypt password hashing, JWT tokens, work contexts, TSO designation, intake messages, document creation and metadata edits, attachments (SHA-256, unique file names, duplicate lookup), notifications, manual reminders, admin functions, system settings, seeding (`apply_seed_payload`), the WebSocket event manager. |
| `models.py` | SQLAlchemy models: all 23 tables and 15 enums. |
| `schemas.py` | Pydantic request and response models. |
| `serializers.py` | Database objects to API responses. |
| `database.py` | Loads `backend\.env`, creates the engine and sessions, adds `CRITICAL` to an old `priority_enum`, adds columns that older databases lack. |
| `intelligence.py` | OCR of registered documents, extracted fields, DS field verification, department ranking and routing suggestions, intake analysis (`/intelligence/*`), OCR warm-up. |
| `ocr_adapter.py` | The backend's single entry point into OCR_new: loads the engine once, runs one OCR at a time (lock), detects handwritten Director instructions, semantic similarity. Imports torch before PaddlePaddle (Windows DLL order). |
| `mail\` | `service.py` (provider choice, DS mailbox sync, notification e-mails), `intranet_provider.py` (POP3 in, SMTP out), `outlook_provider.py` (Microsoft Graph), `base.py` (abstract provider and data classes), `auth_personal.py` (one-time Outlook sign-in). |
| `run_server.py` | Starts uvicorn with HOST/PORT from `backend\.env`; used by `start_backend.bat`. |
| `import_from_csv.py`, `import_employees.py`, `reset_db.py`, `clear_documents.py`, `reset_password.py`, `backup_database.py`, `seed.py` | Admin scripts (section 14). |

### 2.4 Frontend layers

| Layer | Files |
|---|---|
| Entry points | `main.py` (project root, used by `start_frontend.bat` and the .exe build) and `frontend\main.py` (same, when started from `frontend\`) |
| Settings | `frontend\config\settings.py` (reads `frontend\.env`, section 6.2) |
| HTTP and live events | `frontend\api\client.py`, `endpoints.py`, `exceptions.py`; `services\websocket_service.py` (QtWebSockets) |
| Data | `repositories\api_repository.py` (the only place that speaks HTTP), `repositories\provider.py` |
| Services | `auth_service`, `document_service`, `routing_service`, `work_service`, `admin_service`, `notification_service`, `dashboard_service`, `attachment_service`, `ocr_service`, `ocr_adapter`, `event_bus`, `date_utils` |
| Context and menus | `core\context\context_manager.py` (active hat), `core\navigation\navigation_registry.py` (menu per hat) |
| Windows | `ui\login.py` (login, change password), `ui\main_window.py`, `ui\sidebar.py` (menu and context switcher) |
| Pages | `pages\*.py` (section 10.6) |
| Components | `branch_panel.py` (branch and per-person cards), `document_viewer.py`, `document_preview.py` (QtPdf preview), `routing_dialogs.py` (multi-target routing, assignment, progress, review, closure), `workflow_print.py` (printable workflow sheet), `notification_bell.py` / `notification_panel.py`, `priority_badge.py`, `busy_dialog.py`, `ocr_splash_dialog.py` and others |
| Style | `frontend\styles\theme.qss` |

---

## 3. Folder structure

```text
C:\CDTRS-main\
├── README.md                   this file
├── main.py                     desktop app entry point (adds frontend\ to sys.path, loads the theme, opens the login)
├── start_backend.bat           double-click: starts the backend (checks that backend\.env exists)
├── start_frontend.bat          double-click: starts the desktop app
├── requirements.txt            the pinned packages CDTRS uses (backend + frontend + OCR), section 4
├── imp.txt                     `pip list` of the deployment PC's full Python environment (the reference versions)
├── .env.example                note only: there is no project-wide .env (settings are in backend\ and frontend\)
├── .gitignore
├── image.png                   screenshot of CDTRS notification e-mails from an earlier mail test (not used by code)
├── scripts\
│   ├── find_python.bat         finds Python 3.12 for the other .bat files (CDTRS_PYTHON, per-user install, C:\Program Files\Python312, py -3.12)
│   └── backup_database.bat     database + uploads backup (wraps backend\backup_database.py)
├── backend\                    FastAPI server (section 2.3)
│   ├── main.py, workflow.py, crud.py, models.py, schemas.py, serializers.py, database.py
│   ├── intelligence.py, ocr_adapter.py, run_server.py
│   ├── import_from_csv.py, import_employees.py, reset_db.py, clear_documents.py, reset_password.py,
│   │   backup_database.py, seed.py, __init__.py (empty; makes "backend" importable)
│   ├── .env.example            template for backend\.env
│   ├── requirements.txt        backend pins (same versions)
│   ├── mail\                   base.py, service.py, intranet_provider.py, outlook_provider.py, auth_personal.py,
│   │                           __init__.py, .token_cache.json (personal Outlook token, git-ignored, created by auth_personal.py)
│   ├── data\
│   │   ├── seed_data.json      demo departments and accounts (section 21), seeded on every start
│   │   ├── import_templates\   departments.csv, accounts.csv (headers only) + *_example.csv (filled in)
│   │   └── import\             you create it: real staff lists for import_from_csv.py (git-ignored)
│   ├── tests\                  plain-Python test and diagnostic scripts (section 17)
│   └── uploads\                created at run time, git-ignored:
│       ├── <year>\<doc_id>\            files of one document
│       ├── <year>\intake_<msg id>\     attachments of a synced e-mail
│       ├── _analysis\                  temporary copies while the intake reads a file
│       └── .mail_state\pop3_uidl_state.json   which POP3 messages were already imported (section 12.3)
├── frontend\                   PySide6 desktop app (section 2.4)
│   ├── api\, components\, config\, core\, models\, pages\, repositories\, services\, ui\, styles\theme.qss
│   ├── tests\test_ui_smoke.py
│   ├── .env.example            template for frontend\.env
│   └── requirements.txt        client PC pins
├── OCR_new\                    offline OCR and document-intelligence engine (section 15)
│   ├── main.py                 command line
│   ├── document_intelligence.py  DocumentProcessor / DocumentResult (Python API)
│   ├── setup_models.py         check or re-copy the PaddleOCR models
│   ├── requirements.txt
│   ├── config\config.yaml      all OCR settings (section 15.5)
│   ├── api\                    app.py (optional local REST API), schemas.py
│   ├── document\, preprocessing\, ocr\, layout\, classification\, nlp\, extraction\ (patterns.yaml), semantic\, output\, utils\
│   ├── models\
│   │   ├── paddleocr\          det\, rec\, cls\, model_info.json  (about 16 MB, tracked in git)
│   │   ├── embeddings\model\   all-MiniLM-L6-v2 (about 90 MB, tracked in git; its README.md is the model's own card)
│   │   ├── handwriting\        trocr-small-handwritten\, v1\, v2\ ..., active.txt   (not in git)
│   │   ├── classifiers\        text_type\, document\ once you train them (not in git)
│   │   ├── ner\                optional own spaCy model folders
│   │   └── layout\             reserved; no layout model is used
│   ├── fineTune\               handwriting fine-tuning (section 16): 1_..6_*.bat, download_base_model.py,
│   │                           prepare_dataset.py, label_tool.py, set_active_model.py, common.py, tee.py,
│   │                           configs\, datasets\ (raw\, lines\, classification\), training\train.py, evaluation\evaluate.py
│   ├── testing\                130 unittest tests (section 17.4)
│   ├── training\               empty (training moved to fineTune\)
│   ├── input\                  sample inputs (test_doc.png, two PDFs)
│   ├── output\                 CLI results and ocr_system.log
│   └── temp\                   pdf2image temp folder; old experiment scripts and sample images
├── _env_setup\                 local install / diagnostic scripts and logs from setting up the server PC (git-ignored)
│   ├── install_python312_and_packages.bat + install_env.ps1   installs Python 3.12 and every imp.txt version (about 2.5 GB)
│   ├── fix_and_verify.py, verify_quick.bat                    repair and smoke-test the environment
│   └── diagnostics\                                          one-off crash / WebSocket / DB probes from past debugging
├── Claude outputs\             cdtrs_update.zip, an old update archive (git-ignored, not used)
└── backups\                    created by the backup script (git-ignored)
```

---

## 4. Requirements and packages

| | |
|---|---|
| Operating system | Windows 10/11, 64-bit |
| Python | 3.12, 64-bit (PaddlePaddle 2.6.2 supports Python up to 3.12). Installed per user at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` on the server PC |
| Database | PostgreSQL (the server PC runs PostgreSQL 18) |
| Memory | 8 GB minimum on the server: OCR peaks at about 3 GB per page |
| Internet | Not needed to run CDTRS. Needed once to download the handwriting model (about 250 MB), to install packages on a new PC, and for Outlook mail if you use it |

**Package rule.** The versions are fixed. `imp.txt` (project root) is the `pip list` of the deployment PC's whole
Python environment (about 560 packages, many of them unused by CDTRS). `requirements.txt` pins exactly the subset CDTRS
uses, at the same versions; `backend\requirements.txt`, `frontend\requirements.txt` and `OCR_new\requirements.txt` pin
the same versions for their part. Do not upgrade or add packages.

Main packages and what they are for:

| Package | Version | Used for |
|---|---|---|
| fastapi / starlette / uvicorn / websockets | 0.111.0 / 0.37.2 / 0.30.1 / 12.0 | REST API, WebSocket, ASGI server |
| pydantic / pydantic-core / pydantic-settings | 2.8.2 / 2.20.1 / 2.3.4 | Request and response validation |
| python-multipart | 0.0.9 | File uploads |
| sqlalchemy / psycopg2-binary | 2.0.31 / 2.9.9 | ORM, PostgreSQL driver |
| python-dotenv | 1.0.1 | Loads `backend\.env` |
| bcrypt / python-jose / cryptography | 4.0.1 / 3.3.0 / 42.0.8 | Password hashing, JWT tokens |
| passlib | 1.7.4 | Pinned, not imported by the code |
| requests / pip-system-certs | 2.32.3 / 4.0 | Graph calls, frontend HTTP client; Windows certificate store for HTTPS |
| numpy / pandas / pyarrow | 1.26.4 / 2.2.2 / 24.0.0 | Numeric work; pyarrow and pandas are pre-loaded at start-up (Windows DLL order) |
| paddlepaddle / paddleocr | 2.6.2 / 2.8.1 | OCR (CPU) |
| torch / torchvision / transformers / tokenizers / sentencepiece | 2.13.0 / 0.28.0 / 5.15.0 / 0.22.2 / 0.2.2 | TrOCR handwriting recognition (CPU build of torch) |
| sentence-transformers | 5.6.1 | Embeddings for department matching |
| spacy + en_core_web_sm | 3.8.14 + 3.8.0 | Named entities (the model is installed from its GitHub release file, listed in `requirements.txt`) |
| scikit-learn / scipy / scikit-image | 1.9.0 / 1.17.1 / 0.24.0 | TF-IDF, trained classifiers, image processing |
| opencv-python / Pillow / shapely / pyclipper | 4.10.0.84 / 10.4.0 / 2.0.5 / 1.3.0.post5 | Images and text-box geometry |
| PyMuPDF / pypdf / pypdfium2 / pdfplumber / pdf2image | 1.24.9 / 4.3.1 / 4.30.0 / 0.11.9 / 1.17.0 | PDF reading and rendering |
| python-docx / openpyxl | 1.2.0 / 3.1.5 | Word reading; `.xlsx` import files |
| PyYAML / python-dateutil | 6.0.2 / 2.9.0.post0 | OCR configuration; date normalisation |
| huggingface_hub / editdistance | 1.27.0 / 0.8.0 | One-time TrOCR download; error rates in fine-tuning |
| PySide6 | 6.7.2 | Desktop app (QtWidgets, QtPdf, QtPdfWidgets, QtPrintSupport, QtWebSockets) |
| pyinstaller / pyinstaller-hooks-contrib | 6.22.3 / 2026.7 | Building `CDTRS.exe` (in `imp.txt`, not in `requirements.txt`; section 8) |

Install on a new PC (needs internet):

```bat
cd /d C:\CDTRS-main
py -3.12 -m pip install -r requirements.txt
```

To reproduce the full deployment environment instead, double-click `_env_setup\install_python312_and_packages.bat`
(installs Python 3.12.10 to `C:\Python312` and every `imp.txt` version; about 2.5 GB, 20 to 40 minutes, log in
`_env_setup\install_log.txt`). Client PCs that only run the desktop app need just `frontend\requirements.txt`, or
nothing at all if you give them the built `CDTRS.exe` (section 8).

No test framework (pytest) is part of the environment. All tests use the standard library.

---

## 5. Setup on a new server PC

All commands are for the Windows Command Prompt. If `python` is not recognised, use `py -3.12` or the full path in
quotes, `"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"` (the user name may contain a space).

**Step 1. Python and packages.** Section 4.

**Step 2. Create the database** (once). With pgAdmin (Databases > Create > Database..., name `cdtrs`, owner
`postgres`) or:

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -c "CREATE DATABASE cdtrs;"
```

Only the empty database is needed. The backend creates the tables and seeds the data itself.

**Step 3. Backend settings** (once):

```bat
cd /d C:\CDTRS-main\backend
copy .env.example .env
notepad .env
```

Set at least `DATABASE_URL` (the postgres password) and `SECRET_KEY`. Generate a key with:

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Step 4. OCR models** (once):

```bat
cd /d C:\CDTRS-main\OCR_new
python setup_models.py --check
python fineTune\download_base_model.py
```

The first command checks that the PaddleOCR models (in git) are present. The second downloads the TrOCR handwriting
model (about 250 MB, internet needed only this once) into `models\handwriting\trocr-small-handwritten\` and makes it
active. Without it everything works, but handwriting is read by PaddleOCR only. On a PC without internet, run it on
another PC and copy the `OCR_new\models\handwriting\` folder across.

**Step 5. Start the backend.** Double-click `start_backend.bat` and keep the window open. On the first start it
creates the tables and the demo departments and accounts, then loads the OCR engine in the background (20 to 60
seconds). Check http://127.0.0.1:8000/health.

**Step 6. Desktop app settings** (once per PC):

```bat
cd /d C:\CDTRS-main\frontend
copy .env.example .env
```

Set `CDTRS_API_URL` to `http://127.0.0.1:8000/api/v1` on the server itself, or `http://<server-ip>:8000/api/v1` on
other PCs.

**Step 7. Start the app.** Double-click `start_frontend.bat` and log in, for example as `exec_user` / `cdtrs@ds` (DS)
or `corp` / `cdtrs@admin` (Admin). These are demo accounts (section 21); before real use, follow section 14.2 to load
your real departments and staff and remove the demo data.

**Step 8. Office network and mail** (optional): sections 18 and 12.

---

## 6. Configuration reference (every setting)

There are three settings files. There is no project-wide `.env`; the root `.env.example` only says so.

| File | Holds | Template |
|---|---|---|
| `backend\.env` | Database, host/port, security key, uploads, CORS, mail | `backend\.env.example` |
| `frontend\.env` | Address of the backend, request timeout, app name | `frontend\.env.example` |
| `OCR_new\config\config.yaml` | OCR engine settings | itself (section 15.5) |

Both `.env` files contain passwords and are git-ignored. Never paste them into chat, e-mail or screenshots.

### 6.1 backend\.env

`backend\.env` is loaded explicitly from the backend folder by `database.py`, `run_server.py`, `backup_database.py`
and `tests\test_intranet_mail.py`, so it works whatever the current folder is. A variable set in the Command Prompt
(`set NAME=value`) takes precedence over the file. The backend reads the file only when it starts: restart it after
every change.

**Core settings**

| Key | Template value | Default if missing | Meaning |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:CHANGE_ME@localhost:5432/cdtrs` | `postgresql+psycopg2://postgres@localhost:5432/cdtrs` | `postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>`. `postgres://` and `postgresql://` are converted automatically. URL-encode special characters in the password (`@` as `%40`). |
| `HOST` | `0.0.0.0` | `0.0.0.0` | Listen address (`run_server.py`). `0.0.0.0` = other PCs can connect; `127.0.0.1` = this PC only. |
| `PORT` | `8000` | `8000` | Server port. Use the same number in the firewall rule and every client's `CDTRS_API_URL`. |
| `LOG_LEVEL` | (not in template) | `info` | uvicorn log level for `run_server.py`. |
| `SECRET_KEY` | `CHANGE_ME_TO_A_LONG_RANDOM_VALUE` | built-in default | Signs login tokens (HS256). If it is missing or contains "change", the server prints `[SECURITY WARN] ...`; a missing key falls back to a fixed built-in value. Never run like that. Changing the key logs everybody out. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | `480` | How long a login stays valid (8 hours). |
| `UPLOAD_DIR` | `./uploads` | `./uploads` | File storage, relative to `backend\` (`run_server.py` switches to that folder first). |
| `MAX_FILE_SIZE` | `20971520` | 20 MB | Largest accepted upload in bytes; larger files get HTTP 413. |
| `CORS_ORIGINS` | `*` | `*` | `*` or a comma-separated list of browser origins. The desktop app does not need it. |

**Mail selection**

| Key | Values | Meaning |
|---|---|---|
| `MAIL_CHANNEL` | `intranet`, `outlook`, `off` (also `none`, `disabled`) | Which mail system syncs the DS mailbox and sends notifications. **If the line is missing, `outlook` is used.** `local`, `smtp_imap` and `gov_mail` also select the intranet provider; any other unknown value falls back to Outlook. `python run_server.py --no-mail` sets it to `off` for one run. |
| `OVERRIDE_TEST_RECIPIENT_EMAIL` | an address, or empty / `none` / `false` / `off` | Testing: every notification e-mail goes to this one address instead of the real users. |
| `TEST_MAIL_RECIPIENT` | an address | Default recipient for `tests\test_intranet_mail.py --send`. Not used by CDTRS itself. |

**Office mail server (MAIL_CHANNEL=intranet): POP3 in, SMTP out**

Incoming mail is read over **POP3** (since 13 Nov 2026; it was IMAP before). The `INTRANET_POP3_*` keys are the current
names. For host, security and auth the code falls back to the old `INTRANET_IMAP_*` keys, so an old `.env` keeps
working, **but the old `INTRANET_IMAP_PORT` is not used** (993 is an IMAP-only port). Note that `backend\.env.example`
still shows the old IMAP key names.

| Key | Default if missing | Meaning |
|---|---|---|
| `INTRANET_POP3_HOST` | value of `INTRANET_IMAP_HOST`, else empty | Mail server name or IP for the DS mailbox. |
| `INTRANET_POP3_SECURITY` | value of `INTRANET_IMAP_SECURITY`, else `ssl` | `ssl` (POP3S, implicit TLS), `starttls` (STLS) or `plain`. Also accepted: `tls`/`stls` = starttls, `ssl/tls`/`ssl_tls`/`pop3s` = ssl, `none` = plain. |
| `INTRANET_POP3_PORT` | `995` for `ssl`, `110` otherwise | POP3 port. |
| `INTRANET_POP3_AUTH` | value of `INTRANET_IMAP_AUTH`, else `password` | Only `password` is supported. |
| `INTRANET_POP3_STATE_FILE` | `backend\uploads\.mail_state\pop3_uidl_state.json` | Where the UIDLs of already-imported messages are remembered (section 12.3). The default is next to the code, not under `UPLOAD_DIR`. |
| `POP3_TIMEOUT` | value of `IMAP_TIMEOUT`, else `20` | Network timeout in seconds. |
| `DS_MAIL_USER` / `DS_MAIL_PASS` | empty | Login of the **DS mailbox** (incoming). Some servers need the full e-mail address as user name. |
| `INTRANET_SMTP_HOST` | empty | Mail server for sending, through the **CDTRS mailbox**. |
| `INTRANET_SMTP_PORT` | `587` | SMTP port. |
| `INTRANET_SMTP_SECURITY` | `starttls` | `ssl`, `starttls` or `plain` (same aliases as above, except `stls`/`pop3s`). |
| `INTRANET_SMTP_AUTH` | `password` | Only `password` is supported. |
| `CDTRS_MAIL_USER` / `CDTRS_MAIL_PASS` | empty | Login of the CDTRS mailbox (outgoing). A different account from the DS mailbox. |
| `CDTRS_SENDER_EMAIL` | value of `CDTRS_MAIL_USER` | "From" address. Do not leave the line present but empty: an empty value is not the same as a missing line, and the provider then counts as not configured. |
| `CDTRS_SENDER_NAME` | `CDTRS` | "From" display name. |
| `INTRANET_ALLOW_SELFSIGNED` | `false` | `true` accepts a self-signed mail-server certificate (certificate and host-name checks are switched off, for POP3 and SMTP). Use only for a trusted internal server. |
| `INTRANET_IMAP_HOST`, `INTRANET_IMAP_SECURITY`, `INTRANET_IMAP_AUTH`, `IMAP_TIMEOUT` | | Old names, still read as fallbacks (see above). `INTRANET_IMAP_PORT` is ignored. |

The intranet provider counts as **configured** only when the POP3 host, `DS_MAIL_USER`, the SMTP host,
`CDTRS_MAIL_USER` and the sender address are all set.

Example (`ssl` POP3 on 995, STARTTLS SMTP on 587):

```ini
MAIL_CHANNEL=intranet
INTRANET_POP3_HOST=192.168.1.100
INTRANET_POP3_PORT=995
INTRANET_POP3_SECURITY=ssl
INTRANET_POP3_AUTH=password
DS_MAIL_USER=ds_office@intranet.gov.in
DS_MAIL_PASS=<DS mailbox password>
POP3_TIMEOUT=20
INTRANET_SMTP_HOST=192.168.1.100
INTRANET_SMTP_PORT=587
INTRANET_SMTP_SECURITY=starttls
INTRANET_SMTP_AUTH=password
CDTRS_MAIL_USER=cdtrs@intranet.gov.in
CDTRS_MAIL_PASS=<CDTRS mailbox password>
CDTRS_SENDER_EMAIL=cdtrs@intranet.gov.in
CDTRS_SENDER_NAME=CDTRS
INTRANET_ALLOW_SELFSIGNED=true
OVERRIDE_TEST_RECIPIENT_EMAIL=
```

Security modes (ask the mail administrator; do not guess):

| Value | What happens | Usual POP3 port | Usual SMTP port |
|---|---|---|---|
| `ssl` | Encrypted from the first byte | 995 | 465 |
| `starttls` | Plain connection upgraded with STLS / STARTTLS | 110 | 587 |
| `plain` | No encryption (trusted internal network only) | 110 | 25 |

**Outlook / Microsoft 365 (MAIL_CHANNEL=outlook)**

| Key | Meaning |
|---|---|
| `OUTLOOK_AUTH_MODE` | `personal` or `organizational`. Documents the choice only: the code decides by what is present (a token cache file means personal mode; tenant, client id, secret and mailbox mean organisation mode). |
| `OUTLOOK_TENANT_ID` | Organisation mode: Entra ID (directory) tenant id. |
| `OUTLOOK_CLIENT_ID` | Organisation mode: application (client) id. When empty, Microsoft's public client id is used. |
| `OUTLOOK_CLIENT_SECRET` | Organisation mode: client secret value. |
| `OUTLOOK_MAILBOX` | The DS mailbox that is read and that sends notifications. |
| `OUTLOOK_FOLDER` | Mail folder that is read (default `Inbox`). |

### 6.2 frontend\.env

`frontend\config\settings.py` reads `frontend\.env`; only if that file does not exist does it try a `.env` in the
current folder. Keep each value alone on its line (no comment after it). Values already set in the environment win.

| Key | Default | Meaning |
|---|---|---|
| `CDTRS_API_URL` | `http://127.0.0.1:8000/api/v1` | Address of the backend, with `/api/v1`. The older name `API_BASE_URL` is also read when `CDTRS_API_URL` is missing. |
| `CDTRS_API_TIMEOUT` | `15.0` | Seconds to wait for the backend; raise it on a slow network. |
| `CDTRS_APP_NAME` | `CDTRS` | Window title text. |
| `CDTRS_APP_VERSION` | `2.0.0` | Version shown in the app. |

For the built `.exe` the file is looked up in different places (section 8.3).

### 6.3 Other environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `CDTRS_PYTHON` | `scripts\find_python.bat` (all `.bat` files) | Full path of the `python.exe` to use |
| `CDTRS_API_URL` | `backend\tests\test_context_audit.py`, `frontend\tests\test_ui_smoke.py` | Test server address (default `http://127.0.0.1:8123`) |
| `TEST_MAIL_RECIPIENT` | `backend\tests\test_intranet_mail.py` | Default `--recipient` |

### 6.4 System settings stored in the database

`system_settings` holds key/value pairs, edited in Admin > System Configuration or with `/admin/settings`. Missing
defaults are added at every start:

| Key | Default | Used by the code? |
|---|---|---|
| `mail.notifications_enabled` | `true` | **Yes**: e-mail copies of notifications are sent only while it is `true` |
| `mail.reminder_enabled`, `mail.reminder_lead_days` (2), `mail.from_address`, `mail.template.assignment`, `mail.template.reminder` | | No (stored only) |
| `priority_red_days`, `priority_orange_days`, `priority_yellow_days`, `reminder_email_subject`, `reminder_email_template` | written by the System Configuration page | No (stored only; see section 19) |

---

## 7. Running CDTRS

### 7.1 Backend

Double-click `start_backend.bat`. It finds Python (`scripts\find_python.bat`), checks that `backend\.env` exists and
runs `backend\run_server.py`. Keep the window open; closing it stops the server for everybody. Options are passed
through, for example `start_backend.bat --port 8123 --host 127.0.0.1`.

Manual start:

```bat
cd /d C:\CDTRS-main\backend
python run_server.py
python run_server.py --port 8123 --host 127.0.0.1 --log-level debug
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `HOST` from `.env`, else `0.0.0.0` | Listen address |
| `--port` | `PORT` from `.env`, else `8000` | Port |
| `--log-level` | `LOG_LEVEL`, else `info` | uvicorn log level |
| `--no-mail` | off | `MAIL_CHANNEL=off` for this run: no mailbox sync, no e-mails. Always use it for test servers. |

Plain uvicorn also works from the backend folder (`python -m uvicorn main:app --host 0.0.0.0 --port 8000`). **Never
add `--reload`**: it starts a second process and loads the OCR models twice.

What happens on start:

1. Every missing table of the 23 is created (existing tables are never changed or emptied).
2. Old databases: `CRITICAL` is added to `priority_enum` if missing; the columns `routing_suggestions.ranked_departments`,
   `departments.description`, `departments.keywords` and `director_reviews.edited_at` are added if missing
   (`[STARTUP] Added missing column ...`).
3. Seeding from `backend\data\seed_data.json` (section 14.1): `[CDTRS SEED] 15 departments, 17 accounts, ... work contexts.`
4. OCR warm-up in a background thread `ocr-warm-up`: PaddleOCR, NER, regex extraction and the embedding model. The
   first OCR is ready after 20 to 60 seconds; the API answers meanwhile. TrOCR loads with the first document.
5. Background loops: DS mailbox sync every 30 seconds (only when `MAIL_CHANNEL` is not off and the provider is
   configured; one sync at a time), and the deadline-reminder scan every hour (the first scan runs one hour after start).

Start-up problems such as a wrong `DATABASE_URL` are printed as `[STARTUP WARN] ...`; the server keeps running, but
`/health` fails until the database is reachable.

Health check: `curl http://127.0.0.1:8000/health` returns
`{"status": "healthy", "documents": 0, "open_branches": 0, "open_work_items": 0}` (it queries the database).
`GET /` returns `{"service": "CDTRS", "version": "3.0.0", "status": "ok"}` without it.

**Windows DLL order.** Native libraries must load in a fixed order, or the backend crashes silently about 45 seconds
after start and the app reports "WebSocket error: The remote host closed the connection". The code handles it:
`backend\main.py` imports pyarrow and pandas first; `backend\ocr_adapter.py` imports torch before PaddlePaddle;
`OCR_new\document_intelligence.py` calls `utils\native_libs.preload()`. Keep those imports at the top of the files.

### 7.2 Desktop app

Double-click `start_frontend.bat` (runs `python main.py` in the project folder), or the built `CDTRS.exe`. Log in;
choose the work context in the sidebar if the account has several. "Change Password" is on the login window.

---

## 8. Building the desktop app as a Windows .exe

The desktop client is shipped to user PCs as a Windows executable built with **PyInstaller 6.22.3** (installed on the
server PC from `imp.txt`; on another PC: `py -3.12 -m pip install pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.7`).
Only the desktop app is built. The backend and OCR stay on the server and are run with Python.

The repository has no `.spec` file; the command below creates one (`CDTRS.spec`), which you can keep and reuse with
`pyinstaller CDTRS.spec`.

### 8.1 Why these options

- The entry point is the root `main.py`. It puts `frontend\` on `sys.path` at run time and imports `ui.login`, so
  PyInstaller must be told to look in `frontend\` (`--paths frontend`), otherwise none of the app modules are bundled.
- `main.py` loads the theme from `<bundle>\frontend\styles\theme.qss`, so the stylesheet must be added as data at
  exactly that place.
- The app imports only PySide6 (QtWidgets, QtGui, QtCore, QtPdf, QtPdfWidgets, QtPrintSupport, QtWebSockets), requests,
  pypdf and pip-system-certs. It never imports torch, paddle or the backend, so the bundle stays small (about
  180 to 250 MB) even though the build PC has the full environment.
- `--windowed` hides the console window.

### 8.2 Build

```bat
cd /d C:\CDTRS-main
py -3.12 -m PyInstaller --noconfirm --clean --windowed --name CDTRS ^
    --paths frontend ^
    --add-data "frontend\styles\theme.qss;frontend\styles" ^
    main.py
```

Optional: `--icon path\to\cdtrs.ico` (the project has no icon file yet).

Result: `dist\CDTRS\CDTRS.exe` with its `dist\CDTRS\_internal\` folder (one-folder build). `build\`, `dist\` are
git-ignored. Ship the whole `dist\CDTRS\` folder, for example as a zip.

A one-file build (`--onefile` instead of the default) also works but starts slower, because it unpacks itself to a
temporary folder at every start, and it changes where `.env` is found (8.3).

### 8.3 Settings for the .exe (frontend .env)

The app looks for its settings in this order:

1. **`dist\CDTRS\_internal\.env`** (the folder of the bundled `config\settings.py`). Always found, however the exe is
   started. **Recommended.**
2. `.env` in the current folder. When the user double-clicks `CDTRS.exe`, that is the exe's folder, so a `.env` next to
   `CDTRS.exe` also works; a shortcut must then have "Start in" set to that folder.

With `--onefile`, option 1 is a temporary folder, so only option 2 (a `.env` next to the exe, started from its folder)
works. Without any `.env`, the app connects to `http://127.0.0.1:8000/api/v1`.

On each user PC:

```bat
copy C:\CDTRS-main\frontend\.env.example "<install folder>\CDTRS\_internal\.env"
notepad "<install folder>\CDTRS\_internal\.env"
```

and set `CDTRS_API_URL=http://<server-ip>:8000/api/v1`. Do not bundle a `.env` into the build with `--add-data`,
because each site needs its own server address.

### 8.4 Check the build

1. Start `dist\CDTRS\CDTRS.exe` with the backend running and log in.
2. If it closes at once, rebuild without `--windowed` and start it from a Command Prompt to see the traceback.
3. A `ModuleNotFoundError: No module named 'ui'` (or `pages`, `services`, ...) means `--paths frontend` was missing.
4. A plain, unstyled window means the theme was not added at `frontend\styles`.

These steps were verified on 13 Nov 2026 with PyInstaller 6.22.3 and PySide6 6.7.2 on Linux (one-folder build: all app
modules and the Qt Pdf/PrintSupport/WebSockets libraries were collected, the theme was found, the login window started,
and the `.env` lookup behaved as in 8.3). A Windows build has not been run as part of writing this guide.

---

## 9. Database

PostgreSQL database `cdtrs`: **23 tables** and **15 enums**, all defined in `backend\models.py`. Tables are created by
the server on start (or by `reset_db.py`). There is **no migration tool**: `database.py` adds the four columns that
were introduced later (section 7.1). A new column in `models.py` must be added to `_ADDED_COLUMNS` in `database.py`, or
older databases will miss it.

### 9.1 Enums

| Enum (Python) | PostgreSQL type | Values |
|---|---|---|
| `UserRole` | `user_role` | ADMIN, DS, DIRECTOR, TSO, HOD, EMPLOYEE |
| `WorkContextType` | `work_context_type` | EMPLOYEE, HOD, DIRECTOR, DS, TSO, ADMIN |
| `DocumentLifecycle` | `document_lifecycle` | RECEIVED, REGISTERED, IN_REVIEW, IN_WORK, WITH_DS, CLOSED |
| `BranchType` | `branch_type` | DIRECTOR, DEPARTMENT, EMPLOYEE, TSO |
| `BranchStage` | `branch_stage` | Director: REVIEW_REQUESTED, UNDER_DIRECTOR_REVIEW, REMARK_ADDED, RETURNED_TO_DS. Department: HOD_REVIEW, EMPLOYEE_ASSIGNMENT, EMPLOYEE_WORK, HOD_VALIDATION. Employee/TSO: ASSIGNED, IN_PROGRESS, SUBMITTED. Shared: FURTHER_WORK, COMPLETED, CANCELLED |
| `WorkStage` | `work_stage` (also `progress_stage`, `stage_change_from`, `stage_change_to`) | ASSIGNED, UNDER_WORK, WAITING, SUBMITTED, UNDER_REVIEW, RETURNED, COMPLETED, CANCELLED |
| `ReviewOutcome` | `review_outcome` | ACCEPTED, RETURNED |
| `RemarkType` | `remark_type_enum` | DIRECTOR, HOD, DS, TSO, EMPLOYEE, OTHER |
| `Priority` | `priority_enum` | CRITICAL, HIGH, MEDIUM, LOW |
| `SourceType` | `source_type_enum` | OUTLOOK, GOVERNMENT_MAIL, MANUAL_UPLOAD, OTHER_APPROVED_SOURCE, MANUAL |
| `MessageProcessingStatus` | `msg_status_enum` | NEW, PROCESSING, PROCESSED, FAILED, IGNORED |
| `AttachmentType` | `att_type_enum` | ORIGINAL, EMAIL_ATTACHMENT, SUPPORTING_DOCUMENT, PROGRESS_ATTACHMENT |
| `OCRStatus` | `ocr_status_enum` (documents), `ocr_record_status_enum` (document_ocr) | NONE, PENDING, PROCESSING, COMPLETED, FAILED |
| `RoutingSource` | `routing_source_enum` | DOCUMENT_CONTENT, DIRECTOR_REMARK, SOURCE_METADATA, MANUAL |
| `ReminderReason` | `reminder_reason_enum` | DUE_SOON, OVERDUE, ACTION_REQUIRED |

Which branch stages are legal for which branch type is defined in `workflow.BRANCH_STAGES` (also returned by
`GET /api/v1/workflow/vocabulary`).

### 9.2 Tables

| Layer | # | Table | Purpose |
|---|---|---|---|
| Master data | 1 | `departments` | Departments, with routing description and keywords |
| | 2 | `employees` | Staff directory (HR reference data, not a login), optionally linked to an account |
| | 3 | `users` | Login accounts |
| | 4 | `work_context_memberships` | The "hats" a user can wear; the unit of authorization |
| | 23 | `system_settings` | Key/value settings |
| Documents and files | 5 | `incoming_messages` | E-mails fetched from the DS mailbox (intake provenance) |
| | 6 | `documents` | The register, one row per document |
| | 13 | `attachments` | Stored files: originals, mail attachments, supporting documents, progress attachments |
| | 16 | `document_ocr` | One OCR record per document |
| | 17 | `document_extracted_fields` | Fields found by OCR, with the DS-verified value |
| | 18 | `routing_suggestions` | One advisory routing suggestion per document |
| Workflow | 7 | `document_branches` | Independent workstreams on a document |
| | 8 | `work_teams` | Named groups of work items inside a branch (label only) |
| | 9 | `work_items` | One person's work on one branch |
| | 10 | `progress_updates` | Free-text progress (append-only) |
| | 11 | `work_item_reviews` | HOD or DS accepting / returning one person's work |
| | 12 | `work_stage_changes` | Audit of every work-item stage change |
| | 14 | `director_reviews` | Every completed Director review (repeatable) |
| | 15 | `document_remarks` | All remarks (append-only) |
| | 19 | `reminders` | Deadline and manual reminders per work item |
| | 20 | `workflow_events` | Complete chronological history of each document |
| | 22 | `notifications` | In-app notifications, per user and optionally one work context |
| Admin audit | 21 | `audit_logs` | Administrative and configuration actions only |

### 9.3 Key columns

| Table | Key columns |
|---|---|
| `departments` | `id`, `name` (unique, max 100), `code` (unique, max 20, e.g. `FIN`), `description`, `keywords` (one comma-separated line), `is_active`, `created_at` |
| `users` | `id`, `username` (unique, max 50), `password_hash` (bcrypt), `full_name`, `role` (primary designation only, not used for authorization), `department_id` (home department), `employee_code`, `designation`, `email` (unique), `outlook_email`, `gov_email`, `preferred_mail_channel` (default `outlook`; no longer used), `is_active`, `created_at`, `updated_at` |
| `employees` | `id`, `employee_code` (unique), `full_name`, `department_id`, `designation`, `email`, `outlook_email`, `gov_email`, `user_id`, `is_active` |
| `work_context_memberships` | `id`, `user_id`, `context_type`, `department_id` (required for HOD and EMPLOYEE), `is_active`; unique (`user_id`, `context_type`, `department_id`) |
| `documents` | `doc_id`, `reference_no` (unique, `CDTRS-<year>-0001` ...), `title`, `subject`, `description`, `received_date`, `deadline`, `source`, `sender_name`, `sender_reference`, `mode`, `priority`, `lifecycle`, `ocr_status`, `created_by`, `source_message_id`, `version`, `created_at`, `updated_at`, `registered_at`, `closed_at`, `closed_by_user_id`, `closure_remark` |
| `document_branches` | `id`, `document_id`, `branch_type`, `stage`, `department_id`, `target_user_id`, `target_context_membership_id`, `opened_by_user_id`, `instructions`, `requires_hod_validation`, `deadline`, `round_no`, `is_active`, `opened_at`, `closed_at`, `version` |
| `work_items` | `id`, `document_id`, `branch_id`, `team_id`, `assigned_to_user_id`, `assigned_to_context_membership_id`, `assigned_by_user_id`, `instructions`, `deadline`, `stage`, `requires_validation`, `round_no`, `continues_item_id`, `is_active`, `assigned_at`, `started_at`, `submitted_at`, `completed_at`, `version` |
| `progress_updates` | `id`, `document_id`, `work_item_id`, `author_user_id`, `description`, `stage_at_time`, `created_at` |
| `attachments` | `id`, `document_id` (empty for mailbox attachments not yet registered), `progress_update_id`, `uploaded_by_user_id`, `uploaded_by_context_membership_id`, `file_name`, `storage_key` (path under `UPLOAD_DIR`), `file_type`, `file_size`, `checksum` (SHA-256), `attachment_type`, `source_message_id`, `created_at` |
| `director_reviews` | `id`, `document_id`, `branch_id`, `director_user_id`, `remark_text`, `review_no`, `document_version`, `requested_at`, `created_at`, `edited_at` |
| `document_remarks` | `id`, `document_id`, `branch_id`, `work_item_id`, `author_user_id`, `remark_type`, `remark_text`, `provenance` (`MANUAL`, `DIRECTOR_REVIEW`, `WORK_REVIEW`, `CLOSURE`) |
| `document_extracted_fields` | `id`, `document_id`, `field_name` (upper case), `extracted_value`, `confidence`, `source_page`, `verified_value`, `verified_by`, `verified_at` |
| `routing_suggestions` | `document_id` (unique), `suggested_department_id`, `suggested_employee_id` (a `users.id`), `routing_confidence`, `routing_reason`, `routing_source`, `is_director_instruction`, `ranked_departments` (JSON), `generated_at`, `confirmed_by`, `confirmed_at` |
| `workflow_events` | `id`, `document_id`, `branch_id`, `work_item_id`, `event_type`, `actor_user_id`, `actor_context_type`, `summary`, `details`, `created_at` |
| `reminders` | `id`, `document_id`, `work_item_id`, `recipient_user_id`, `recipient_context_membership_id`, `reason`, `message`, `due_at`, `sent_at`, `is_read`, `deduplication_key` (unique) |
| `notifications` | `id`, `user_id`, `context_membership_id`, `document_id`, `branch_id`, `work_item_id`, `event_id`, `title`, `message`, `is_read` |

Useful checks (psql asks for the postgres password):

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d cdtrs -c "SELECT id, subject, sender_email, has_attachments, received_at FROM incoming_messages ORDER BY id DESC LIMIT 5;"
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d cdtrs -c "SELECT id, file_name, storage_key, file_size, source_message_id FROM attachments WHERE source_message_id IS NOT NULL ORDER BY id DESC LIMIT 5;"
```

### 9.4 File storage

```text
backend\uploads\
  <year>\<doc_id>\               files of one document: original, supporting documents, progress attachments
  <year>\intake_<message id>\    attachments of a synced e-mail (they stay here after registration)
  _analysis\                     temporary copies while the DS intake reads a file (deleted right away)
  .mail_state\                   POP3 UIDL state (section 12.3)
```

- `<year>` is the year of the upload, so a file added later to an older document goes into a newer folder.
- A file never overwrites another: a second `letter.pdf` in the same folder is stored as `letter_1.pdf`, then
  `letter_2.pdf`; the original name is kept in the database.
- `attachments.storage_key` holds the relative path. Do not rename or move files, or downloads fail with "Stored file
  is missing from disk."
- The application never deletes stored files. Back them up together with the database (section 18.3).

---

## 10. Workflow, roles and work contexts

### 10.1 Work contexts ("hats")

A user holds one or more `WorkContextMembership` rows. The active hat is sent on every request as `X-Work-Context-Id`
and decides what the person sees and may do: dashboard, menu, task list, permissions and notifications. Without the
header the backend uses the hat matching the account's primary role, otherwise the first active one. An
`X-Work-Context-Id` that is not one of the caller's active hats gets 403.

```text
tso_user
  ├── TSO (Executive Office)
  └── EMPLOYEE (Engineering & Innovation)
```

TSO work never appears in that person's Employee task list. The organisation has exactly **one** active TSO
(`POST /admin/tso/{user_id}/activate`; granting a TSO hat to someone takes it from the previous holder). An account
without any active hat cannot log in ("This account has no active work context. Contact an administrator.").

### 10.2 Visibility

- DS and Director hats see the whole register.
- An HOD sees the document-level entries, the Director review, and only the workstreams of their own department (plus
  any they opened, are the target of, or have work in). Workstreams, remarks, attachments and history entries of other
  departments are left out of every document endpoint and of `/history`.
- An Employee or the TSO sees the workstreams they work on.
- The Admin hat sees no documents.

### 10.3 The life of a document

1. **Intake (DS).** Manual upload, mailbox message, or metadata only. Reference number `CDTRS-<year>-NNNN`; lifecycle
   RECEIVED. OCR runs and a routing suggestion is made.
2. **Check and register (DS).** Correct the details (`PATCH /documents/{id}`), verify OCR fields, confirm with
   `register` (REGISTERED).
3. **Director review.** The DS sends it to the Director (`send-to-director`, or a routing request whose only target is
   the Director). Only one Director review can be open. The Director opens it (`director-review/start`) and returns it
   with a required remark (`director-review`). Reviews are numbered and all kept; the Director who wrote a review can
   correct its wording later (`PATCH /director-reviews/{id}`, recorded as `DIRECTOR_REMARK_EDITED`).
4. **Routing (DS).** One request can open many branches: departments (HOD), employees directly, or the TSO, each with
   instructions, deadline, "requires HOD validation", optional assignees and a team name. Routing again to a target
   whose branch is open adds a round (FURTHER_WORK).
5. **Assignment (HOD or DS).** One work item per person. An HOD only on their own department's branch; assignees of a
   Department branch need an EMPLOYEE hat in that department.
6. **Work (Employee, TSO, or an HOD on their own item).** Stage changes (the worker may choose UNDER_WORK, WAITING,
   SUBMITTED), free-text progress, progress with a file, submission. Submission goes to UNDER_REVIEW when validation is
   required on a Department branch (HODs are notified), otherwise COMPLETED (the DS is notified). It never closes the
   document.
7. **Review (HOD of the department, or DS).** ACCEPTED or RETURNED, with a note, per person.
8. **Closure (DS only).** Refused while workstreams are open unless `force` is set (they are then cancelled and
   recorded). A single branch can be closed on its own. A closed document can be reopened by the DS with a reason.

Every step writes a `workflow_events` row, sends in-app notifications, pushes a WebSocket event, and (if mail is on)
an e-mail copy.

### 10.4 The Director gate and verified prior review

Routing to HODs, employees or the TSO is refused (HTTP 400) until a Director review exists, and the Director cannot be
combined with work targets in one routing request. The one exception: OCR finds a handwritten Director instruction on
the letter and sets the fields `PRIOR_DIRECTOR_REVIEW_DETECTED = true` and `DIRECTOR_HANDWRITTEN_REMARK`. That alone is
**not** enough: the DS must verify `PRIOR_DIRECTOR_REVIEW_DETECTED` with `true` (also accepted: `1`, `yes`, `detected`,
`confirmed`); `workflow._ocr_prior_director_review_detected` reads only `verified_value`. The intake page shows the
instruction OCR found (editable) with a tick box "The Director has already reviewed this document"; when it is ticked,
registering verifies both fields, writes `PRIOR_DIRECTOR_REVIEW_CONFIRMED` to the history, lets the confirmed
instruction steer the routing suggestion, and the routing dialog offers HODs, employees and the TSO straight away. The
document viewer also lets the DS verify these fields later (**Verify & Save**). Re-running OCR keeps DS-verified values.

### 10.5 Notifications, reminders and deadlines

- Every workflow notification is stored in-app (`notifications`), addressed to a user and optionally one hat. The
  bell and panel in the app show those for the active hat plus those without a hat.
- **Deadline scan** (hourly, or `POST /reminders/check`): for each live work item with a deadline that is overdue or due
  within 2 days, one reminder and notification per item, reason and day (`deduplication_key`).
- **Manual reminder**: the DS or an HOD reminds one work item, or everyone with open work on the document
  (`POST /documents/{id}/remind`).
- E-mail copies: see section 12.4.

### 10.6 Desktop pages per hat

| Hat | Menu (from `navigation_registry.py`) |
|---|---|
| DS | Dashboard, Document Intake, Inbox (incoming communications, Sync Now), Documents, Workflow History |
| DIRECTOR | Dashboard, Inbox (review queue), Documents, History / Audit (director_reviewed page) |
| HOD | Dashboard, HOD Inbox, Documents, Workflow History |
| EMPLOYEE | Dashboard, Employee Tasks, Documents, Workflow History |
| TSO | Dashboard, TSO Tasks, Documents, Workflow History |
| ADMIN | Dashboard, User Configuration, Department Configuration, System Configuration, Audit History |

Admin pages: **User Configuration** (add user, manage, activate / deactivate, reset password, add / remove hats;
accounts cannot be deleted because the history refers to them), **Department Configuration** (name, code, description,
routing keywords, activate / deactivate; a description is required), **System Configuration** (section 6.4),
**Audit History**. `pages\priority.py` (a deadlines and priority monitor) exists but is not in any menu (section 19).

---

## 11. Intake, OCR and routing suggestions

### 11.1 How documents enter

1. **Manual intake (desktop app, DS).** Document Intake > Manual Intake / Upload File. The app sends the file to
   `POST /intelligence/analyze` (OCR, fields, department suggestion; nothing stored) to pre-fill the form; the DS
   checks it and clicks Register Document, which calls `POST /intake/manual-upload` with the text and fields already
   read, so the file is not read twice. The routing dialog then opens.
2. **Mailbox.** The backend fetches the DS mailbox every 30 seconds, or at once with **Sync Now** in the DS Inbox
   (`POST /intake/sync-outlook`, whatever `MAIL_CHANNEL` is, despite the name). Each new e-mail becomes an
   `incoming_messages` row with its attachments stored; the DS opens it in Document Intake and registers it
   (`POST /intake/{message_id}/process`). The same e-mail is never stored twice (matched by its Message-ID) and a
   message already registered cannot be processed again (409).
3. **Metadata only.** `POST /documents`.
4. **Other programs / scanners.** `POST /intake/manual-upload` with a DS token (section 13.4). Example with Windows
   `curl`:

   ```bat
   curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"username\": \"<ds user>\", \"password\": \"<password>\"}"
   rem note access_token and the id of the DS context in the answer
   curl -X POST http://127.0.0.1:8000/api/v1/intake/manual-upload ^
     -H "Authorization: Bearer <access_token>" -H "X-Work-Context-Id: <DS context id>" ^
     -F "title=Annual budget allocation 2026-27" -F "received_date=2026-09-25" -F "priority=HIGH" ^
     -F "sender_reference=FIN/2026/114" -F "file=@C:\scans\budget_letter.pdf"
   ```

   Without `ocr_text` the server runs OCR before answering, which can take a minute for a scan. Then register with
   `POST /documents/<doc_id>/register`.

Accepted upload types: `.pdf .docx .doc .xlsx .xls .png .jpg .jpeg .tif .tiff .bmp .webp .txt .csv .zip` (others 415),
up to `MAX_FILE_SIZE` (413). OCR reads `.pdf .png .jpg .jpeg .tif .tiff .bmp .webp .docx .txt`.

**Duplicate protection.** Every stored file gets a SHA-256 checksum. A manual upload equal to an existing document's
ORIGINAL is refused with 409 naming that document ("This file is already registered as document CDTRS-... Open that
document instead of registering it again."); adding the same file twice to one document is 409 too. Mail attachments
are not checksum-checked on arrival (the e-mail is recognised by Message-ID); once registered they count as originals.
Progress attachments are not checked.

**Dates.** `received_date` and `deadline` must be real calendar dates (`2026-09-27`, `27/09/2026`, `27.09.2026`,
`27 September 2026` and similar). An empty received date means today; anything unreadable, such as `44/88/2026`, is
refused with 422.

**Priority.** CRITICAL, HIGH, MEDIUM, LOW in any case; `URGENT`/`IMMEDIATE` = CRITICAL, `NORMAL` = MEDIUM, `ROUTINE`
= LOW; unknown = MEDIUM.

### 11.2 OCR of a registered document

- Runs in a worker thread, so the server keeps answering and the WebSocket stays connected. OCR_new is used by one
  request at a time (the models are not thread-safe).
- Source text, in this order: text sent by the intake form; otherwise OCR_new on the stored original (or the first
  attachment OCR_new can read); otherwise the title (engine `FALLBACK_METADATA`).
- Results: OCR text and confidence (`document_ocr`), extracted fields in upper case (`document_extracted_fields`),
  Director instruction detection, and a fresh routing suggestion.
- `DATE` / `DEADLINE` are only taken when they are real dates (`OCR_new\extraction\date_utils.py`): a reference such
  as `44/88/2026` or `31/02/2026` is skipped. "Last date / due date / reply by / on or before ..." dates are deadlines,
  not the letter's date.
- Failures are stored as FAILED with the error and never block registration. Re-running OCR
  (`POST /documents/{id}/ocr/run`) replaces unverified values only.
- If the PaddleOCR models are missing, the error says to run `python OCR_new/setup_models.py` once.

**Director instruction detection** (`backend\ocr_adapter.py`). Among the HANDWRITTEN lines, address lines ("To, The
Director", "Sir", "Subject", "Ref", "Yours" ...) are ignored; the rest are scored for instruction words ("put up",
"discuss", "for action", "see me", "do the needful", "approved", "noted", "urgent" ...). The best line is returned with
the handwritten lines next to it as `DIRECTOR_HANDWRITTEN_REMARK` / `PRIOR_DIRECTOR_REVIEW_DETECTED`. A printed letter
never triggers an instruction. It stays unverified until the DS confirms it (10.4).

### 11.3 Routing suggestions (advisory)

`intelligence.py` scores every active department against the title, subject and OCR text. The keyword score is the
highest of these signals:

| Signal | Score |
|---|---|
| The full department name appears | 1.0 |
| OCR found a "Department:" line naming it | 0.95 |
| Configured routing keywords found: 1 / 2 / 3 or more | 0.55 / 0.75 / 0.9 |
| All words of the name appear, in any order | 0.85 |
| The department code as a separate word, same capitals | 0.8 (0.5 for a two-letter code) |
| A staff member of the department is named | 0.6 |
| Built-in topic words (from the name, code and description): 1 / 2 / 3 / 4+ | 0.2 / 0.45 / 0.65 / 0.8 |
| Distinctive words of the department's description (4+ letters, common words excluded): 2 / 3-4 / 5+ | 0.25 / 0.35 / 0.5 |

The **semantic score** is the similarity of the text to a department profile (name, code, description, keywords,
topic words, staff designations) from the local `all-MiniLM-L6-v2` model. Combined:
`score = 1 - (1 - keyword) x (1 - semantic)`. A department is suggested only when the score is at least **0.3** and
either the keyword score is at least **0.2** or the semantic score at least **0.4**. The full ranking is stored in
`ranked_departments`; the routing dialog shows the top 5 as clickable chips.

Precedence: a Director remark naming an employee (confidence 0.95) or a department (0.92) first; then a department or
employee the DS chose on the intake form (1.0); otherwise the content ranking. The suggestion is refreshed after OCR
and after every Director review (and on `POST /documents/{id}/analyze-routing`). It never routes anything.

**Keyword matching rules.** Case and punctuation are ignored (`e-office` matches "E-Office"). A phrase must appear as
exactly that word sequence. A single word of 6+ letters also matches words starting with the same six letters
(`payment` matches "payments"). A word of 4 or 5 letters matches only itself. A word of 3 characters or fewer (HR, IT,
GST, RTI) counts only as a separate word written in CAPITALS in the document.

**Tips for good routing data.** One or two plain sentences of description listing the subjects the department
handles; 5 to 15 keywords typical for that department only (avoid "letter", "request", "office"; never give the same
keyword to two departments); phrases for common words (`service book`, `supply order`); both forms of short words
(`bill, bills`); the abbreviations your documents really use. Register a few real documents, look at the ranking in
the routing dialog, and adjust. Keywords may be separated by commas, semicolons or new lines; they are stored as one
comma-separated line with duplicates removed. Changes apply to documents analysed from then on.

---

## 12. Mail integration (POP3/SMTP and Outlook)

Mail is optional. Without it CDTRS works with manual intake and in-app notifications, and the mailbox is reported as
"not configured".

### 12.1 Overview

| Direction | Intranet (`MAIL_CHANNEL=intranet`) | Outlook (`MAIL_CHANNEL=outlook`) |
|---|---|---|
| Incoming | DS mailbox over **POP3** (`backend\mail\intranet_provider.py`) | DS mailbox via Microsoft Graph (`outlook_provider.py`), unread messages of `OUTLOOK_FOLDER` |
| Outgoing | CDTRS mailbox over SMTP | Graph `sendMail` from `OUTLOOK_MAILBOX` |
| "Already imported" | UIDL state file (12.3); mail stays on the server | Message marked as read in the mailbox |
| Recipient address | account's `email`, then `gov_email`, then `outlook_email` | `outlook_email`, then `email`, then `gov_email` |

The sync logic for both is in `backend\mail\service.py`: each new e-mail becomes an `incoming_messages` row (status
NEW); attachments are saved under `uploads\<year>\intake_<message id>\` with a SHA-256 checksum; a Message-ID already
in the database is skipped and counted as a duplicate; after storing, the provider's `mark_as_read` is called. Up to 50
messages per sync.

### 12.2 POP3 behaviour (intranet)

- Connects with `POP3_SSL` (ssl), `POP3` + `STLS` (starttls) or plain `POP3`, then `USER`/`PASS` with `DS_MAIL_*`.
- Lists messages with `UIDL`. Messages whose UIDL is in the "seen" set are skipped. The newest 50 new messages are
  downloaded with `RETR`, newest first.
- **Nothing is ever deleted from the server** (no `DELE` is sent); the session ends with `QUIT`.
- Very old servers without `UIDL`: the provider falls back to message numbers and all messages are offered each time;
  duplicates are then only filtered by Message-ID in the database.
- A message without a Message-ID header gets the id `intranet-pop3-<uidl>`.
- poplib's line limit is raised to 1 MB so long lines (big HTML, unwrapped base64) do not abort the download.
- SMTP: `SMTP_SSL`, `SMTP` + `STARTTLS` or plain, login with `CDTRS_MAIL_*`, timeout 15 s, multipart (text + HTML +
  attachments).

### 12.3 The UIDL state file

POP3 has no "read" flag, so CDTRS remembers imported messages in
`backend\uploads\.mail_state\pop3_uidl_state.json` (or `INTRANET_POP3_STATE_FILE`):

```json
{ "seen": ["<uidl>", "..."], "pending": {"<uidl>": 1}, "updated_at": "2026-11-13T10:00:00" }
```

- A UIDL handed to the sync goes to `pending` (count + 1). When the message is stored, `mark_as_read` moves it to
  `seen`.
- A message that was offered but not confirmed (usually because the sync skipped it as a duplicate already in the
  database) is offered again up to 3 more times and then counted as seen.
- UIDLs no longer on the server are forgotten, so the file does not grow forever.
- The file is written atomically and protected by a lock (timer sync and Sync Now can overlap).
- If the file is unreadable, it starts fresh; duplicates are still filtered by Message-ID.
- **Deleting the file** (or `reset_db.py --wipe-uploads`, which empties `backend\uploads`) makes CDTRS consider every
  message still on the server as new. Against the same database they are skipped as duplicates; against a fresh
  database they are imported again.

### 12.4 Outgoing notification e-mails

Every workflow notification is stored in-app. An e-mail copy is queued in the background when the system setting
`mail.notifications_enabled` is `true` (seeded default) and the provider selected by `MAIL_CHANNEL` is configured. All
e-mails go through that one office-wide channel (`users.preferred_mail_channel` is not used). Accounts without any
address get no e-mail. `OVERRIDE_TEST_RECIPIENT_EMAIL` sends everything to one test address. The e-mail carries the
document's original, mail and supporting files; notifications about one person's progress update or submitted work also
carry that person's progress attachments. Subjects look like `[CDTRS] Task assigned: CDTRS-2026-0002 ...`.

### 12.5 Setting up the office mail server (step by step)

1. Fill in `backend\.env` as in section 6.1 and restart the backend.
2. Check the network from the server PC (PowerShell): `Test-NetConnection 192.168.1.100 -Port 995` and `-Port 587`.
   `TcpTestSucceeded : True` is needed for both; otherwise fix the network, VPN or firewall first.
3. **Stop the live backend, or run it with `--no-mail`**, while testing: a running backend with mail on syncs the DS
   mailbox every 30 seconds and would take your test e-mails first.
4. Connection test (does not touch the database or the UIDL state file):

   ```bat
   cd /d C:\CDTRS-main\backend
   python tests\test_intranet_mail.py
   ```

   It prints the configuration (passwords masked), checks the seven required values (`INTRANET_POP3_HOST`,
   `DS_MAIL_USER`, `DS_MAIL_PASS`, `INTRANET_SMTP_HOST`, `CDTRS_MAIL_USER`, `CDTRS_MAIL_PASS`, `CDTRS_SENDER_EMAIL`), the
   security and auth values, then connects, logs in, shows `STAT` (messages on the server), whether `UIDL` works and
   how many messages CDTRS has not imported yet, and lists up to 10 most recent messages (sender, subject, time,
   attachments, start of body). Exit code 0 when all requested tests pass.
5. Send a test e-mail (with a small PDF attached) to the DS mailbox and run the test again; check that it is listed
   with `Attachments: 1`.
6. SMTP test: `python tests\test_intranet_mail.py --send --recipient you@intranet.gov.in`; type `SEND` to confirm.
   Subject `[CDTRS] Intranet Mail Integration Test`. Check the sender, and the junk folder. Options: `--send`,
   `--recipient`, `--all` (= `--send` using `--recipient` or `TEST_MAIL_RECIPIENT`), `--incoming-only` (skips SMTP).
7. `python tests\test_mail_service.py` must show `IntranetMailProvider` in block `[5]`. `OutlookGraphProvider` means
   `MAIL_CHANNEL` is missing or misspelled.
8. Start the backend normally, log in as the DS, Inbox > **Sync Now**: "New communications: 1". Sync again: 0 new.
9. Run a full workflow with `OVERRIDE_TEST_RECIPIENT_EMAIL` set, check the notification e-mails, then empty it and
   restart before going live. Make sure user accounts have their office e-mail filled in.

### 12.6 Outlook / Microsoft 365

**Mode A, personal mailbox (testing with @outlook.com / @hotmail.com).** In `backend\.env`: `MAIL_CHANNEL=outlook`,
`OUTLOOK_AUTH_MODE=personal`, `OUTLOOK_MAILBOX=...`, `OUTLOOK_FOLDER=Inbox`. Sign in once (internet needed):

```bat
cd /d C:\CDTRS-main\backend
python mail\auth_personal.py
```

It prints a web address and a code (device-code sign-in with Microsoft's public client, permissions `Mail.ReadWrite`,
`Mail.Send`, `User.Read`) and saves `backend\mail\.token_cache.json` (git-ignored). Restart the backend; the token
refreshes itself. **While that file exists, Outlook counts as configured**, even if the other `OUTLOOK_` settings are
empty, and it is tried first. To disconnect, delete it and restart. A token from an older version (read-only mail
permission) must be replaced by signing in again.

**Mode B, organisation mailbox.**

1. https://portal.azure.com > Microsoft Entra ID > App registrations > New registration (e.g. `CDTRS Mail
   Integration`, single tenant, no redirect URI).
2. Copy the Application (client) ID to `OUTLOOK_CLIENT_ID` and the Directory (tenant) ID to `OUTLOOK_TENANT_ID`.
3. Certificates & secrets > New client secret; copy the **Value** into `OUTLOOK_CLIENT_SECRET`. Note the expiry date.
4. API permissions > Microsoft Graph > **Application** permissions: `Mail.ReadWrite` (read and mark as read;
   `Mail.Read` alone cannot mark) and `Mail.Send`. Grant admin consent.
5. Application permissions reach every mailbox: ask the Exchange admin to restrict the app to the DS mailbox
   (`New-ApplicationAccessPolicy -AccessRight RestrictAccess` with a mail-enabled group containing it).
6. `backend\.env`: `MAIL_CHANNEL=outlook`, `OUTLOOK_AUTH_MODE=organizational`, tenant, client id, secret,
   `OUTLOOK_MAILBOX`, `OUTLOOK_FOLDER=Inbox`. Make sure `backend\mail\.token_cache.json` does **not** exist.

Tests (from `backend\`): `python tests\test_mail_service.py` (which provider, configured or not);
`python tests\test1.py` (personal token: `/me`, folders, Inbox; sends nothing);
`python tests\test_provider.py someone@example.com` (sends **one real** e-mail). The server needs HTTPS access to
`login.microsoftonline.com` and `graph.microsoft.com`.

---

## 13. API reference

All 84 routes are in `backend\main.py`. Paths are relative to `/api/v1`, except `/`, `/health`. "Who" means:
Public (no token), Login (any valid token), Doc access (login and the active hat may open the document, 10.2), or the
hat type that must be active (`X-Work-Context-Id`). Workflow rules are checked in `workflow.py`.

### 13.1 Health and live events

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/` | Public | Service, version, status (no database) |
| GET | `/health` | Public | Database check with counts |
| WebSocket | `/api/v1/ws` | Public (no token) | Live events as JSON: `event_type`, `document_id`, `user_id`, `timestamp`, `payload`. Any text the client sends is a heartbeat. Event types: `DOCUMENT_CREATED`, `DIRECTOR_REVIEW_REQUESTED`, `DOCUMENT_ROUTED`, `DIRECTOR_REMARK`, `WORK_ASSIGNED`, `WORK_STAGE_CHANGED`, `PROGRESS_UPDATED`, `WORK_SUBMITTED`, `WORK_REVIEWED`, `ATTACHMENT_ADDED`, `DOCUMENT_CLOSED` |
| GET | `/events/recent?limit=20` | Login | Latest events (last 100 kept in memory, lost on restart) |

### 13.2 Authentication

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/login` | Public | `{"username", "password"}` → `access_token`, `token_type`, `user`, `contexts`, `active_context`. 401 wrong credentials / inactive; 403 no active hat |
| GET | `/auth/me` | Login | Own account with hats |
| GET | `/auth/contexts` | Login | Own active hats |
| POST | `/auth/switch-context` | Login | `{"context_membership_id"}`: checks it is yours. The server keeps no session; the client sends the id in `X-Work-Context-Id` |
| POST | `/auth/change-password` | Login | `{"current_password", "new_password"}` |

### 13.3 Reference data

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/users` | Login | Active users; `?context_type=EMPLOYEE&department_id=<id>` lists holders of a hat |
| GET | `/departments` | Login | Active departments with description and keywords |
| GET | `/departments/{department_id}/employees` | Login | Users with an EMPLOYEE hat there |
| GET | `/employees` | Login | Staff directory |
| GET | `/workflow/vocabulary` | Login | Branch stages per type, work stages, worker-selectable stages, lifecycle labels |

### 13.4 Intake and analysis

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/intake` | DS | Mailbox messages not yet processed |
| POST | `/intake/sync-outlook` | DS | Sync the DS mailbox now with the `MAIL_CHANNEL` provider → `status`, `synced_count`, `ignored_duplicates`, `message` |
| GET | `/intake/{message_id}/attachments` | DS | Files of a mailbox message before registration |
| POST | `/intake/{message_id}/process` | DS | Turn a message into a document. JSON body required (may be `{}`), all optional: `title`, `subject`, `description`, `received_date`, `deadline`, `priority`, `source`, `sender_name`, `sender_reference`, `ocr_text`, `ocr_confidence`, `ocr_fields`, `suggested_department_id`, `suggested_employee_id`. 409 if already registered |
| POST | `/intake/manual-upload` | DS | Multipart: `file`*, `title`*, `received_date`*, `mode` (default `MANUAL_UPLOAD`), `priority`, `subject`, `description`, `source` (default `Manual Intake`), `sender_name`, `sender_reference`, `deadline`, `ocr_text`, `confidence` (0-1 or 0-100), `ocr_fields` (JSON object string), `suggested_department_id`, `suggested_employee_id` (stored as suggestion with confidence 1.0). 201; 409 duplicate; 413; 415; 422 bad date |
| POST | `/intelligence/analyze` | DS | Multipart `file` (+ optional `body`): OCR, fields, suggestion. Nothing stored |
| POST | `/intelligence/analyze-text` | DS | `{"text"}` (first 200,000 characters): fields and suggestion. Nothing stored |

### 13.5 Documents

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents` | Login | Documents visible to the active hat, with the caller's own work |
| GET | `/documents/inbox` | Login | What the hat must act on now (DS: new, registered, back with DS, finished branches, returned reviews; Director: open reviews; HOD: active department branches; Employee/TSO: own active work) |
| POST | `/documents` | DS | Register from metadata only. 201 |
| GET | `/documents/{document_id}` | Doc access | Full document limited to what the hat may see; `director_review_satisfied` says whether work routing is open |
| PATCH | `/documents/{document_id}` | DS | Correct `title`, `subject`, `description`, `received_date`, `deadline`, `source`, `sender_name`, `sender_reference`, `priority`, optional `expected_version`. Every change goes to history |
| POST | `/documents/{document_id}/register` | DS | RECEIVED → REGISTERED (idempotent) |
| POST | `/documents/{document_id}/send-to-director` | DS | Open a Director review (`expected_version` optional). Must be registered; one open review at a time. 201 |
| POST | `/documents/{document_id}/close` | DS | `{"remark", "force", "expected_version"}` |
| POST | `/documents/{document_id}/reopen` | DS | `{"reason"}` |
| GET | `/documents/{document_id}/history` | Doc access | Events, oldest first |
| GET | `/history?limit=500` | Login | Events of all visible documents, newest first |
| GET | `/documents/{document_id}/remarks` | Doc access | Visible remarks |

### 13.6 Routing and Director review

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/branches` | Doc access | Workstreams with work items |
| POST | `/documents/{document_id}/branches` | DS | `{"branches": [{"branch_type", "department_id", "target_user_id", "instructions", "requires_hod_validation", "deadline", "assignee_user_ids", "team_name"}], "expected_version"}`. Each target its own branch. Director gate applies. 201 |
| POST | `/branches/{branch_id}/work-items` | DS, HOD | `{"assignee_user_ids", "instructions", "deadline", "requires_validation", "team_name"}`. 201 |
| POST | `/branches/{branch_id}/remark` | DS, HOD, TSO, Employee | `{"remark_text"}` (HOD only on own department's branch) |
| POST | `/branches/{branch_id}/close` | DS | `{"reason"}`; unfinished work items cancelled; document stays open |
| POST | `/branches/{branch_id}/director-review/start` | Director | Mark Under Director Review (idempotent) |
| POST | `/branches/{branch_id}/director-review` | Director | `{"remark_text", "expected_version"}`; remark required; returns to DS, notifies DS, refreshes suggestion |
| GET | `/documents/{document_id}/director-reviews` | Doc access | All reviews, oldest first |
| PATCH | `/director-reviews/{review_id}` | Director (author) | `{"remark_text"}`; keeps number, sets `edited_at`, logs old and new wording, notifies DS. Refused on a closed document |

### 13.7 Work items

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/work-items/mine?include_finished=false` | Login | Own work for the active hat |
| GET | `/work-items/department` | HOD | All work items on the department's branches |
| GET | `/documents/{document_id}/work-items` | Doc access | Work items of a document |
| GET | `/work-items/{work_item_id}` | Doc access | One item with progress and reviews |
| PATCH | `/work-items/{work_item_id}/stage` | Employee, TSO, HOD (own item) | `{"stage", "note"}`: UNDER_WORK, WAITING or SUBMITTED |
| POST | `/work-items/{work_item_id}/progress` | same | `{"description", "new_stage"}`. 201 |
| POST | `/work-items/{work_item_id}/progress-with-file` | same | Multipart `description`, optional `new_stage`, `file` (PROGRESS_ATTACHMENT). The file is checked first, so a rejected file leaves no update. 201 |
| POST | `/work-items/{work_item_id}/submit` | same | `{"note"}` (UNDER_REVIEW or COMPLETED, 10.3) |
| POST | `/work-items/{work_item_id}/review` | HOD (own department), DS | `{"outcome": "ACCEPTED" or "RETURNED", "note"}`; only SUBMITTED / UNDER_REVIEW work |

### 13.8 Attachments

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/attachments` | Doc access | List |
| POST | `/documents/{document_id}/attachments` | Doc access | Multipart `file`, `attachment_type` (default SUPPORTING_DOCUMENT; unknown → 422; ORIGINAL only in DS hat → 403), optional `progress_update_id` (must belong to the document → 422). 409 if the same file is already attached. 201 |
| GET | `/attachments/{attachment_id}/download` | Doc access | Download. Unregistered mailbox attachments only in DS or Admin hat (403 otherwise) |

### 13.9 OCR and routing suggestions

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/ocr` | Doc access | Text, status, engine, confidence, error, fields (extracted, verified, effective) |
| POST | `/documents/{document_id}/ocr/run` | DS | Run OCR again (waits); verified values kept |
| POST | `/documents/{document_id}/verify-field` | DS | `{"field_name", "verified_value"}`; any case; unknown names are created in upper case |
| GET | `/documents/{document_id}/routing-suggestion` | Doc access | Suggestion or `null` |
| POST | `/documents/{document_id}/analyze-routing` | Doc access | `{"include_director_remark": true}`; recompute |

### 13.10 Notifications, reminders, dashboard

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/notifications` | Login | Latest 100 for the active hat plus those without a hat |
| GET | `/notifications/unread` | Login | Unread, same filter |
| PATCH | `/notifications/{notification_id}/read` | Login | Mark one of your own read |
| PATCH | `/notifications/read-all` | Login | → `{"updated": n}` |
| GET | `/reminders` | Login | Your reminders (all hats) |
| POST | `/reminders/check` | Login | Run the deadline scan now |
| PATCH | `/reminders/{reminder_id}/read` | Login | Mark read |
| POST | `/documents/{document_id}/remind` | DS, HOD | `{"work_item_id", "recipient_user_id", "message"}` |
| GET | `/dashboard` | Login | Counter cards and up to 25 inbox documents |

### 13.11 Administration (Admin hat)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/users` | All accounts (also inactive) with hats |
| POST | `/admin/users` | `username`, `password`, `full_name`, `role`, optional `email`, `outlook_email`, `gov_email`, `employee_code`, `designation`, `department_id`. Gets the default hat of its role (EMPLOYEE/HOD only with a department; TSO only if no TSO is active). 201 |
| PUT | `/admin/users/{user_id}` | Change `full_name`, `role`, e-mails, `employee_code`, `designation`, `department_id`, `is_active` |
| POST | `/admin/users/{user_id}/reset-password` | `{"new_password"}` |
| POST | `/admin/users/{user_id}/toggle-active` | → `{"is_active"}` |
| GET | `/admin/users/{user_id}/contexts` | Active hats |
| POST | `/admin/users/{user_id}/contexts` | `{"user_id", "context_type", "department_id"}` (`user_id` must be in the body; the path value is used). TSO designates the single TSO. 201 |
| DELETE | `/admin/users/{user_id}/contexts/{context_id}` | Revoke; 409 if it still has open work |
| GET | `/admin/tso` | Current TSO hat or `null` |
| POST | `/admin/tso/{user_id}/activate` | Designate the TSO |
| GET | `/admin/departments?include_inactive=true` | All departments |
| POST | `/admin/departments` | `{"name", "code", "description", "keywords"}`. 201 |
| PUT | `/admin/departments/{dept_id}` | Any of `name`, `code`, `is_active`, `description`, `keywords` (empty clears) |
| GET / POST | `/admin/settings` | Read / `{"key", "value", "description"}` |
| GET | `/admin/audit-logs?limit=200&offset=0` | Audit log, newest first |

### 13.12 Status codes

| Code | When |
|---|---|
| 400 | Workflow rule violated, invalid input, stale `expected_version`, invalid `X-Work-Context-Id` |
| 401 | Invalid / expired token, inactive or deleted account, wrong login |
| 403 | No `Authorization` header or not a Bearer token (FastAPI HTTPBearer); wrong hat; no access to the document; hat not yours; login without active hat |
| 404 | Not found; stored file missing on disk |
| 409 | Duplicate file; message already registered; revoking a hat with open work |
| 413 / 415 | File too large / type not allowed |
| 422 | Missing or wrong fields; invalid date; unknown `attachment_type`; `progress_update_id` of another document |

### 13.13 Interactive API pages

Swagger UI at `/docs` and ReDoc at `/redoc` ("Authorize" takes the token; `X-Work-Context-Id` appears per endpoint).
They load scripts from a CDN, so on a PC without internet they stay blank. `/openapi.json` always works.

---

## 14. Data management and admin scripts

Run the scripts from the backend folder (`cd /d C:\CDTRS-main\backend`). They use the database in `backend\.env`.

### 14.1 Seeding at every start

The backend runs `crud.seed_data` with `backend\data\seed_data.json` (`{"departments": [], "system_users": [],
"employees": []}`) on every start. It **only creates what is missing**, in one transaction:

| Data | What seeding does |
|---|---|
| Departments (matched by name or code, any case) | Missing ones created; existing ones only get the file's description / keywords if theirs are empty |
| Staff directory (by employee code) | Missing records created |
| Accounts (by username) | Missing ones created with `default_password` (or `cdtrs@123`); existing ones never changed |
| Work contexts | Only accounts created in this run get their hats; removed hats are not switched on again |
| TSO | Designated only if that account was just created and no TSO is active |
| Settings | Missing defaults added |

So Admin edits survive restarts. But whenever a demo account or department is missing (new or reset database), it is
created again with its demo password. **Empty `seed_data.json` before going live.** A seeding error prints
`[STARTUP WARN] ...`, nothing from that run is saved, and the backend still starts.

### 14.2 Going live with real data

1. Prepare `departments.csv` and `accounts.csv` (14.3) and run `python import_from_csv.py --check`. Every department
   used in `accounts.csv` must be in `departments.csv`, because the database will be empty after the reset.
2. Stop the backend and run `python backup_database.py`.
3. Keep the demo file and empty the real one:

   ```bat
   copy data\seed_data.json data\seed_data_demo.json
   notepad data\seed_data.json
   rem replace the whole content with:  {"departments": [], "system_users": [], "employees": []}
   ```

   Keep `seed_data_demo.json`: the tests need the demo accounts (17.1). When you install a newer CDTRS version, keep
   your edited `seed_data.json`.
4. `python reset_db.py --confirm --wipe-uploads`
5. `python import_from_csv.py`
6. Start the backend, log in with your new ADMIN account, check User and Department Configuration.
7. Ask everyone to change their first password and schedule the daily backup (18.3).

If you keep the existing database instead: in **User Configuration** deactivate the demo accounts (they cannot be
deleted; inactive accounts cannot log in and are not offered for routing), remove hats you do not want, give the TSO hat
to the real TSO; in **Department Configuration** deactivate unused demo departments (never suggested or offered).

### 14.3 import_from_csv.py: departments and accounts

```bat
mkdir data\import
copy data\import_templates\departments.csv data\import\
copy data\import_templates\accounts.csv data\import\
rem fill both in Excel, Save As "CSV UTF-8 (Comma delimited)"
python import_from_csv.py --check
python import_from_csv.py
python import_from_csv.py D:\staff_lists --check      (another folder)
```

`.xlsx` files with the same columns also work (active sheet; `.csv` wins if both exist). Column names are not
case-sensitive and empty rows are skipped. Format employee-code columns as Text in Excel to keep leading zeros.
Examples: `data\import_templates\departments_example.csv`, `accounts_example.csv`.

`departments.csv`: `name` (required; a name or code matching an existing department updates it, its name is not
changed), `code` (stored in capitals), `description`, `keywords` (comma-separated).

`accounts.csv`:

| Column | Meaning |
|---|---|
| `username` | Required; the key |
| `full_name` | Default: the username |
| `role` | ADMIN, DS, DIRECTOR, TSO, HOD or EMPLOYEE (default EMPLOYEE) |
| `department` | Code or name, any case; required for HOD and EMPLOYEE |
| `designation` | Default `Staff` |
| `employee_code` | EMPLOYEE rows with a code also get a staff-directory record (without one: a NOTE, account only) |
| `email`, `outlook_email`, `gov_email` | Notification addresses; `email` must be unique |
| `password` | First password of NEW accounts (default `cdtrs@123`); existing passwords never change |
| `contexts` | Optional `;`-separated `TYPE[:DEPT]` (a comma also works) |

`contexts` examples: empty + EMPLOYEE FIN → EMPLOYEE of FIN; `HOD:FIN; HOD:SP` → HOD of both; `EMPLOYEE; HOD:CX` with
department ENG → EMPLOYEE of ENG and HOD of CX; `TSO; EMPLOYEE:FIN`. A filled-in value replaces the default, so include
the main hat. The first row giving a TSO hat makes that account THE TSO. Listed hats are created or switched on again;
unlisted hats are never removed.

Checks (with and without `--check`): empty or unknown values, a code or username used twice, a department code already
belonging to another department, an e-mail used twice or belonging to another account, an employee code used twice.
Any ERROR stops with "Nothing was imported." The import is all-or-nothing (one transaction) and safe to re-run: existing
accounts get the file's name, role, designation, code, department and given e-mails; existing departments get the
description and keywords when filled in, and the code if they have none. Passwords and active status never change.
`--check` needs the database. The backend may keep running. Delete or secure the files afterwards (first passwords).

### 14.4 Other scripts

| Command | Effect |
|---|---|
| `python import_employees.py staff.xlsx [--seed-db]` | Older tool: **replaces the `employees` list in `data\seed_data.json`** from a roster (unknown departments added with the first four letters as code, missing usernames become `emp_<first>_<last>`, password `cdtrs@emp`); `--seed-db` then runs `seed.py`. Cannot set roles or hats. Prefer `import_from_csv.py` |
| `python reset_db.py --confirm` | **Destructive**: drops the whole `public` schema, recreates the 23 tables, seeds, prints the accounts. Without `--confirm` only prints help. Stop the backend first |
| `python reset_db.py --confirm --wipe-uploads` | Also empties `backend\uploads` (and a project-level `uploads` folder if present), including the POP3 state file. It always empties `backend\uploads`, whatever `UPLOAD_DIR` says |
| `python clear_documents.py --confirm` | Deletes all documents and their workflow data, mailbox messages, attachment records, OCR, suggestions, events, reminders, notifications. Keeps accounts, departments, hats, staff directory, settings, audit log and the files in `uploads`. Reference numbers restart at `CDTRS-<year>-0001` |
| `python reset_password.py <username> <new_password>` | Sets a password (without arguments it asks). Does not reactivate an inactive account |
| `python backup_database.py [--dest D:\backups] [--keep 14] [--no-uploads]` | Backup (18.3) |
| `python seed.py` | Older: creates missing tables and seeds (as a server start does), then lists accounts with seed passwords. Its `--reset` drops tables and clears uploads; use `reset_db.py` instead |

Passwords: users change their own on the login window (**Change Password**); the Admin resets them in User
Configuration; on the server use `reset_password.py`. They are bcrypt hashes and cannot be read back.

---

## 15. The OCR engine (OCR_new) in detail

OCR_new reads scanned letters, forms, PDFs and photos, including handwritten notes, and returns the text of every line
with position and confidence, printed/handwritten labels, a category, entities, regex fields and semantic information.
It runs fully offline: all models are local and nothing is downloaded while processing.

### 15.1 Pipeline (`DocumentProcessor.process()` in `document_intelligence.py`; CDTRS always uses `mode="full"`)

```text
1. Load            document/          detect type; render PDF pages at 300 DPI; image frames; DOCX text + embedded images
2. Preprocess      preprocessing/     optional clean-up (every step off by default)
3. PaddleOCR       ocr/paddle_engine  detect lines → turn upside-down lines → read; drop below drop_score; sort
4. Layout          layout/            page regions (HEADER, TITLE, PARAGRAPH ...); does not change the text     [full]
5. Text type       ocr/text_type_detector   PRINTED / HANDWRITTEN / UNKNOWN per line                            [full]
6. TrOCR re-read   ocr/handwriting_engine   handwritten and unsure lines read again                              [full]
7. Classification  classification/    keyword rules, or your trained classifier                       [classify, full]
8. Extraction      nlp/, extraction/  spaCy entities + regex entities + patterns.yaml fields           [extract, full]
9. Semantic        semantic/          embedding, TF-IDF keywords, semantic category, similarities  [understand, full]
```

Input: PDF (every page rendered and OCR'd, the text layer is not used; renderers pypdfium2, then PyMuPDF, then
pdf2image/Poppler), images `.png .jpg .jpeg .tif .tiff .bmp .webp` (each TIFF frame a page), `.docx` (paragraph text
taken directly, embedded images OCR'd as pages 1001, 1002 ...), `.txt`. Unknown extensions are recognised by their
first bytes.

### 15.2 How CDTRS uses it

`backend\ocr_adapter.py` creates one `DocumentProcessor` (reads `config\config.yaml` once) and returns text, average
line confidence, fields, page count, file type and `is_handwritten` (more HANDWRITTEN than PRINTED lines). It adds the
Director-instruction fields (11.2). `extract_text_fields(text)` runs only extraction (e-mail bodies, intake text);
`rank_references(text, refs)` uses the embedding model for department matching. Calls share a lock. A missing
PaddleOCR model raises `SystemExit`, which the adapter turns into "Run 'python OCR_new/setup_models.py' once".
**After editing `config.yaml`, switching the handwriting model or training a classifier, restart the backend.**

### 15.3 Models

| Model | Folder | Size | In git | What to do |
|---|---|---|---|---|
| PaddleOCR det (en_PP-OCRv3_det), rec (en_PP-OCRv4_rec), cls (ch_ppocr_mobile_v2.0_cls) | `models\paddleocr\det`, `rec`, `cls`, `model_info.json` | 16 MB | yes | Nothing. `python setup_models.py --check` shows `[OK]`/`[MISSING]`; `python setup_models.py` re-copies them from `~\.paddleocr\whl` (downloads there first only if missing; refuses PaddleOCR 3.x) |
| TrOCR `trocr-small-handwritten` | `models\handwriting\` + `active.txt` | 250 MB | no | `python fineTune\download_base_model.py` (`--model small|base|large`, default small; `--no-activate`) |
| spaCy `en_core_web_sm` 3.8.0 | installed package | | | Nothing |
| `all-MiniLM-L6-v2` | `models\embeddings\model\` | 90 MB | yes | Nothing (384-number embeddings) |
| Own classifiers | `models\classifiers\text_type\`, `document\` | small | no | Fine-tuning (16) |
| Own spaCy model | `models\ner\<folder with meta.json>\` | | no | Optional; tried before the package |
| Layout model | `models\layout\` | | | None is used: the region detector always uses its contour method; a `layout_model.pkl` would be loaded but model-based detection is not implemented |

`models\handwriting\active.txt` names the model folder in use (now `trocr-small-handwritten`). With no `active.txt`,
or a missing folder, handwriting re-reading is skipped and PaddleOCR's reading is kept. `python main.py --mode
check-offline` checks the offline flag, the PaddleOCR models and the patterns file (not the handwriting, NER or
embedding models).

### 15.4 Printed/handwritten detection and TrOCR

**Detector** (`ocr/text_type_detector.py`, `FEATURE_VERSION = 2`): each line is cut out, scaled to 64 px high, ruled
lines removed, and 20 shape features measured (glyph height uniformity, shared baseline/top line, stroke width and its
variation, ink density, slant variation, PaddleOCR confidence ...). P(handwritten) comes from your trained Random Forest
(`models\classifiers\text_type\classifier.pkl`, ignored with a warning if trained on older features) or the built-in
logistic model over 12 features (fitted on about 1,900 lines). P >= 0.70 → HANDWRITTEN; P <= 0.35 → PRINTED; between →
UNKNOWN; fewer than 3 glyphs or a tiny crop → UNKNOWN with 0.0.

**TrOCR** (`ocr/handwriting_engine.py`): re-reads HANDWRITTEN lines and UNKNOWN lines with PaddleOCR confidence below
`replace_below_confidence` (0.9); crop at least 8 x 8 px; at most `max_lines_per_page` (80). Crops are greyed, ruled
lines painted out and trimmed to the line band; read in batches of 8 with beam search. The reading replaces PaddleOCR's
only if it is non-empty, at least `min_confidence` (0.5) **and** at least PaddleOCR's confidence. Both readings stay on
the region (`handwriting_text`, `paddle_text`, `recognizer: handwriting`). Log: `Handwriting model re-read N line(s),
replaced M.`

Performance: peak about 3 GB per A4 page (was over 6 GB before the memory settings); TrOCR about 25 s per handwritten
page on 2 CPU cores; warm-up 20 to 60 s. Faster: `num_beams: 1` or a lower `max_lines_per_page`. Less memory: lower
`text_det_limit_side_len` or `pdf.dpi`.

### 15.5 Configuration (`OCR_new\config\config.yaml`)

Relative paths in the file are relative to `OCR_new`.

| Section / key | Value | Meaning |
|---|---|---|
| `offline_mode` | `true` | Keep true; only `check-offline` reads it |
| `paths.output_dir` / `temp_dir` / `patterns_file` | `output` / `temp` / `extraction/patterns.yaml` | CLI output root (`ocr`, `patterns` modes); pdf2image temp; regex fields. `models_dir`, `input_dir` unused |
| `paddleocr.lang` / `ocr_version` | `en` / `PP-OCRv4` | Language and model family (PP-OCRv3 det + PP-OCRv4 rec for `en`) |
| `paddleocr.use_gpu` | `false` | CPU-only paddle |
| `paddleocr.use_textline_orientation` | `true` | Run the `cls` model |
| `paddleocr.text_det_limit_side_len` / `_type` | `1920` / `max` | Longest page side; lower = less memory, may miss small text. **Do not raise** |
| `paddleocr.text_det_thresh` / `text_det_box_thresh` | `0.2` / `0.4` | Lower keeps fainter strokes / lines (and more junk) |
| `paddleocr.text_det_unclip_ratio` | `1.6` | Margin around boxes (1.8 merged lines) |
| `paddleocr.det_model_dir`, `rec_model_dir`, `cls_model_dir` | `models/paddleocr/...` | Local model folders |
| `paddleocr.drop_score` | `0.25` | Drop lines read less confidently |
| `paddleocr.det_square_pad`, `rec_batch_num`, `rec_ratio_step`, `rec_max_ratio` | `true`, `1`, `8`, `32` | **Memory settings, leave as they are**: pad pages to 640/1280/1920 squares, read lines one at a time, widen line images to multiples of 8 x height, narrow lines longer than 32 x height |
| `text_type_detection.enabled` / `model_path` | `true` / `models/classifiers/text_type` | Off also skips TrOCR |
| `handwriting.enabled`, `model_path`, `device`, `num_beams`, `max_new_tokens`, `replace_below_confidence`, `min_confidence`, `max_lines_per_page` | `true`, `models/handwriting`, `cpu`, `3`, `64`, `0.9`, `0.5`, `80` | See 15.4 |
| `classification.model_path` / `min_model_confidence` | `models/classifiers/document` / `0.6` | Trained classifier used when at least this sure and at least as sure as the rules. Built-in rules know INVOICE, LEAVE_APPLICATION, TECHNICAL_REPORT, LETTER, CONTRACT, RESUME |
| `ner.enabled`, `model_path`, `package`, `backend` | `true`, `models/ner`, `en_core_web_sm`, `spacy` | `backend: regex` never uses spaCy |
| `preprocessing.*` | `enabled: true`, every step `false`, `threshold_method: adaptive`, `upscale_factor: 1.0`, `pdf_render_dpi: 300` | Keep `deskew` and `auto_rotate` false (they garble handwriting). Steps that move or resize the page give the detector and TrOCR wrong crops |
| `pdf.dpi` / `page_image_format` / `keep_temp_pages` | `300` / `PNG` / `false` | Render resolution; pdf2image fallback options |
| `docx.extract_embedded_images` | `true` | OCR images inside DOCX |
| `output.json_indent` | `2` | `save_txt`, `save_json`, `save_region_crops` are unused |
| `logging.*` | `INFO`, file `OCR_new\output\ocr_system.log`, 5 MB x 3 | Log settings |
| Optional, not in the file: `semantic.enabled` (true), `semantic.embedding_model`, `classification.rules_file`, `classification.categories_file`, `pdf.poppler_path` | | Read by the code if present |

### 15.6 Standalone use

Command line (every run reloads the models):

```bat
cd /d C:\CDTRS-main\OCR_new
python main.py --mode full --input input\test_doc.png
python main.py --mode full --input "C:\scans\letter from HQ.pdf"
```

Modes: `ocr` (steps 1-3), `understand` (1-3, 9), `classify` (1-3, 7), `extract` (1-3, 8), `full` (1-9), `patterns`
(regex fields on a text file or pasted text), `check-offline`. `--input` paths are relative to `OCR_new`; `--config`
picks another config file. Results go to `OCR_new\output\<file name>\`: `result.json` (everything), `ocr.txt`,
`ocr.json`, `layout.json`, `text_types.json`, `entities.json`, `extracted.json`, `classification.json`, `semantic.json`.

Python API:

```python
import sys
sys.path.insert(0, r"C:\CDTRS-main\OCR_new")
from document_intelligence import DocumentProcessor   # import before paddleocr (Windows DLL order)
processor = DocumentProcessor()                       # one processor, reuse it; not thread-safe
result = processor.process(r"C:\scans\letter.pdf", mode="full")
print(result.text, result.pages, result.entities, result.extracted_fields, result.classification)
result.save()                                          # OCR_new\output\letter\...
```

Optional local REST API (never on port 8000 while the backend runs):
`python -m uvicorn api.app:app --host 127.0.0.1 --port 8010` with `GET /health`, `POST /process`
(`{"file_path", "mode", "config_overrides"}`), `POST /ocr`, `POST /classify` and `POST /extract` (`{"text"}`). One
document at a time; CORS only localhost.

---

## 16. Fine-tuning the OCR on your own handwriting

Everything runs offline with the installed packages. You can train three things; the first is the useful one:

| What | Command | Result |
|---|---|---|
| Handwriting reading (TrOCR) | `python fineTune\training\train.py --task handwriting` | `models\handwriting\v1`, `v2` ...; made active only if it reads the test lines better than the previous model and PaddleOCR |
| Printed/handwritten detector | `python fineTune\training\train.py --task text_type` | `models\classifiers\text_type\classifier.pkl` (installed only if at least as good as the built-in; old file kept as `classifier_<date>.pkl`) |
| Document categories | `python fineTune\training\train.py --task classification` | `models\classifiers\document\` (extra information only; routing still uses department keywords) |

PaddleOCR itself is not retrained (its training tools are not in the installed package). Run everything from
`C:\CDTRS-main\OCR_new`, or double-click the helpers `fineTune\1_prepare_dataset.bat` ... `6_choose_model.bat`.

1. **Prepare.** Put scans or PDFs (300 DPI, the real variety of writers and forms) in `fineTune\datasets\raw\`
   (sub-folders fine). `python fineTune\prepare_dataset.py` cuts every page into line images in `datasets\lines\` and a
   row per line in `datasets\labels.csv` (20 to 40 s per page). Re-running only adds new files. Options: `--stats`,
   `--lines` (each file is already one line; a same-name `.txt` gives its label; `--type PRINTED`), `--min-height 20`.
2. **Label.** `python fineTune\label_tool.py` (PySide6). Type exactly what is written (including mistakes), choose
   Handwritten (Ctrl+H) or Printed (Ctrl+P), Enter to save; Ctrl+K skips unusable lines (stamps, signatures,
   unreadable); Page Up/Down moves; Ctrl+G restores PaddleOCR's reading. Skip lines you cannot read with certainty.
   Label a few hundred printed lines too. Excel also works on `labels.csv` (`text`, `type` = HANDWRITTEN / PRINTED /
   SKIP; save as CSV UTF-8; close Excel before any other step). Each line is assigned once and for ever to `train`
   (~80%), `val` (~10%) or `test` (~10%, never used for training).
3. **Train.** `python fineTune\training\train.py --task handwriting`: starts from the active model, augments
   (tilt, slant, blur, pen thickness), keeps the best epoch on `val`, stops early, scores new/previous/PaddleOCR on
   `test`, saves the next version, activates it only if better. Needs at least 20 labelled HANDWRITTEN train lines.
   About 0.5 s per line per epoch on CPU (1,000 lines x 15 epochs ≈ 2 hours). Options: `--epochs 20`, `--batch-size 4`
   (less memory), `--learning-rate 1e-5`, `--base-model trocr-small-handwritten`, `--activate`, `--no-activate`
   (defaults in `fineTune\configs\handwriting.yaml`). Log: `fineTune\checkpoints\train_handwriting.log`.
   Expected gains: 100-300 lines a first improvement; 1,000-3,000 clearly better; 5,000+ best.
4. **Evaluate.** `python fineTune\evaluation\evaluate.py --show 10` compares PaddleOCR and every model on the test
   lines (CER = character error rate, WER = word error rate; lower is better) and lists the worst lines, often label
   mistakes. Options `--split val|train|all`, `--models v1 v2`, `--report`, `--task text_type`, `--task classification
   --folder <folder>`.
5. **Use.** Restart the backend. `python fineTune\set_active_model.py` lists models (`*` = active);
   `set_active_model.py v2`, `set_active_model.py trocr-small-handwritten` (back to base) or `--off` (PaddleOCR only);
   restart again. Old versions are never deleted automatically.

Document categories: put at least 5 examples per category in `fineTune\datasets\classification\<CATEGORY>\` (PDF,
images, DOCX, TXT); scans are OCR'd once and cached as `<name>.ocr.txt`.

Datasets, labels, checkpoints and trained models are not in git: **back up `fineTune\datasets\` yourself**.

---

## 17. Tests

All tests are plain Python scripts or standard-library `unittest`; they print PASS/FAIL lines.

### 17.1 Test database and test server

The workflow, API and UI tests log in with the demo accounts and create documents. **Never run them against the live
database.** Create a separate database once and start a test backend on port 8123:

```bat
"C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h localhost -U postgres cdtrs_test
cd /d C:\CDTRS-main\backend
set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
set UPLOAD_DIR=./uploads_test
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

`--no-mail` is required: otherwise the test server would sync the real DS mailbox into the test database (and, with
POP3, record those messages as imported in the shared state file) and could send e-mails. `set` only applies to that
window and wins over `backend\.env`.

If `seed_data.json` has been emptied for production, seed the test database from the demo copy first, and copy the
real file back before the live server restarts:

```bat
copy /y data\seed_data.json data\seed_data_real.json
copy /y data\seed_data_demo.json data\seed_data.json
python reset_db.py --confirm            (with the cdtrs_test DATABASE_URL set; never add --wipe-uploads here)
copy /y data\seed_data_real.json data\seed_data.json
```

### 17.2 Running them (second window, same `set` lines)

| Command (folder) | Tests |
|---|---|
| `backend> python tests\test_full_workflow.py` | Workflow engine end to end, directly against the database (no server) |
| `backend> python tests\test_api_workflow.py [base url]` | Full HTTP workflow, default `http://127.0.0.1:8123` |
| `backend> python tests\test_new_fixes.py [base url]` | Sept 2026 fixes: verified Director instruction opens routing, HOD sees only own department, Director edits a remark, invalid dates refused, intake attachments |
| `backend> python tests\test_context_audit.py` | Work-context and authorization audit (`CDTRS_API_URL`, default port 8123) |
| `frontend> python tests\test_ui_smoke.py` | Every page in every context, headless, against port 8123 |
| `backend> python tests\test_director_detection.py -v` | Director-instruction detector unit tests (no database, no models) |

### 17.3 Mail diagnostics (real mail servers)

| Command | What |
|---|---|
| `python tests\test_intranet_mail.py [--send --recipient x@y] [--incoming-only] [--all]` | POP3 + SMTP diagnostic (12.5); reads most recent messages without touching the UIDL state; sends only after typing SEND |
| `python tests\test_mail_service.py` | Which provider `MAIL_CHANNEL` selects; contacts no server |
| `python tests\test_provider.py recipient@example.com` | Sends one real Outlook e-mail |
| `python tests\test1.py` | Graph diagnostic with the personal token; sends nothing |
| `python tests\outlook_test.py` | Static checks of the progress-attachment rules in `mail\service.py`; sends nothing |

### 17.4 OCR engine (no database)

```bat
cd /d C:\CDTRS-main\OCR_new
python -m unittest discover -s testing -t . -v
python -m unittest testing.test_text_type -v          (one file)
```

130 tests in `test_document`, `test_preprocessing`, `test_ocr` (PaddleOCR tests skipped when models are missing),
`test_text_type`, `test_handwriting`, `test_semantic`, `test_classification`, `test_extraction`, `test_patterns`,
`test_document_intelligence`, `test_finetune`.

---

## 18. Deployment on the office network, backup and restore

### 18.1 Server PC

1. `HOST=0.0.0.0` and `PORT=8000` in `backend\.env`.
2. Allow the port (Administrator Command Prompt), once:

   ```bat
   netsh advfirewall firewall add rule name="CDTRS backend" dir=in action=allow protocol=TCP localport=8000
   netsh advfirewall firewall show rule name="CDTRS backend"
   ```

   Only the backend port is opened; PostgreSQL (5432) does not need to be reachable from the LAN.
3. Note the server's IPv4 address (`ipconfig`) and ask for a fixed IP or DHCP reservation; if it changes, every client
   stops connecting.
4. Start `start_backend.bat` and keep the window open; the server PC must not sleep. (There is no Windows service
   wrapper; to start it automatically, a Task Scheduler task "At log on" running `start_backend.bat` is one option.)
5. Check `http://127.0.0.1:8000/health` on the server and `http://<server-ip>:8000/health` from a client; in
   PowerShell `Test-NetConnection <server-ip> -Port 8000` must give `TcpTestSucceeded : True`.

### 18.2 Client PCs

Either give them the built `CDTRS.exe` folder with its `.env` (section 8), or install Python 3.12 64-bit, copy the
project to `C:\CDTRS-main`, run `python -m pip install -r frontend\requirements.txt`, create `frontend\.env` with
`CDTRS_API_URL=http://<server-ip>:8000/api/v1`, and use `start_frontend.bat`. If an old `C:\CDTRS-main\.env` from
earlier versions exists, move its settings into `backend\.env` / `frontend\.env` and rename it (the app reads a
current-folder `.env` when `frontend\.env` is missing).

### 18.3 Backup

```bat
cd /d C:\CDTRS-main\backend
python backup_database.py                       (or double-click scripts\backup_database.bat)
python backup_database.py --dest D:\cdtrs_backups --keep 30
python backup_database.py --no-uploads
```

It writes `cdtrs_db_YYYYmmdd_HHMM.dump` (whole database, pg_dump custom format; password from `DATABASE_URL`; pg_dump
found on PATH or in `C:\Program Files\PostgreSQL\<version>\bin`) and `cdtrs_uploads_YYYYmmdd_HHMM.zip` (all of
`backend\uploads`, including the POP3 state) into `C:\CDTRS-main\backups\`, keeping the newest `--keep` (default 14) of
each. Copy backups to another disk or PC regularly. Also back up `backend\.env`, your `seed_data.json`,
`OCR_new\models\handwriting\` and `OCR_new\fineTune\datasets\` separately.

**Daily backup with Task Scheduler:** Create Basic Task > Daily > Start a program `C:\CDTRS-main\scripts\backup_database.bat`
(options in Add arguments). Tick "Open the Properties dialog" and set "Stop the task if it runs longer than 1 hour",
because on failure the batch file waits at `pause`. Or run python directly: program = full path of `python.exe`,
arguments `backup_database.py --keep 30`, Start in `C:\CDTRS-main\backend`. Run it under the Windows account that has
Python (it is installed per user). A failed run creates no new `.dump`.

### 18.4 Restore (replaces the current data)

```bat
rem 1. stop the backend
"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --clean --if-exists -h localhost -U postgres -d cdtrs C:\CDTRS-main\backups\cdtrs_db_YYYYmmdd_HHMM.dump
rem    (if the database does not exist: "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h localhost -U postgres cdtrs)
rem 2. move the current backend\uploads aside, then:
powershell -Command "Expand-Archive -Path C:\CDTRS-main\backups\cdtrs_uploads_YYYYmmdd_HHMM.zip -DestinationPath C:\CDTRS-main\backend\uploads"
rem 3. start the backend (seeding runs as usual)
```

### 18.5 Go-live checklist

- [ ] `backend\.env`: real `DATABASE_URL`, random `SECRET_KEY`, `HOST=0.0.0.0`
- [ ] Firewall rule added, fixed server IP, `/health` reachable from a client
- [ ] Real departments (with descriptions and keywords) and accounts imported; `seed_data.json` emptied; demo data gone
- [ ] Handwriting model downloaded (`set_active_model.py` shows `*`)
- [ ] Mail tested (12.5); `OVERRIDE_TEST_RECIPIENT_EMAIL` emptied; backend restarted; users have e-mail addresses
- [ ] Every test backend started with `--no-mail`
- [ ] Daily backup scheduled and a restore tried once
- [ ] Clients have `CDTRS.exe` (or Python + `frontend\.env`) pointing at the server

---

## 19. Known limitations and loose ends

These are true of the code as of 13 Nov 2026. None of them blocks normal use.

| Area | Limitation |
|---|---|
| Mail template | `backend\.env.example` still documents the old `INTRANET_IMAP_*` keys and port 993. They still work as fallbacks for host, security and auth, but the port defaults to 995/110 and `INTRANET_IMAP_PORT` is ignored. New installs should use the `INTRANET_POP3_*` keys (6.1). |
| Mail labels | Messages and labels still say "IMAP" or "Outlook" in places: the sync result says "Intranet IMAP ... not configured" / "synced ... from DS Outlook mailbox", the endpoint is `/intake/sync-outlook`, and every synced message is stored with `source_type = OUTLOOK`, also for intranet mail. |
| Mail attachments | Synced mail attachments are recorded with `uploaded_by_user_id = 1` (assumes user id 1 exists). |
| POP3 | Mail is never deleted from the server, so the mailbox grows; the server's own retention applies. Without UIDL support every message is offered at each sync (filtered by Message-ID). Losing the state file re-offers all messages (12.3). |
| MAIL_CHANNEL | A missing line means `outlook`, not off. With a leftover `backend\mail\.token_cache.json`, Outlook then counts as configured. |
| WebSocket | `/api/v1/ws` needs no token: anyone on the LAN who can reach the port can watch event summaries. |
| In-memory events | `/events/recent` keeps the last 100 events in memory only. |
| System Configuration | The priority countdown thresholds and reminder e-mail template saved by Admin > System Configuration (`priority_*_days`, `reminder_email_*`) are stored but not read anywhere. Likewise `mail.reminder_enabled`, `mail.reminder_lead_days`, `mail.from_address` and the `mail.template.*` settings. The deadline scan uses a fixed "overdue or due within 2 days". |
| Priority page | `frontend\pages\priority.py` (deadlines and priority monitor) is only used by the UI smoke test; it is not in any menu. |
| Reminders | The first automatic deadline scan runs one hour after start (not at start). |
| Database | No migration tool; new columns must be added to `database._ADDED_COLUMNS`. |
| OCR | One document at a time; Paddle memory is freed only when the process ends (restart the backend if it grows); CPU only. |
| Swagger UI | Blank without internet (CDN). |
| Packages | `passlib` and `users.preferred_mail_channel` are unused leftovers. |
| Build | No `.spec` file, no app icon, and no Windows build was run while writing this guide (8.4). |
| Docs references | Some code comments and `.bat` files still mention the old README files (e.g. "see README.md" in `OCR_new\fineTune\*.bat`, "Section 23 of README.md" in `document_intelligence.py`, "See OUTLOOK_INTEGRATION_GUIDE.md" in `backend\.env.example`). This README now covers those topics. |

---

## 20. Troubleshooting

When something fails, first find the layer: network, mail server login, configuration, database, OCR, or desktop app.

| Problem | What to do |
|---|---|
| App says it cannot reach the server | Is the `start_backend.bat` window open? Check `CDTRS_API_URL` in `frontend\.env` (or `_internal\.env` for the exe), the firewall rule, and `http://<server>:8000/health` |
| Client browser times out on `/health` | Firewall rule missing or client on another network: 18.1 |
| "Connection refused" from a client | Backend not running, `HOST=127.0.0.1`, or a different `PORT` |
| Works on the server but not on clients | Wrong or changed IP; firewall |
| App still connects to 127.0.0.1 | `frontend\.env` missing or `CDTRS_API_URL` not in it; for the exe see 8.3 |
| All clients suddenly disconnect | Backend window closed, or the server PC slept / restarted |
| `password authentication failed for user "postgres"` | Fix the password in `DATABASE_URL` |
| Backend shows database errors at start, `/health` fails | PostgreSQL service stopped, or wrong `DATABASE_URL` (`[STARTUP WARN]`) |
| `[SECURITY WARN] SECRET_KEY` | Set a random `SECRET_KEY` |
| Backend closes during the first OCR, or app says "WebSocket error: The remote host closed the connection" | Windows DLL order (7.1); start with `start_backend.bat`, use 64-bit Python 3.12, keep the import order in `main.py` / `ocr_adapter.py` |
| First OCR is slow | Warm-up still running (20 to 60 s) |
| Out of memory, PC very slow, backend disappears during OCR | Keep the memory settings; lower `text_det_limit_side_len` (1280) or `pdf.dpi` (200); do not run the OCR CLI/API on the same PC meanwhile; restart the backend |
| `PaddleOCR model files not found` / `[MISSING]` | Restore `OCR_new\models\paddleocr` from git, or `python setup_models.py` |
| Handwriting read badly / never `recognizer: handwriting` | `set_active_model.py`; `download_base_model.py`; `handwriting.enabled` and `text_type_detection.enabled` true; lines marked PRINTED are not re-read (train the detector); restart |
| `active.txt names 'x', which is not a model folder` | `python fineTune\set_active_model.py <name>` |
| `Text-type classifier ... trained with older features` | Retrain with `--task text_type` (built-in model used meanwhile) |
| Only regex entities found | `python -c "import spacy; spacy.load('en_core_web_sm')"`; check `ner.enabled` / `ner.backend` |
| `semantic.json` embedding is null | `models\embeddings\model\` missing; restore from git |
| Wrong department suggested | Improve that department's description and keywords (11.3) |
| Python not found by the `.bat` files | Install Python 3.12 or set `CDTRS_PYTHON` |
| `test_intranet_mail.py` says `backend\.env was not found` | File missing or saved as `.env.txt`: `dir /a C:\CDTRS-main\backend\.env*` |
| Configuration check shows `MISSING` | Value empty, still commented out, or in an old root `.env` |
| POP3/SMTP connection fails and `Test-NetConnection` is False | Fix network / VPN / firewall first |
| Errors about SSL/TLS or "wrong version number" | Security mode does not match the port (e.g. `ssl` on a STARTTLS port) |
| "certificate verify failed" | `INTRANET_ALLOW_SELFSIGNED=true` (trusted internal server only) |
| POP3 login fails | Check `DS_MAIL_USER`/`DS_MAIL_PASS` (not the CDTRS account); try the full address as user name |
| SMTP login fails or sender refused | Check `CDTRS_MAIL_*`; use a `CDTRS_SENDER_EMAIL` that account may send as |
| Sync Now says "not configured" | `MAIL_CHANNEL` wrong, `off` or `--no-mail`, a required value missing (including an empty `CDTRS_SENDER_EMAIL=` line), or no restart |
| Sync Now says "Mailbox sync is a DS action." | Switch to the DS context |
| New mail never appears in the live Inbox | Another backend with mail on (test server, second PC) imported it into its own database: always `--no-mail` for test servers. With POP3, the message's UIDL may now be "seen" in the shared state file; remove that UIDL from `pop3_uidl_state.json` (backend stopped) to fetch it again |
| A message is never imported again after I deleted it in CDTRS | Its UIDL is in the state file; see the previous row |
| Outlook: `Personal token refresh HTTP 400 ... invalid_grant` | Run `python mail\auth_personal.py` again |
| Outlook: 401/403 from Graph (organisation) | Admin consent, `Mail.ReadWrite`/`Mail.Send`, access policy, or expired secret |
| Outlook: imported messages stay unread | Needs `Mail.ReadWrite`; personal: sign in again |
| No notification e-mails | Account has no address; provider not configured; `mail.notifications_enabled` is not `true` |
| "already registered as document" (409) | That e-mail or file is already a document; open it instead |
| Opening a synced attachment gives 403 | Only the DS or Admin context may open unregistered intake attachments |
| `Stored file is missing from disk` | A file under `backend\uploads` was moved or renamed; restore it from backup |
| Swagger `/docs` is blank | No internet on that PC; use `/openapi.json` |
| Built exe closes at once / `No module named 'ui'` / no styling | Section 8.4 |

---

## 21. Demo accounts and departments

Created from `backend\data\seed_data.json`: 15 departments, 9 system users and 8 employees (17 accounts). Change or
remove them before real use (14.2).

| Username | Password | Work contexts |
|---|---|---|
| `corp` | `cdtrs@admin` | Admin |
| `director` | `cdtrs@director` | Director |
| `exec_user` | `cdtrs@ds` | DS (Director's Secretary) |
| `tso_user` | `cdtrs@tso` | TSO (Executive Office) + Employee Engineering & Innovation |
| `hod_prod` | `cdtrs@hod` | HOD Product Strategy + HOD Enterprise Solutions |
| `hod_eng` | `cdtrs@hod` | HOD Engineering & Innovation + HOD Customer Experience |
| `hod_cit` | `cdtrs@hod` | HOD Information Technology + HOD Talent Management |
| `hod_corp` | `cdtrs@hod` | HOD Corporate Administration, Finance & Accounts, Business Support, Operations & Procurement |
| `hod_ptc` | `cdtrs@hod` | HOD Partnerships & Technology, Product Consulting, Corporate Research, Market & Business Transformation |
| `emp_anil` | `cdtrs@emp` | Employee Product Strategy |
| `emp_vikram` | `cdtrs@emp` | Employee Product Strategy + HOD Enterprise Solutions |
| `emp_sneha` | `cdtrs@emp` | Employee Engineering & Innovation + HOD Customer Experience |
| `emp_rahul` | `cdtrs@emp` | Employee Engineering & Innovation + HOD Product Strategy |
| `emp_sunil` | `cdtrs@emp` | Employee Information Technology + HOD Talent Management |
| `emp_pooja` | `cdtrs@emp` | Employee Corporate Administration + HOD Finance & Accounts |
| `emp_kamble` | `cdtrs@emp` | Employee Finance & Accounts |
| `emp_rajesh` | `cdtrs@emp` | Employee Operations & Procurement + HOD Business Support |

Department codes: PROD (Product Strategy), ENG (Engineering & Innovation), EXEC (Executive Office), ENT (Enterprise
Solutions), CX (Customer Experience), CR (Corporate Research), MBT (Market & Business Transformation), PTN
(Partnerships & Technology), CONS (Product Consulting), TECH (Information Technology), OPS (Operations & Procurement),
TALENT (Talent Management), CORP (Corporate Administration), FIN (Finance & Accounts), SUPPORT (Business Support).
Each has a description and routing keywords in `seed_data.json`.
