# CDTRS Backend

Centralised Document Tracking and Routing System - server part.
FastAPI + SQLAlchemy + PostgreSQL, with the offline OCR engine `OCR_new` running inside the server process.

```text
API base URL     http://<server>:8000/api/v1          (on the server itself: http://127.0.0.1:8000/api/v1)
Health check     http://<server>:8000/health
Swagger UI       http://<server>:8000/docs            (also /redoc; needs internet, see 6.13)
WebSocket        ws://<server>:8000/api/v1/ws
Login            POST /api/v1/auth/login  ->  access_token (JWT, HS256)
Request headers  Authorization: Bearer <access_token>
                 X-Work-Context-Id: <id of the work context in use>
Settings         backend\.env   (template: backend\.env.example)
Project folder   C:\CDTRS-main  (deployment PC, Windows, Python 3.12, PostgreSQL 18, database "cdtrs")
```

Contents

1. [Overview and file structure](#1-overview-and-file-structure)
2. [Technologies](#2-technologies)
3. [Setup on Windows](#3-setup-on-windows)
4. [Architectural principles](#4-architectural-principles)
5. [Database](#5-database)
6. [API reference](#6-api-reference)
7. [Intake, OCR and routing suggestions](#7-intake-ocr-and-routing-suggestions)
8. [Mail integration](#8-mail-integration)
9. [Admin scripts](#9-admin-scripts)
10. [Tests](#10-tests)
11. [Seeded test accounts](#11-seeded-test-accounts)

---

## 1. Overview and file structure

The backend is the only server in CDTRS. It:

- keeps the document register and the complete workflow history in PostgreSQL (database `cdtrs`);
- offers a REST API under `/api/v1` and a WebSocket that pushes live events to the desktop clients;
- enforces the workflow rules and decides what each person may see and do (work contexts);
- stores uploaded and mailed files under `backend\uploads`;
- reads documents with the offline OCR engine `OCR_new` and suggests departments (advisory only);
- optionally reads the DS mailbox and sends notification e-mails (Outlook or the office intranet mail server).

How the parts fit together:

```text
PySide6 desktop app (frontend\, started by main.py / start_frontend.bat)
        |  HTTP /api/v1  +  WebSocket /api/v1/ws        (address: CDTRS_API_URL in frontend\.env)
        v
FastAPI backend (backend\, started by run_server.py / start_backend.bat)
        |-- PostgreSQL 18, database "cdtrs"        (DATABASE_URL in backend\.env)
        |-- backend\uploads                        (UPLOAD_DIR)
        |-- OCR_new engine, imported in-process     (backend\ocr_adapter.py; models are local, no internet needed)
        '-- mail server, optional                  (Outlook / Microsoft Graph, or intranet IMAP + SMTP)
```

- The **frontend** never touches the database and does not run OCR itself. The intake screen sends the file to
  `POST /api/v1/intelligence/analyze`, so the OCR models are loaded once, on the server.
- **OCR_new** (project folder `OCR_new\`) is imported directly by `backend\ocr_adapter.py`; the backend adds
  `OCR_new` to the Python path itself. See `..\OCR_new\README.md` for the engine, its models and fine-tuning.

### File structure

`backend\`

| File | Purpose |
|---|---|
| `main.py` | FastAPI application: every HTTP endpoint and the WebSocket, login and work-context dependencies, upload checks (size, file type, duplicates), start-up tasks (tables, columns, seeding, OCR warm-up, mailbox sync loop, hourly reminder loop). |
| `workflow.py` | The workflow engine: routing (branches), Director review and the Director gate, work items and stages, progress, HOD validation, branch and document closure, reopening, visibility, inbox, dashboard, deadline reminders, in-app notifications and the e-mail copy. |
| `crud.py` | Data access outside the workflow: password hashing (bcrypt), JWT tokens, work contexts, TSO designation, intake messages, document creation and metadata edits, attachments (SHA-256 checksum, unique file names, duplicate lookup), notifications, manual reminders, admin functions, system settings, seeding (`apply_seed_payload`), the WebSocket event manager. |
| `models.py` | SQLAlchemy models: all 23 tables and 15 enums. |
| `schemas.py` | Pydantic request and response models. |
| `serializers.py` | Turns database objects into API responses. |
| `database.py` | Loads `backend\.env`, creates the engine and sessions, adds `CRITICAL` to an old `priority_enum`, adds columns that older databases lack. |
| `intelligence.py` | OCR of registered documents, storing extracted fields, DS field verification, department ranking and routing suggestions, intake analysis (`/intelligence/*`), OCR warm-up. |
| `ocr_adapter.py` | The backend's single entry point into OCR_new: loads the engine once, runs one OCR at a time (lock), detects handwritten Director instructions, semantic similarity. Imports torch before PaddlePaddle (Windows DLL order). |
| `run_server.py` | Starts uvicorn with HOST and PORT from `backend\.env`; used by `start_backend.bat`. |
| `import_from_csv.py` | Imports departments and accounts from CSV or XLSX files (section 9). |
| `import_employees.py` | Older tool: rewrites the `employees` list in `data\seed_data.json` from a roster file. |
| `reset_db.py` | Destructive: drops all tables and enum types, recreates the schema, seeds. |
| `clear_documents.py` | Deletes all documents and workflow data; keeps accounts, departments, contexts and settings. |
| `reset_password.py` | Sets one user's password from the command line. |
| `backup_database.py` | Database dump (pg_dump) plus a zip of the uploads, with rotation. |
| `seed.py` | Older setup script: creates missing tables and adds the missing records of `data\seed_data.json` (the server does this itself on every start), then lists the accounts with their seed passwords. |
| `__init__.py` | Empty. Makes `backend` importable as a package (`intelligence.py` imports `backend.ocr_adapter`). |
| `.env.example` | Template for `backend\.env`. |
| `requirements.txt` | Pinned package versions (section 2). |
| `uploads\` | Created at run time: stored documents and attachments (git-ignored). |

`backend\mail\`

| File | Purpose |
|---|---|
| `__init__.py` | Exports the provider classes and `mail_service`; silences a harmless `requests` version warning. |
| `base.py` | Abstract `BaseMailProvider` and the e-mail data classes. |
| `service.py` | `MailService`: chooses the provider (`MAIL_CHANNEL`), syncs the DS mailbox into the intake list, sends workflow notification e-mails with attachments, `OVERRIDE_TEST_RECIPIENT_EMAIL`. |
| `outlook_provider.py` | Microsoft Graph provider (personal mailbox via token cache, or organisation via client credentials). |
| `intranet_provider.py` | Office mail server provider: IMAP for the DS mailbox (incoming), SMTP for the CDTRS mailbox (outgoing). |
| `auth_personal.py` | One-time device-code sign-in for a personal Outlook mailbox; writes `mail\.token_cache.json` (git-ignored). |

`backend\tests\` (plain Python scripts, see section 10)

| File | Purpose |
|---|---|
| `test_full_workflow.py` | Workflow engine end to end, directly against the database in `backend\.env`. |
| `test_api_workflow.py` | Full HTTP workflow against a running server (default `http://127.0.0.1:8123`). |
| `test_context_audit.py` | Work-context and authorization audit over HTTP (default `http://127.0.0.1:8123`, or `CDTRS_API_URL`). |
| `test_director_detection.py` | Unit tests for the handwritten Director-instruction detector (`python tests\test_director_detection.py`); no database or OCR models needed. |
| `test_intranet_mail.py` | Intranet IMAP/SMTP diagnostic; sends an e-mail only with `--send`. |
| `test_mail_service.py` | Shows which provider `MAIL_CHANNEL` selects and whether it is configured; contacts no mail server. |
| `test_provider.py` | Sends one real e-mail through Outlook to the address given as argument. |
| `outlook_test.py` | Static checks of the progress-attachment rules in `mail\service.py`; sends nothing. |
| `test1.py` | Microsoft Graph diagnostic with the cached personal token (`/me`, mail folders, Inbox); sends nothing. |

`backend\data\`

| File | Purpose |
|---|---|
| `seed_data.json` | 15 departments (each with `description` and `keywords`), 9 system users and 8 employees. Records that do not exist yet are created on every server start. |
| `import_templates\departments.csv`, `accounts.csv` | Header-only templates for `import_from_csv.py`. |
| `import_templates\departments_example.csv`, `accounts_example.csv` | The same with filled-in example rows. |
| `import\` | You create it: default input folder of `import_from_csv.py` (git-ignored, holds real staff lists). |

---

## 2. Technologies

Python **3.12** (64-bit) and **PostgreSQL 18**. All versions below are the pins in `backend\requirements.txt`, which are
identical to the installed package list `imp.txt` in the project root. Do not upgrade them and do not install other
packages.

| Package | Version | Used for |
|---|---|---|
| fastapi | 0.111.0 | REST API, WebSocket, Swagger UI at `/docs` |
| starlette | 0.37.2 | ASGI toolkit under FastAPI |
| uvicorn | 0.30.1 | ASGI server (`run_server.py`) |
| websockets | 12.0 | WebSocket support in uvicorn |
| pydantic / pydantic-core | 2.8.2 / 2.20.1 | Request and response validation |
| python-multipart | 0.0.9 | Multipart file uploads |
| sqlalchemy | 2.0.31 | ORM |
| psycopg2-binary | 2.9.9 | PostgreSQL driver |
| python-dotenv | 1.0.1 | Loads `backend\.env` |
| bcrypt | 4.0.1 | Password hashing (used directly) |
| python-jose | 3.3.0 | JWT login tokens (HS256) |
| cryptography | 42.0.8 | Crypto backend |
| passlib | 1.7.4 | Pinned; not imported by the backend code |
| requests | 2.32.3 | Microsoft Graph calls (Outlook), frontend HTTP client |
| pip-system-certs | 4.0 | Lets Python use the Windows certificate store for HTTPS |
| numpy / pandas | 1.26.4 / 2.2.2 | Numeric work; pandas is pre-loaded at start-up (Windows DLL order) |
| paddlepaddle / paddleocr | 2.6.2 / 2.8.1 | OCR (CPU) inside OCR_new |
| torch / transformers / tokenizers | 2.13.0 / 5.15.0 / 0.22.2 | Handwriting recognition (TrOCR) in OCR_new |
| sentence-transformers | 5.6.1 | Semantic similarity (department matching) |
| spacy | 3.8.14 | Named-entity extraction in OCR_new |
| scikit-learn / scipy / scikit-image | 1.9.0 / 1.17.1 / 0.24.0 | Classifiers, TF-IDF keywords, image processing in OCR_new |
| opencv-python / Pillow / shapely / pyclipper | 4.10.0.84 / 10.4.0 / 2.0.5 / 1.3.0.post5 | Image handling and text-box geometry for OCR |
| PyMuPDF / pypdf / pypdfium2 / pdfplumber | 1.24.9 / 4.3.1 / 4.30.0 / 0.11.9 | PDF reading |
| python-docx | 1.2.0 | Word (.docx) reading |
| PyYAML | 6.0.2 | OCR_new configuration |
| python-dateutil | 2.9.0.post0 | Date normalisation in OCR_new |
| pdf2image | 1.17.0 | PDF page rendering in OCR_new |
| torchvision / sentencepiece | 0.28.0 / 0.2.2 | Installed alongside torch / transformers (not imported directly by CDTRS code) |
| huggingface_hub | 1.27.0 | One-time download of the handwriting base model (`OCR_new\fineTune\download_base_model.py`) |
| editdistance | 0.8.0 | Character error rate in OCR_new fine-tuning |
| openpyxl | 3.1.5 | Reading `.xlsx` files in `import_from_csv.py` |
| pyarrow | 24.0.0 | Pre-loaded at start-up (Windows DLL order, see 3.5) |
| PySide6 | 6.7.2 | Desktop frontend (listed here because the requirement files are shared) |

The project-wide `requirements.txt` in the project root is the complete list for the whole system (backend, frontend
and OCR_new); it also includes the spaCy English model `en_core_web_sm` 3.8.0, installed from its official release
file.

---

## 3. Setup on Windows

All commands are for the Windows Command Prompt, starting in `C:\CDTRS-main`.

### 3.1 Python 3.12 and packages

Python 3.12 is installed per user at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, and all packages of
`imp.txt` (project root) are already installed. Check:

```bat
python --version
```

If `python` is not found, use `py -3.12` or the full path above in the commands of this document.
The `.bat` files find Python by themselves (`scripts\find_python.bat`: the `CDTRS_PYTHON` variable, the per-user
install, `C:\Program Files\Python312`, or `py -3.12`).

Reinstalling is normally not needed. The commands below only reinstall the same pinned versions - the complete set
for the whole system from the project root, or the backend's own list:

```bat
cd /d C:\CDTRS-main
python -m pip install -r requirements.txt

cd /d C:\CDTRS-main\backend
python -m pip install -r requirements.txt
```

### 3.2 Create the PostgreSQL database

With psql (installed with PostgreSQL; use the full path if it is not on PATH):

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres
```

```sql
CREATE DATABASE cdtrs;
\q
```

Or in pgAdmin: right-click **Databases** > **Create** > **Database...**, name `cdtrs`, owner `postgres`, **Save**.

Only the empty database is needed. The backend creates the tables and seeds the data itself (3.5).

### 3.3 Create backend\.env

```bat
cd /d C:\CDTRS-main\backend
copy .env.example .env
notepad .env
```

`backend\.env` is the only settings file of the backend (there is no project-wide `.env`). It is loaded explicitly
from the backend folder by `database.py`, `run_server.py`, `backup_database.py` and `tests\test_intranet_mail.py`,
so it works whatever the current folder is. It holds passwords and is git-ignored. Restart the backend after
every change. A variable set in the Command Prompt (`set NAME=value`) takes precedence over the file.

At minimum set `DATABASE_URL` (the postgres password) and `SECRET_KEY`. Generate a key with:

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Key | Template value | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:CHANGE_ME@localhost:5432/cdtrs` | PostgreSQL connection: `postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>`. `postgres://` and `postgresql://` are converted automatically. Special characters in the password must be URL-encoded (for example `@` as `%40`). |
| `HOST` | `0.0.0.0` | Address the server listens on (`run_server.py`). `0.0.0.0` = other PCs on the LAN can connect; `127.0.0.1` = this PC only. |
| `PORT` | `8000` | Port of the server. |
| `SECRET_KEY` | `CHANGE_ME_TO_A_LONG_RANDOM_VALUE` | Signs the login tokens. Use a long random value. Changing it logs everybody out. If the key is missing or still contains "change" (like the template value), the server prints `[SECURITY WARN] ...` at start; a missing key falls back to a built-in default - never run like that. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | How long a login stays valid (480 = 8 hours, also the default when the key is missing). |
| `UPLOAD_DIR` | `./uploads` | Where files are stored, relative to `backend\` (`run_server.py` switches to the backend folder). Uploaded files go to `uploads\<year>\<document id>\`, mailbox attachments to `uploads\<year>\intake_<message id>\`. |
| `MAX_FILE_SIZE` | `20971520` | Largest accepted upload in bytes (20 MB). Larger files get HTTP 413. |
| `CORS_ORIGINS` | `*` | `*` or a comma-separated list of allowed browser origins. The desktop app does not need it. |
| `MAIL_CHANNEL` | `intranet` (commented out) | Mail system: `outlook`, `intranet`, or `off` (also `none` / `disabled`) = no mailbox sync and no notification e-mails. If the line is missing the code uses `outlook`. See section 8. |
| `OUTLOOK_AUTH_MODE` | `personal` / `organizational` | Notes which Outlook mode is used. The current code does not read it to decide: a token cache file means personal mode; tenant, client id, secret and mailbox mean organisational mode. |
| `OUTLOOK_TENANT_ID` | GUID | Organisational mode: Entra ID tenant. |
| `OUTLOOK_CLIENT_ID` | GUID | Organisational mode: app registration. When empty, Microsoft's public client id is used. |
| `OUTLOOK_CLIENT_SECRET` | secret | Organisational mode: client secret. |
| `OUTLOOK_MAILBOX` | `ds.office@your-domain.gov.in` | DS mailbox that receives documents. |
| `OUTLOOK_FOLDER` | `Inbox` | Mail folder that is read. |
| `INTRANET_IMAP_HOST` | `192.168.1.100` | Office mail server for the DS mailbox (incoming). |
| `INTRANET_IMAP_PORT` | `993` | IMAP port. |
| `INTRANET_IMAP_SECURITY` | `ssl` | `ssl`, `starttls` or `plain`. |
| `INTRANET_IMAP_AUTH` | `password` | Login method; only `password` is supported. |
| `DS_MAIL_USER` | `ds_office@intranet.gov.in` | DS mailbox user name. |
| `DS_MAIL_PASS` | (empty) | DS mailbox password. |
| `IMAP_TIMEOUT` | `20` | IMAP network timeout in seconds. |
| `INTRANET_SMTP_HOST` | `192.168.1.100` | Office mail server for sending (the CDTRS mailbox). |
| `INTRANET_SMTP_PORT` | `587` | SMTP port. |
| `INTRANET_SMTP_SECURITY` | `starttls` | `ssl`, `starttls` or `plain`. |
| `INTRANET_SMTP_AUTH` | `password` | Login method; only `password` is supported. |
| `CDTRS_MAIL_USER` | `cdtrs@intranet.gov.in` | CDTRS mailbox user name. |
| `CDTRS_MAIL_PASS` | (empty) | CDTRS mailbox password. |
| `CDTRS_SENDER_EMAIL` | `cdtrs@intranet.gov.in` | Sender address; defaults to `CDTRS_MAIL_USER`. |
| `CDTRS_SENDER_NAME` | `CDTRS` | Sender display name. |
| `INTRANET_ALLOW_SELFSIGNED` | `true` | `true` accepts the mail server's self-signed certificate (certificate and host-name checks are switched off). Default `false`. |
| `OVERRIDE_TEST_RECIPIENT_EMAIL` | (empty) | Testing: every notification e-mail goes to this one address. Empty, `none`, `false` or `off` = normal delivery. |

One more optional key, not in the template: `LOG_LEVEL` (default `info`) sets the uvicorn log level for `run_server.py`.

### 3.4 Start the backend

Double-click `C:\CDTRS-main\start_backend.bat`. It checks that `backend\.env` exists, then runs
`backend\run_server.py` with HOST and PORT from `backend\.env`. Keep the window open while CDTRS is in use; closing
it stops the server. Options are passed through:

```bat
start_backend.bat --port 8123 --host 127.0.0.1
```

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
| `--no-mail` | off | Sets `MAIL_CHANNEL=off` for this run: no mailbox sync, no e-mails. Always use it for test servers (section 10). |

Plain uvicorn also works, from the backend folder (so that `UPLOAD_DIR=./uploads` resolves to `backend\uploads`):

```bat
cd /d C:\CDTRS-main\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Never add `--reload`: it starts a second process and loads the OCR models twice.

### 3.5 What happens on start

1. **Tables**: every missing table of the 23 is created (existing tables are never changed or emptied).
2. **Old databases**: `CRITICAL` is added to `priority_enum` if missing, and the columns
   `routing_suggestions.ranked_departments`, `departments.description` and `departments.keywords` are added if
   missing (`[STARTUP] Added missing column ...` in the window).
3. **Seeding** from `data\seed_data.json`, on every start (`[CDTRS SEED] 15 departments, 17 accounts, ... work contexts.`).
   Seeding only creates what is missing: departments, staff-directory records, accounts and default system
   settings. Work contexts are only given to accounts created in that same run. It never changes existing
   accounts, passwords or work contexts, so an Admin's edits, deactivated accounts and revoked contexts stay as they
   are. An existing department only gets the file's description and keywords if its own are empty. The file's TSO
   (`tso_user`) is designated only if that account was just created and no TSO is active; an existing `tso_user` is
   never re-designated. Everything is written in one transaction.
4. **OCR warm-up** in a background thread: PaddleOCR, the NER and the embedding models are loaded so the first upload
   does not wait. The first OCR is ready after about 20-60 seconds; the API answers meanwhile.
5. **Background loops**: DS mailbox sync every 30 seconds (only when the selected mail provider is configured and
   `MAIL_CHANNEL` is not `off`) and a deadline-reminder scan every hour.

Start-up problems such as a wrong `DATABASE_URL` are printed as `[STARTUP WARN] ...`; the server keeps running, but
`/health` fails until the database is reachable.

On Windows, native libraries must load in a fixed order or the process crashes silently about 45 seconds after start
(the desktop app then reports "WebSocket error: The remote host closed the connection"). This is handled in code:
`main.py` imports pyarrow and pandas first, and `ocr_adapter.py` (and `OCR_new\utils\native_libs.py`) import torch
before PaddlePaddle.

### 3.6 Health check

Open `http://127.0.0.1:8000/health` in a browser, or:

```bat
curl http://127.0.0.1:8000/health
```

```json
{"status": "healthy", "documents": 0, "open_branches": 0, "open_work_items": 0}
```

`/health` queries the database. `GET /` answers `{"service": "CDTRS", "version": "3.0.0", "status": "ok"}` without it.

### 3.7 Access from other PCs (LAN / intranet)

1. `HOST=0.0.0.0` in `backend\.env`.
2. Allow the port in the Windows Firewall (Command Prompt **as Administrator**):

   ```bat
   netsh advfirewall firewall add rule name="CDTRS backend" dir=in action=allow protocol=TCP localport=8000
   ```

3. Find the server's address with `ipconfig` (IPv4 Address).
4. On each client PC set `CDTRS_API_URL=http://<server-ip>:8000/api/v1` in `frontend\.env`
   (template `frontend\.env.example`). Clients need Python 3.12 and the frontend packages (`frontend\requirements.txt`).

---

## 4. Architectural principles

The workflow model is described in [`../ARCHITECTURE.md`](../ARCHITECTURE.md) - read it before changing workflow code.
In short:

- **One document, many workstreams.** A document has only a coarse lifecycle (`RECEIVED`, `REGISTERED`, `IN_REVIEW`,
  `IN_WORK`, `WITH_DS`, `CLOSED`), derived from its branches. Each `DocumentBranch` (Director, Department, Employee,
  TSO) is an independent workstream with its own stage; several run at the same time.
- **One work item per person.** A `WorkItem` is one person's work on one branch, with its own stage, deadline,
  progress and attachments. Teams only group work items.
- **Progress is free text and history is append-only.** Remarks, Director reviews, progress updates, stage changes
  and workflow events are never overwritten. There are no percentages.
- **Who does what.** Only the DS opens branches (routes) and closes documents. The Director reviews and remarks, never
  closes. An HOD assigns and validates work only on their own department's branch. All workflow rules live in
  `workflow.py`.
- **Authorization comes from the active work context**, not from the job title. A user can hold several contexts
  (for example Employee in one department and HOD in another). The client sends the one in use in the
  `X-Work-Context-Id` header; without the header the backend uses the context matching the account's role, otherwise
  the first active one. Only one TSO exists organisation-wide.
- **Visibility.** DS and Director contexts see the whole register. HOD, Employee and TSO contexts see documents they
  took part in (an HOD also sees documents with a branch for their department). The Admin context sees no documents.
- **Director gate.** Work routing (HOD, employee, TSO) is only allowed after a Director review (section 7.4).
- **Optimistic concurrency.** Mutations accept `expected_version`; if the document changed meanwhile the request is
  refused (HTTP 400, "changed by someone else ... Reload it and try again").
- **Closed means closed.** Changes to a closed document are refused until the DS reopens it.
- **OCR and routing suggestions are assistive only**; they never route anything.
- **Live updates** are pushed over the WebSocket, so screens refresh without polling.

---

## 5. Database

PostgreSQL database `cdtrs`: **23 tables** and **15 enums**, all defined in `models.py`. Tables are created by the
server on start (or by `reset_db.py`); there is no migration tool - `database.py` adds the few columns that were
introduced later.

### 5.1 Enums

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

Which branch stages are legal for which branch type is defined in `workflow.BRANCH_STAGES`
(also returned by `GET /api/v1/workflow/vocabulary`).

### 5.2 Tables

| # | Table | Purpose |
|---|---|---|
| 1 | `departments` | Departments, with the routing description and keywords. |
| 2 | `employees` | Staff directory (HR reference data, not a login). Optionally linked to an account. |
| 3 | `users` | Login accounts. |
| 4 | `work_context_memberships` | The "hats" a user can wear; the unit of authorization. |
| 5 | `incoming_messages` | E-mails fetched from the DS mailbox (intake provenance). |
| 6 | `documents` | The document register (one row per document). |
| 7 | `document_branches` | Independent workstreams on a document. |
| 8 | `work_teams` | Named groups of work items inside a branch (label only). |
| 9 | `work_items` | One person's work on one branch. |
| 10 | `progress_updates` | Free-text progress written by the worker (append-only). |
| 11 | `work_item_reviews` | HOD or DS accepting or returning one person's work. |
| 12 | `work_stage_changes` | Audit of every work-item stage change. |
| 13 | `attachments` | Stored files: originals, mail attachments, supporting documents, progress attachments. |
| 14 | `director_reviews` | Every completed Director review (repeatable, none replaces another). |
| 15 | `document_remarks` | All remarks (append-only). |
| 16 | `document_ocr` | One OCR record per document. |
| 17 | `document_extracted_fields` | Fields found by OCR, with the DS-verified value. |
| 18 | `routing_suggestions` | One advisory routing suggestion per document. |
| 19 | `reminders` | Deadline and manual reminders per work item. |
| 20 | `workflow_events` | Complete chronological history of each document. |
| 21 | `audit_logs` | Administrative and configuration actions only. |
| 22 | `notifications` | In-app notifications, addressed to a user and optionally one work context. |
| 23 | `system_settings` | Key/value settings (Admin). |

### 5.3 Key columns of the main tables

| Table | Key columns |
|---|---|
| `departments` | `id`, `name` (unique), `code` (unique, e.g. `FIN`), `description`, `keywords` (one comma-separated line), `is_active` |
| `users` | `id`, `username` (unique), `password_hash` (bcrypt), `full_name`, `role` (primary designation only - not used for authorization), `department_id` (home department), `employee_code`, `designation`, `email` (unique), `outlook_email`, `gov_email`, `preferred_mail_channel` (default `outlook`; no longer used), `is_active` |
| `work_context_memberships` | `id`, `user_id`, `context_type`, `department_id` (required for HOD and EMPLOYEE), `is_active`; unique (`user_id`, `context_type`, `department_id`) |
| `documents` | `doc_id`, `reference_no` (unique, `CDTRS-<year>-0001` ...), `title`, `subject`, `description`, `received_date`, `deadline`, `source`, `sender_name`, `sender_reference`, `mode`, `priority`, `lifecycle`, `ocr_status`, `created_by`, `source_message_id`, `version`, `registered_at`, `closed_at`, `closed_by_user_id`, `closure_remark` |
| `document_branches` | `id`, `document_id`, `branch_type`, `stage`, `department_id` (Department branches), `target_user_id` / `target_context_membership_id` (other branches), `opened_by_user_id`, `instructions`, `requires_hod_validation`, `deadline`, `round_no`, `is_active`, `version` |
| `work_items` | `id`, `document_id`, `branch_id`, `team_id`, `assigned_to_user_id`, `assigned_to_context_membership_id`, `assigned_by_user_id`, `instructions`, `deadline`, `stage`, `requires_validation`, `round_no`, `continues_item_id`, `is_active`, `started_at`, `submitted_at`, `completed_at`, `version` |
| `progress_updates` | `id`, `document_id`, `work_item_id`, `author_user_id`, `description`, `stage_at_time`, `created_at` |
| `attachments` | `id`, `document_id` (empty for mailbox attachments not yet processed), `progress_update_id`, `uploaded_by_user_id`, `file_name`, `storage_key` (path under `UPLOAD_DIR`), `file_type`, `file_size`, `checksum` (SHA-256), `attachment_type`, `source_message_id` |
| `director_reviews` | `id`, `document_id`, `branch_id`, `director_user_id`, `remark_text`, `review_no`, `document_version`, `requested_at`, `created_at` |
| `document_remarks` | `id`, `document_id`, `branch_id`, `work_item_id`, `author_user_id`, `remark_type`, `remark_text`, `provenance` (`MANUAL`, `DIRECTOR_REVIEW`, `WORK_REVIEW`, `CLOSURE`) |
| `document_extracted_fields` | `id`, `document_id`, `field_name` (upper case), `extracted_value`, `confidence`, `source_page`, `verified_value`, `verified_by`, `verified_at` |
| `routing_suggestions` | `document_id` (unique), `suggested_department_id`, `suggested_employee_id` (a `users.id`), `routing_confidence`, `routing_reason`, `routing_source`, `is_director_instruction`, `ranked_departments` (JSON), `generated_at`, `confirmed_by`, `confirmed_at` |
| `workflow_events` | `id`, `document_id`, `branch_id`, `work_item_id`, `event_type`, `actor_user_id`, `actor_context_type`, `summary`, `details`, `created_at` |
| `reminders` | `id`, `document_id`, `work_item_id`, `recipient_user_id`, `reason`, `message`, `due_at`, `sent_at`, `is_read`, `deduplication_key` (unique) |
| `notifications` | `id`, `user_id`, `context_membership_id`, `document_id`, `branch_id`, `work_item_id`, `event_id`, `title`, `message`, `is_read` |

---

## 6. API reference

Generated from the route decorators in `main.py` (82 routes). Paths in the tables are relative to `/api/v1`, except
`/`, `/health` and the WebSocket.

**Who** column:

| Value | Meaning |
|---|---|
| Public | No token needed. |
| Login | Any valid token (`Authorization: Bearer ...`). |
| Doc access | Login, and the active context may open the document (see "Visibility" in section 4). |
| DS, Director, HOD, TSO, Employee, Admin | The active work context (`X-Work-Context-Id`) must be of that type. Workflow endpoints check this in `workflow.py`. |

### 6.1 Health and live events

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/` | Public | Service name, version, status (no database access). |
| GET | `/health` | Public | Database check: counts of documents, open branches, open work items. |
| WebSocket | `/api/v1/ws` | Public (no token) | Live events as JSON: `event_type`, `document_id`, `user_id`, `timestamp`, `payload`. Any text the client sends is treated as a heartbeat. |
| GET | `/events/recent?limit=20` | Login | Latest events (the last 100 are kept in memory; lost on restart). |

Event types sent over the WebSocket: `DOCUMENT_CREATED`, `DIRECTOR_REVIEW_REQUESTED`, `DOCUMENT_ROUTED`,
`DIRECTOR_REMARK`, `WORK_ASSIGNED`, `WORK_STAGE_CHANGED`, `PROGRESS_UPDATED`, `WORK_SUBMITTED`, `WORK_REVIEWED`,
`ATTACHMENT_ADDED`, `DOCUMENT_CLOSED`.

### 6.2 Authentication

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/login` | Public | JSON `{"username", "password"}`. Returns `access_token`, `token_type`, `user`, `contexts`, `active_context`. 401 for wrong credentials or an inactive account; 403 if the account has no active work context. |
| GET | `/auth/me` | Login | Own account with its work contexts. |
| GET | `/auth/contexts` | Login | Own active work contexts. |
| POST | `/auth/switch-context` | Login | `{"context_membership_id"}`; checks that the context is yours and returns it. The server keeps no session: the client then sends that id in `X-Work-Context-Id`. |
| POST | `/auth/change-password` | Login | `{"current_password", "new_password"}`. |

### 6.3 Reference data

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/users` | Login | Active users. `?context_type=EMPLOYEE&department_id=<id>` lists holders of a work context (used by routing and assignment pickers). |
| GET | `/departments` | Login | Active departments, with description and keywords. |
| GET | `/departments/{department_id}/employees` | Login | Users holding an EMPLOYEE context in that department. |
| GET | `/employees` | Login | Staff directory (`employees` table). |
| GET | `/workflow/vocabulary` | Login | Branch stages per branch type, work stages, stages a worker may choose, lifecycle labels. |

### 6.4 Intake and intake analysis

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/intake` | DS | Messages fetched from the DS mailbox that are not yet processed into documents. |
| POST | `/intake/sync-outlook` | DS | Sync the DS mailbox now, with the provider `MAIL_CHANNEL` selects (Outlook or intranet, despite the name). Returns `status`, `synced_count`, `ignored_duplicates`, `message`. |
| POST | `/intake/{message_id}/process` | DS | Turn a mailbox message into a document. A JSON body is required but may be `{}`; its fields are all optional: `title`, `subject`, `description`, `received_date`, `deadline`, `priority`, `source`, `sender_name`, `sender_reference`. The message's attachments move to the document; OCR and the routing suggestion run. **409** if the message was already registered as a document (the message names it). |
| POST | `/intake/manual-upload` | DS | Register a received file (multipart, see below). 201 with the document. **409** if the same file (same SHA-256) is already the ORIGINAL of an existing document; the message names that document. |
| POST | `/intelligence/analyze` | DS | Multipart `file` (+ optional form field `body`): OCR, extracted fields and department suggestion for the intake form. Nothing is stored. |
| POST | `/intelligence/analyze-text` | DS | JSON `{"text": ...}` (first 200,000 characters): fields and department suggestion for text only, e.g. an e-mail body. Nothing is stored. |

`POST /intake/manual-upload` form fields:

| Field | Required | Notes |
|---|---|---|
| `file` | yes | Allowed types: .pdf .docx .doc .xlsx .xls .png .jpg .jpeg .tif .tiff .bmp .webp .txt .csv .zip (others: 415). Max `MAX_FILE_SIZE` (413). |
| `title` | yes | |
| `received_date` | yes | `2026-09-25`, `25/09/2026`, `25.09.2026`, `25 September 2026` and similar; unreadable dates become today. |
| `mode` | no | Default `MANUAL_UPLOAD`. |
| `priority` | no | CRITICAL, HIGH, MEDIUM, LOW (any case); `URGENT`/`IMMEDIATE` = CRITICAL, `NORMAL` = MEDIUM, `ROUTINE` = LOW; unknown = MEDIUM. |
| `subject`, `description`, `source`, `sender_name`, `sender_reference`, `deadline` | no | `source` defaults to `Manual Intake`. |
| `ocr_text`, `confidence`, `ocr_fields` | no | Result of `/intelligence/analyze`, so the file is not read twice. `confidence` as 0-1 or 0-100; `ocr_fields` as a JSON object string. |
| `suggested_department_id`, `suggested_employee_id` | no | The DS's choice on the intake form; stored as the routing suggestion with confidence 1.0. |

### 6.5 Documents

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents` | Login | Documents visible to the active context, with the caller's own work. |
| GET | `/documents/inbox` | Login | What the active context must act on now (DS: new, registered, back with DS, finished branches, returned Director reviews; Director: open reviews; HOD: active department branches; Employee/TSO: own active work items). |
| POST | `/documents` | DS | Register a document from metadata only (JSON, no file). 201. |
| GET | `/documents/{document_id}` | Doc access | Full document with branches and work items. |
| PATCH | `/documents/{document_id}` | DS | Correct metadata: `title`, `subject`, `description`, `received_date`, `deadline`, `source`, `sender_name`, `sender_reference`, `priority`, optional `expected_version`. Every change is written to the history. |
| POST | `/documents/{document_id}/register` | DS | Confirm the metadata: RECEIVED -> REGISTERED. Repeating it changes nothing. |
| POST | `/documents/{document_id}/send-to-director` | DS | Open a Director review. Optional `{"expected_version"}`. The document must be registered; only one Director review can be open. 201. |
| POST | `/documents/{document_id}/close` | DS | `{"remark", "force", "expected_version"}`. Refused while workstreams are open, unless `force` is true (they are then cancelled and recorded as such). |
| POST | `/documents/{document_id}/reopen` | DS | `{"reason"}`. |
| GET | `/documents/{document_id}/history` | Doc access | Workflow events, oldest first. |
| GET | `/history?limit=500` | Login | Events of all documents visible to the active context, newest first. |
| GET | `/documents/{document_id}/remarks` | Doc access | All remarks of the document. |

### 6.6 Routing (branches) and Director review

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/branches` | Doc access | Workstreams with their work items. |
| POST | `/documents/{document_id}/branches` | DS | Route to one or many targets: `{"branches": [{"branch_type", "department_id", "target_user_id", "instructions", "requires_hod_validation", "deadline", "assignee_user_ids", "team_name"}], "expected_version"}`. Each target becomes its own branch. Routing again to a target whose branch is open adds a round (FURTHER_WORK). The Director gate applies (7.4). 201. |
| POST | `/branches/{branch_id}/work-items` | DS, HOD | Assign people: `{"assignee_user_ids", "instructions", "deadline", "requires_validation", "team_name"}`. One work item per person. An HOD only on their own department's branch; assignees of a Department branch need an EMPLOYEE context in that department. 201. |
| POST | `/branches/{branch_id}/remark` | DS, HOD, TSO, Employee | `{"remark_text"}`. An HOD only on their own department's branch. |
| POST | `/branches/{branch_id}/close` | DS | `{"reason"}`. Ends one workstream (its unfinished work items are cancelled); the document stays open. |
| POST | `/branches/{branch_id}/director-review/start` | Director | Marks the review as Under Director Review. Repeating it changes nothing. |
| POST | `/branches/{branch_id}/director-review` | Director | `{"remark_text", "expected_version"}`. A remark is required. Saves review number n, returns the branch to the DS, notifies the DS and refreshes the routing suggestion. |
| GET | `/documents/{document_id}/director-reviews` | Doc access | Every Director review, oldest first. |

### 6.7 Work items

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/work-items/mine?include_finished=false` | Login | Own work items for the active context. |
| GET | `/work-items/department` | HOD | Every work item on the department's branches (empty list for other contexts). |
| GET | `/documents/{document_id}/work-items` | Doc access | All work items of a document. |
| GET | `/work-items/{work_item_id}` | Doc access | One work item with progress and reviews. |
| PATCH | `/work-items/{work_item_id}/stage` | Employee, TSO, HOD (own item) | `{"stage", "note"}`; the worker may choose UNDER_WORK, WAITING or SUBMITTED. |
| POST | `/work-items/{work_item_id}/progress` | Employee, TSO, HOD (own item) | `{"description", "new_stage"}`. Free text, append-only. 201. |
| POST | `/work-items/{work_item_id}/progress-with-file` | Employee, TSO, HOD (own item) | Multipart: `description`, optional `new_stage`, optional `file` (stored as PROGRESS_ATTACHMENT of that update). The file is checked first (413/415), so a rejected file leaves no progress update behind. 201. |
| POST | `/work-items/{work_item_id}/submit` | Employee, TSO, HOD (own item) | `{"note"}`. Goes to UNDER_REVIEW when validation is required on a Department branch (HODs are notified), otherwise COMPLETED (the DS is notified). Never closes the document. |
| POST | `/work-items/{work_item_id}/review` | HOD (own department), DS | `{"outcome": "ACCEPTED" or "RETURNED", "note"}`. Only for SUBMITTED or UNDER_REVIEW work. |

### 6.8 Attachments

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/attachments` | Doc access | List the document's files. |
| POST | `/documents/{document_id}/attachments` | Doc access | Multipart: `file`, `attachment_type` (default SUPPORTING_DOCUMENT, any case), optional `progress_update_id`. An unknown `attachment_type` gets 422 with the list of valid values; ORIGINAL may only be added in the DS context (403); `progress_update_id` must belong to this document (422). Same type and size rules as manual upload. **409** if the same file (same SHA-256) is already attached to this document. 201. |
| GET | `/attachments/{attachment_id}/download` | Doc access | Download the stored file. Mailbox attachments not yet registered as a document can only be downloaded in the DS or Admin context (403 otherwise). |

Stored file names are never overwritten: a second `letter.pdf` in the same folder is stored as `letter_1.pdf`, then
`letter_2.pdf`; the original name is kept in the database.

### 6.9 OCR and routing suggestions

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/documents/{document_id}/ocr` | Doc access | OCR text, status, engine, confidence, error, and the extracted fields (extracted, verified and effective value). |
| POST | `/documents/{document_id}/ocr/run` | DS | Run OCR again (the request waits for it). DS-verified values are kept. |
| POST | `/documents/{document_id}/verify-field` | DS | `{"field_name", "verified_value"}`. The field name is matched in any case; a field that does not exist yet is created with an upper-case name. |
| GET | `/documents/{document_id}/routing-suggestion` | Doc access | Suggested department and employee, confidence, reason, source, ranking of departments; `null` if none. |
| POST | `/documents/{document_id}/analyze-routing` | Doc access | `{"include_director_remark": true}`; recomputes the suggestion. |

### 6.10 Notifications, reminders, dashboard

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/notifications` | Login | Latest 100 for the caller: those for the active context plus those without a context. |
| GET | `/notifications/unread` | Login | Unread ones, same filter. |
| PATCH | `/notifications/{notification_id}/read` | Login | Mark one of your own as read. |
| PATCH | `/notifications/read-all` | Login | Mark all as read (active context plus those without a context); returns `{"updated": n}`. |
| GET | `/reminders` | Login | Your reminders (all contexts). |
| POST | `/reminders/check` | Login | Run the deadline scan now (it also runs every hour): a reminder and notification for each live work item due within 2 days or overdue, at most once per item, reason and day. |
| PATCH | `/reminders/{reminder_id}/read` | Login | Mark one of your own as read. |
| POST | `/documents/{document_id}/remind` | DS, HOD | `{"work_item_id", "recipient_user_id", "message"}`: remind one work item, or everyone with open work on the document. |
| GET | `/dashboard` | Login | Counter cards for the active context and up to 25 inbox documents. |

### 6.11 Administration

All require the Admin context.

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/users` | All accounts (also inactive) with their contexts. |
| POST | `/admin/users` | Create an account: `username`, `password`, `full_name`, `role`, optional `email`, `outlook_email`, `gov_email`, `employee_code`, `designation`, `department_id`. The account gets the default work context of its role: EMPLOYEE or HOD in its department (only if `department_id` is set), ADMIN, DS or DIRECTOR; a TSO account becomes TSO only when no TSO is active. An account without any context cannot log in (403) - add one with the contexts endpoint below. 201. |
| PUT | `/admin/users/{user_id}` | Change `full_name`, `role`, e-mail fields, `employee_code`, `designation`, `department_id`, `is_active`. |
| POST | `/admin/users/{user_id}/reset-password` | `{"new_password"}`. |
| POST | `/admin/users/{user_id}/toggle-active` | Activate or deactivate; returns `{"is_active"}`. |
| GET | `/admin/users/{user_id}/contexts` | The user's active contexts. |
| POST | `/admin/users/{user_id}/contexts` | Grant a context: `{"user_id", "context_type", "department_id"}` (`user_id` must be present in the body; the path value is used). HOD and EMPLOYEE need a department. Granting TSO designates this user as the single TSO. 201. |
| DELETE | `/admin/users/{user_id}/contexts/{context_id}` | Revoke a context. **409** if it still has open work items. |
| GET | `/admin/tso` | The current TSO context, or `null`. |
| POST | `/admin/tso/{user_id}/activate` | Designate the single TSO (the previous TSO context is deactivated). |
| GET | `/admin/departments?include_inactive=true` | All departments. |
| POST | `/admin/departments` | `{"name", "code", "description", "keywords"}`. 201. |
| PUT | `/admin/departments/{dept_id}` | JSON with any of `name`, `code`, `is_active`, `description`, `keywords` (an empty description or keywords value clears it). |
| GET | `/admin/settings` | System settings as key/value. |
| POST | `/admin/settings` | `{"key", "value", "description"}`. |
| GET | `/admin/audit-logs?limit=200&offset=0` | Administrative audit log, newest first. |

### 6.12 Status codes

| Code | When |
|---|---|
| 400 | A workflow rule was violated, invalid input, or `expected_version` did not match. The message explains it. |
| 401 | Invalid or expired token; account inactive or deleted; wrong user name or password at login. |
| 403 | Missing `Authorization` header ("Not authenticated") or a header that is not a `Bearer` token - both from FastAPI's HTTPBearer; wrong work context for the action (for example an ORIGINAL attachment outside the DS context); no access to the document; `X-Work-Context-Id` is not one of your contexts; login of an account without any active work context. |
| 404 | Document, work item, attachment, user, etc. not found; stored file missing on disk. |
| 409 | Duplicate file (manual upload, attachments); mailbox message already registered as a document; revoking a context that still has open work. |
| 413 | File larger than `MAX_FILE_SIZE`. |
| 415 | File type not allowed. |
| 422 | Required JSON or form fields missing or of the wrong type (FastAPI validation); unknown `attachment_type`, or a `progress_update_id` of another document. |

### 6.13 Interactive API pages

FastAPI serves Swagger UI at `/docs` and ReDoc at `/redoc` (the "Authorize" button in Swagger takes the token; the
`X-Work-Context-Id` header appears as a field on each endpoint). Both pages load their scripts and styles from a CDN on
the internet, so on a PC without internet access they stay blank. The API itself does not need internet;
`/openapi.json` (the machine-readable description) always works.

---

## 7. Intake, OCR and routing suggestions

### 7.1 How documents enter

1. **Manual intake (desktop app).** The DS picks a file; the app sends it to `POST /intelligence/analyze`
   (OCR, fields, department suggestion - nothing stored) to pre-fill the form, then registers it with
   `POST /intake/manual-upload`, passing the text and fields it already has so the file is not read twice.
2. **Mailbox.** The backend fetches the DS mailbox every 30 seconds (or on `POST /intake/sync-outlook`). Each new
   e-mail becomes an `incoming_messages` row, its attachments are stored; the DS turns it into a document with
   `POST /intake/{message_id}/process`. The same e-mail is never stored twice (matched by its message id), and a
   message that is already registered as a document cannot be processed again (409).
3. **Metadata only.** `POST /documents` registers a document without a file.

Each document gets a reference number `CDTRS-<year>-<4 digits>` and starts as RECEIVED.

**Duplicate protection:** a manual upload whose SHA-256 checksum equals an existing document's ORIGINAL file is
rejected with HTTP 409 naming that document; adding the same file twice to one document also returns 409.

### 7.2 OCR

- OCR of a registered document runs in a worker thread, so the server keeps answering other requests and the
  WebSocket stays connected. OCR_new is used by one request at a time (the models are not thread-safe).
- Source text, in this order: text sent by the intake form; otherwise OCR_new on the stored original (or the first
  attachment OCR_new can read: .pdf .png .jpg .jpeg .tif .tiff .bmp .webp .docx .txt); otherwise the title
  (engine `FALLBACK_METADATA`).
- Results: OCR text and confidence (`document_ocr`), extracted fields (`document_extracted_fields`, stored in upper
  case), Director instruction detection, and a fresh routing suggestion. Failures are stored as FAILED with the error
  and never block registration.
- Re-running OCR replaces unverified values only; values the DS verified are kept.
- If the PaddleOCR models are missing the error says to run `python OCR_new/setup_models.py` once.

### 7.3 Routing suggestions (advisory)

`intelligence.py` scores every active department against the document text (title, subject and OCR text):

- **Keyword score**: the department name or code appears; generic topic words derived from the name, code and
  description; an extracted "Department" field; a named staff member of the department (0.6); and the **Routing
  keywords** the Admin sets per department in "Department Configuration". Configured keyword hits score **0.55 /
  0.75 / 0.9** for 1 / 2 / 3 or more hits. Keywords of 3 characters or less (for example `HR`, `IT`) only count as
  whole words written in UPPER CASE in the document.
- **Semantic score**: similarity of the text to a department profile built from name, code, **Description**,
  **Keywords**, topic words and staff designations, using OCR_new's local embedding model (all-MiniLM-L6-v2).
- Combined: `1 - (1 - keyword) * (1 - semantic)`. A department is suggested only if the score is at least 0.3 and
  either the keyword score is at least 0.2 or the semantic score at least 0.4. The full ranking is stored in
  `ranked_departments`.
- A Director remark that names an employee (confidence 0.95) or a department (0.92) takes precedence; a department or
  employee chosen by the DS on the intake form comes next (1.0); the content ranking is used otherwise.
- The suggestion is refreshed after OCR and after every Director review. It never routes anything: the DS decides.

Good descriptions and keywords make better suggestions. Edit them in the app (Admin > Department Configuration),
through `PUT /admin/departments/{id}`, or once for all departments with `import_from_csv.py`.

### 7.4 DS verification and the Director gate

1. The DS checks the OCR fields and corrects them with `POST /documents/{id}/verify-field`; the original extracted
   value is kept, the verified value is what the system trusts. The DS corrects document details with
   `PATCH /documents/{id}` and confirms them with `POST /documents/{id}/register`.
2. The DS sends the document to the Director (`POST /documents/{id}/send-to-director`, or a routing request whose only
   target is the Director).
3. The Director opens it (`director-review/start`) and returns it with a remark (`director-review`). Reviews are
   numbered and all kept; the Director never closes documents.
4. Only then can the DS route to HODs, employees or the TSO. Until a Director review exists, such routing is refused
   (HTTP 400), and the Director cannot be combined with work targets in one routing request.
5. Exception: when OCR finds a handwritten Director instruction on the letter it sets the fields
   `PRIOR_DIRECTOR_REVIEW_DETECTED = true` and `DIRECTOR_HANDWRITTEN_REMARK`. If the DS verifies
   `PRIOR_DIRECTOR_REVIEW_DETECTED` with `true` (also accepted: `1`, `yes`, `detected`, `confirmed`), the gate counts as
   passed. The extracted value alone is not enough - it must be DS-verified.

---

## 8. Mail integration

Mail is optional; without it CDTRS works with manual intake and in-app notifications.

- `MAIL_CHANNEL` in `backend\.env` selects the system: `outlook` (Microsoft Graph), `intranet` (office mail server:
  IMAP for the DS mailbox, SMTP for the CDTRS mailbox), or `off` (also `none` / `disabled`): no mailbox sync and no
  notification e-mails at all. If the line is missing, `outlook` is used. `python run_server.py --no-mail` switches
  mail off for one run without editing the file.
- **Outlook, personal mailbox**: sign in once from the backend folder with `python mail\auth_personal.py`
  (device-code sign-in); the token is saved in `backend\mail\.token_cache.json` (git-ignored). While that file
  exists the Outlook provider counts as configured. The sign-in asks for `Mail.ReadWrite` (so imported e-mails can be
  marked as read), `Mail.Send` and `User.Read`; a token saved by an older version (read-only mail permission) must be
  replaced by running `python mail\auth_personal.py` once more.
- **Outlook, organisation**: `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET` and `OUTLOOK_MAILBOX`.
- **Intranet**: counts as configured when `INTRANET_IMAP_HOST`, `DS_MAIL_USER`, `INTRANET_SMTP_HOST`,
  `CDTRS_MAIL_USER` and a sender address are set.
- **Incoming**: while the selected provider is configured, the DS mailbox is synced every 30 seconds and on
  `POST /intake/sync-outlook` (section 7.1). Synced e-mails are marked as read in the mailbox.
- **Outgoing**: every workflow notification is stored in-app. An e-mail copy is queued in the background when the
  system setting `mail.notifications_enabled` is `true` (the seeded default) and the provider selected by
  `MAIL_CHANNEL` is configured. All e-mails go through that one office-wide channel (the `users.preferred_mail_channel`
  column is not used).
- **Recipient address**: with `outlook` the account's `outlook_email` is used first, then `email`, then `gov_email`;
  with `intranet` the account's `email` first, then `gov_email`, then `outlook_email`. Accounts without any address
  get no e-mail. `OVERRIDE_TEST_RECIPIENT_EMAIL` sends every e-mail to one test address instead.
- **Attachments**: the e-mail carries the document's original, mail and supporting files; notifications about one
  person's progress update or submitted work also carry that person's progress attachments.

Step-by-step guides: [`../OUTLOOK_INTEGRATION_GUIDE.md`](../OUTLOOK_INTEGRATION_GUIDE.md) (Microsoft 365 / Graph) and
[`../Intranet_testing.md`](../Intranet_testing.md) (office mail server, with test procedure and troubleshooting).

---

## 9. Admin scripts

Run all scripts from the backend folder; they use the database in `backend\.env`:

```bat
cd /d C:\CDTRS-main\backend
```

### 9.1 import_from_csv.py - import departments and accounts

```bat
mkdir data\import
copy data\import_templates\departments.csv data\import\
copy data\import_templates\accounts.csv data\import\
rem fill both files in Excel and save as "CSV UTF-8"
python import_from_csv.py --check
python import_from_csv.py
```

Another folder: `python import_from_csv.py D:\staff_lists --check`. `.xlsx` files with the same columns also work.
Filled examples: `data\import_templates\departments_example.csv` and `accounts_example.csv`.

| File | Columns |
|---|---|
| `departments.csv` | `name`, `code`, `description`, `keywords` (comma-separated routing keywords) |
| `accounts.csv` | `username`, `full_name`, `role`, `department`, `designation`, `employee_code`, `email`, `outlook_email`, `gov_email`, `password`, `contexts` |

- `role`: ADMIN, DS, DIRECTOR, TSO, HOD or EMPLOYEE. EMPLOYEE and HOD accounts need a `department`.
- `department`: code or name, from `departments.csv` or already in the database. Codes and names match in any case.
- `contexts` (optional): `;`-separated `TYPE[:DEPT]`, e.g. `EMPLOYEE:ENG; HOD:ENG; HOD:QA`. Without it EMPLOYEE and
  HOD get their own department, the other roles get their role. Only one TSO exists organisation-wide: a TSO context
  in the file makes that user the TSO.
- `password`: first password of NEW accounts (default `cdtrs@123`). Existing passwords are never changed.
- EMPLOYEE rows with an `employee_code` also get a staff-directory (`employees`) record.
- Checks (with and without `--check`): empty names, unknown roles and departments, a department code used twice or
  already belonging to another department, a username or e-mail used twice in the file, an e-mail that already
  belongs to another account, an employee code used twice. Any error stops the import. `--check` only validates;
  no departments or accounts are written.
- The import is all-or-nothing: it is written in one transaction, so if anything fails nothing is saved.
- Running it again updates, never duplicates. Existing accounts get the file's full name, role, designation,
  employee code, department and any e-mail addresses given; listed contexts are added or switched on again (never
  removed). Existing departments get the file's description and keywords when these are filled in, and the code if
  they have none. It uses the same code as the start-up seeding (`crud.apply_seed_payload`), but with updating
  switched on; the start-up seeding only adds missing records.
- A step-by-step guide for moving from the demo data to real data is in
  [`../DATA_MANAGEMENT_GUIDE.md`](../DATA_MANAGEMENT_GUIDE.md).

### 9.2 import_employees.py - older roster tool

```bat
python import_employees.py staff.xlsx
python import_employees.py staff.csv --seed-db
```

Reads `employee_code`, `username`, `full_name`, `department`, `designation`, `email`, `outlook_email`, `gov_email`,
`password` and **replaces the whole `employees` list in `data\seed_data.json`** (unknown departments are added there,
missing usernames become `emp_<first>_<last>`, default password `cdtrs@emp`). `--seed-db` then runs `seed.py`;
otherwise the next server start picks the file up. Both only add records that do not exist yet - changes to existing
employees or accounts do not reach the database. Prefer `import_from_csv.py`.

### 9.3 reset_db.py - rebuild the database (destructive)

```bat
python reset_db.py --confirm
python reset_db.py --confirm --wipe-uploads
```

Drops the whole `public` schema (all tables and enum types), recreates the 23 tables, seeds from
`data\seed_data.json` and prints the accounts with their contexts. `--wipe-uploads` also empties `backend\uploads`.
Without `--confirm` it only prints its help. Stop the backend first.

### 9.4 clear_documents.py - empty the register

```bat
python clear_documents.py --confirm
```

Deletes all documents with their branches, work items, progress, reviews, remarks, OCR data, suggestions, events,
reminders, notifications, attachment records and mailbox messages. Accounts, departments, staff directory, work
contexts, settings and the audit log are kept. Files in `backend\uploads` are not deleted.

### 9.5 reset_password.py

```bat
python reset_password.py <username> <new_password>
python reset_password.py
```

Without arguments it asks for the user name and password. The new password is shown on screen. Users can also change
their own password in the app (`/auth/change-password`), and the Admin can reset it (`/admin/users/{id}/reset-password`).

### 9.6 backup_database.py

```bat
python backup_database.py
python backup_database.py --dest D:\backups --keep 14
python backup_database.py --no-uploads
```

Or double-click `scripts\backup_database.bat` (same options). It writes to `<project>\backups\` (git-ignored):

- `cdtrs_db_YYYYmmdd_HHMM.dump` - the whole database (pg_dump custom format; password taken from `DATABASE_URL`);
- `cdtrs_uploads_YYYYmmdd_HHMM.zip` - `backend\uploads` (skipped with `--no-uploads`).

Only the newest `--keep` backups of each kind are kept (default 14). `pg_dump` is found on PATH or in
`C:\Program Files\PostgreSQL\<version>\bin`.

Restore (replaces the current data):

```bat
rem 1. stop the backend
"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --clean --if-exists -h localhost -U postgres -d cdtrs cdtrs_db_YYYYmmdd_HHMM.dump
rem 2. unzip cdtrs_uploads_YYYYmmdd_HHMM.zip into backend\uploads
```

Daily backups: Windows Task Scheduler > Create Basic Task > Daily > Start a program > `scripts\backup_database.bat`.

### 9.7 seed.py

`python seed.py` creates missing tables and adds the missing records of `data\seed_data.json` - the same as a server
start - then lists all accounts with their seed passwords from `seed_data.json`. Its `--reset` option drops the
tables with SQLAlchemy and clears the uploads; use `reset_db.py --confirm` instead.

---

## 10. Tests

The tests are plain Python scripts, run with `python`; no test framework has to be installed. They print PASS/FAIL
lines. The Director-instruction detector has quick unit tests that need no database:

```bat
cd /d C:\CDTRS-main\backend
python tests\test_director_detection.py -v
```

### 10.1 Test database

The workflow, API and UI tests create documents and log in with the demo accounts (`exec_user`, `director`,
`hod_eng`, `hod_prod`, `emp_rahul`, `emp_sneha`, `emp_anil`, `tso_user`, `corp`). Never run them against the real
database: use a separate database `cdtrs_test`, seeded from the demo `seed_data.json`. Create it once:

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE cdtrs_test;"
```

The test server fills it on its first start from `data\seed_data.json` (10.2). If that file has been emptied or
replaced with real data, put the demo copy back for that first start - `DATA_MANAGEMENT_GUIDE.md` (section 2.3) keeps
it as `data\seed_data_demo.json`:

```bat
cd /d C:\CDTRS-main\backend
copy /y data\seed_data.json data\seed_data_real.json
copy /y data\seed_data_demo.json data\seed_data.json
rem ... start the test server once (10.2) and wait for the "[CDTRS SEED]" line, then:
copy /y data\seed_data_real.json data\seed_data.json
```

Do not restart the real backend while the demo file is in place - its start-up seeding would add the demo accounts
to the real database.

### 10.2 Test server

The API and UI tests need a backend on port 8123 using the test database. Start it in its own Command Prompt and
keep it open:

```bat
cd /d C:\CDTRS-main\backend
set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

`--no-mail` is required: without it the test server would sync the real DS mailbox into the test database, mark
those e-mails as read, and could send notification e-mails.

### 10.3 Running the tests

In a second Command Prompt:

```bat
cd /d C:\CDTRS-main\backend
python tests/test_api_workflow.py
python tests/test_context_audit.py

cd /d C:\CDTRS-main\frontend
python tests/test_ui_smoke.py
```

- `test_api_workflow.py` uses `http://127.0.0.1:8123`; another base URL can be given as the first argument.
- `test_context_audit.py` uses `http://127.0.0.1:8123` too; `CDTRS_API_URL` (with or without `/api/v1`) overrides it.
- `test_ui_smoke.py` runs headless against port 8123.

Workflow engine, directly against a database (no server needed). Set the test database in the same window first,
otherwise it uses the database in `backend\.env`:

```bat
cd /d C:\CDTRS-main\backend
set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
python tests/test_full_workflow.py
```

### 10.4 OCR engine

130 tests, standard-library unittest:

```bat
cd /d C:\CDTRS-main\OCR_new
python -m unittest discover -s testing -t . -v
```

### 10.5 Mail diagnostics

These talk to real mail servers:

```bat
cd /d C:\CDTRS-main\backend
python tests/test_intranet_mail.py
python tests/test_intranet_mail.py --send --recipient x@y
python tests/test_mail_service.py
```

`test_intranet_mail.py` reads `backend\.env`; it only sends with `--send` (other options: `--incoming-only`, `--all`;
the recipient can also be set as `TEST_MAIL_RECIPIENT`). `test_mail_service.py` only shows the provider selection.
`tests/test_provider.py` **sends one real Outlook e-mail** to the address given as argument:

```bat
python tests/test_provider.py recipient@example.com
```

---

## 11. Seeded test accounts

Created from `data\seed_data.json` (15 departments, 17 accounts). Change these passwords before real use.

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

Department codes: PROD (Product Strategy), ENG (Engineering & Innovation), EXEC (Executive Office),
ENT (Enterprise Solutions), CX (Customer Experience), CR (Corporate Research), MBT (Market & Business
Transformation), PTN (Partnerships & Technology), CONS (Product Consulting), TECH (Information Technology),
OPS (Operations & Procurement), TALENT (Talent Management), CORP (Corporate Administration), FIN (Finance & Accounts),
SUPPORT (Business Support). Each has a description and routing keywords in `seed_data.json`.
