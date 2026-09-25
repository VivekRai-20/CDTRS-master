# CDTRS Architecture

Centralised Document Tracking and Routing System.
FastAPI + PostgreSQL backend, PySide6 desktop client.

---

## The one idea everything follows

A document is **not** a thing with a status. It is a thing with **workstreams**,
and each workstream has **people**, and each person has **their own work**.

```
Document                       lifecycle only: Received / Registered /
  │                            In Review / In Work / With DS / Closed
  │
  ├── DocumentBranch           ONE independent workstream, with its OWN stage
  │     │
  │     ├── DIRECTOR     Review Requested → Under Review → Remark Added → Returned to DS
  │     ├── DEPARTMENT   HOD Review → Employee Assignment → Employee Work → HOD Validation → Completed
  │     ├── EMPLOYEE     Assigned → In Progress → Submitted → Completed
  │     └── TSO          Assigned → In Progress → Submitted → Completed
  │
  └── WorkItem                 ONE PERSON's work — the unit of traceability
        ├── WorkStage          Assigned / Under Work / Waiting / Submitted /
        │                      Under Review / Returned / Completed / Cancelled
        ├── own deadline, own round
        ├── ProgressUpdate[]   free text, append-only, never a percentage
        │     └── Attachment[] tied to the update it belongs to
        └── WorkItemReview[]   HOD accepted / returned this person's work
```

Three branches on one document routinely sit at three different stages. That is
the normal case, and nothing in the system collapses them into a single value.

---

## Rules the code enforces

| Rule | Where |
|---|---|
| Only the DS opens branches | `workflow.open_branches` requires a DS context |
| Only the DS closes a document | `workflow.close_document` requires a DS context |
| The Director reviews and remarks — never closes | `DirectorReview` has no decision field |
| Director review is repeatable, every remark kept | one `DocumentBranch` per review, `review_no` increments |
| One work item per person, always | `assign_work_items` creates one row per `user_id` |
| A team groups work items, never replaces them | `WorkTeam` is a label; members keep separate `WorkItem`s |
| Progress is free text | `ProgressUpdate.description`; no numeric column exists |
| Branch stage never leaks into document lifecycle | `recompute_lifecycle` only looks at active/closed, not stages |
| Nothing is overwritten | remarks, reviews, progress and stage changes are all append-only |
| Authorization comes from the active context, not the job title | `require_context(...)` on every mutation |

---

## Work contexts

A user holds one or more `WorkContextMembership` rows — "hats". The active hat is
sent on every request as `X-Work-Context-Id` and decides what the person sees and
may do.

```
tso_user
  ├── TSO — Executive Office
  └── EMPLOYEE — Engineering & Innovation
```

Switching context changes the dashboard, navigation, task list, permissions and
notifications. TSO work never appears in that person's Employee task list.

The organisation designates exactly **one** TSO at a time
(`/admin/tso/{user_id}/activate`).

---

## Backend modules

| File | Responsibility |
|---|---|
| `models.py` | Schema. Every table, every enum. |
| `workflow.py` | **The workflow engine.** All routing, assignment, stages, reviews, closure, visibility, reminders. The single place workflow rules live. |
| `crud.py` | Identity, contexts, intake, attachments (unique file names, duplicate checks), admin, seeding / import. No workflow. |
| `intelligence.py` | OCR and routing suggestions. Assistive only — never routes anything. |
| `ocr_adapter.py` | Bridge to the offline OCR engine in `OCR_new/` (loaded once, warmed up at start). |
| `mail/` | Mailbox sync and notification e-mails: `outlook_provider.py` (Microsoft Graph), `intranet_provider.py` (IMAP/SMTP), `service.py`. |
| `serializers.py` | ORM → API shapes. |
| `schemas.py` | Request/response contracts. |
| `main.py` | HTTP endpoints, WebSocket, context dependency, background mailbox sync and reminders. |
| `run_server.py` | Starts uvicorn with HOST/PORT from `backend/.env`. |

## Intake, OCR and suggestions

```
manual upload ─────────► Document + ORIGINAL attachment (duplicate file → 409)
mailbox sync ─► intake message ─► DS registers it ─► Document
                           │
                           ▼ background thread
                        OCR_new: PaddleOCR → printed/handwritten per line →
                        TrOCR re-reads handwriting → entities, fields
                           │
                           ├─► DocumentOCR (text), DocumentExtractedField (unverified)
                           │     e.g. DIRECTOR_HANDWRITTEN_REMARK, PRIOR_DIRECTOR_REVIEW_DETECTED
                           └─► RoutingSuggestion.ranked_departments
                                 (semantic similarity + department description and
                                  routing keywords set by the Admin)
```

- Suggestions only pre-fill the DS's routing dialog; the DS decides.
- A Director instruction found by OCR counts only after the DS has **verified** it
  (`verified_value`); only then may work be routed without a new Director review.
- Department descriptions and routing keywords are edited in Admin → Department
  Configuration (or imported with `backend/import_from_csv.py`).

## Key endpoints

All paths are under `/api/v1` (e.g. `http://127.0.0.1:8000/api/v1/documents/12/close`);
[backend/readme.md](backend/readme.md) lists every endpoint.

```
POST /documents/{id}/branches        route — one or MANY targets at once
POST /branches/{id}/work-items       assign people (one work item each)
POST /branches/{id}/director-review  Director's remark, returns to DS
PATCH /work-items/{id}/stage         worker moves their own work
POST /work-items/{id}/progress       free-text update (+ /progress-with-file)
POST /work-items/{id}/submit         hand in
POST /work-items/{id}/review         HOD accept / return ONE person's work
POST /documents/{id}/close           DS only
```

---

## Frontend

| Layer | Files |
|---|---|
| Models | `models/document.py`, `models/workflow.py`, `models/enums.py` |
| Data | `repositories/api_repository.py` (only place that speaks HTTP) |
| Services | `document_service`, `routing_service`, `work_service`, `admin_service`, … |
| Workflow UI | `components/branch_panel.py` (branch + per-person cards), `components/document_viewer.py` |
| Dialogs | `components/routing_dialogs.py` — multi-target routing, assignment, progress, review, closure |

The Documents table renders a **multi-line Workstreams column**: one line per
branch with its own stage, e.g.

```
Engineering HOD: Employee Work
Anil Kumar: Completed
TSO: In Progress
```

---

## Running it

Settings live in `backend/.env` (template `backend/.env.example`) and
`frontend/.env` (template `frontend/.env.example`).

Double-click `start_backend.bat` and `start_frontend.bat`, or:

```bat
cd backend
python run_server.py
```

`run_server.py` takes HOST and PORT from `backend\.env`. Then, from the project folder:

```bat
python main.py
```

On start the backend creates missing tables and columns and adds the departments
and accounts of `backend/data/seed_data.json` **that do not exist yet**. It never
changes existing accounts, contexts or the chosen TSO.

Maintenance (from `backend/`):

| Command | Effect |
|---|---|
| `python reset_db.py --confirm` | **Destructive**: drop everything, rebuild, seed |
| `python clear_documents.py --confirm` | Delete all documents, keep accounts |
| `python import_from_csv.py --check` | Validate real departments / accounts; run again without `--check` to import |
| `python backup_database.py` | `pg_dump` + zip of uploads into `..\backups` |

## Tests

No test framework is needed (pytest is not part of the installed packages). The
backend and UI tests use the demo accounts and create documents, so run them
against a separate test database and a test server on port 8123 (see readme.md →
Tests):

```bat
cd /d C:\CDTRS-main\backend
set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
set UPLOAD_DIR=./uploads_test
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

| Command (run in the folder shown, second window, same `set` lines) | Tests |
|---|---|
| `backend> python tests\test_full_workflow.py` | Workflow engine, directly against the database |
| `backend> python tests\test_api_workflow.py` | Full HTTP workflow, including context headers |
| `backend> python tests\test_context_audit.py` | Context and authorization audit |
| `frontend> python tests\test_ui_smoke.py` | Every page in every context, headless |
| `OCR_new> python -m unittest discover -s testing -t . -v` | OCR engine and fine-tuning helpers (no database) |

## Seeded accounts

Demo data from `backend/data/seed_data.json` (15 departments, 17 accounts).

| Username | Password | Contexts |
|---|---|---|
| `exec_user` | `cdtrs@ds` | DS |
| `director` | `cdtrs@director` | Director |
| `corp` | `cdtrs@admin` | Admin |
| `tso_user` | `cdtrs@tso` | TSO, Employee Engineering & Innovation |
| `hod_prod` | `cdtrs@hod` | HOD Product Strategy, HOD Enterprise Solutions |
| `hod_eng` | `cdtrs@hod` | HOD Engineering & Innovation, HOD Customer Experience |
| `hod_cit` | `cdtrs@hod` | HOD Information Technology, HOD Talent Management |
| `hod_corp` | `cdtrs@hod` | HOD Corporate Administration, Finance & Accounts, Business Support, Operations & Procurement |
| `hod_ptc` | `cdtrs@hod` | HOD Partnerships & Technology, Product Consulting, Corporate Research, Market & Business Transformation |
| `emp_anil` | `cdtrs@emp` | Employee Product Strategy |
| `emp_vikram` | `cdtrs@emp` | Employee Product Strategy, HOD Enterprise Solutions |
| `emp_sneha` | `cdtrs@emp` | Employee Engineering, HOD Customer Experience |
| `emp_rahul` | `cdtrs@emp` | Employee Engineering, HOD Product Strategy |
| `emp_sunil` | `cdtrs@emp` | Employee Information Technology, HOD Talent Management |
| `emp_pooja` | `cdtrs@emp` | Employee Corporate Administration, HOD Finance & Accounts |
| `emp_kamble` | `cdtrs@emp` | Employee Finance & Accounts |
| `emp_rajesh` | `cdtrs@emp` | Employee Operations & Procurement, HOD Business Support |

Replace them with your real organisation before going live — see
[DATA_MANAGEMENT_GUIDE.md](DATA_MANAGEMENT_GUIDE.md).
