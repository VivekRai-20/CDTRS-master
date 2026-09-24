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
| `crud.py` | Identity, contexts, intake, attachments, admin, seeding. No workflow. |
| `intelligence.py` | OCR and routing suggestions. Assistive only — never routes anything. |
| `serializers.py` | ORM → API shapes. |
| `schemas.py` | Request/response contracts. |
| `main.py` | HTTP endpoints and context dependency. |

## Key endpoints

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
TSO: Technical Work
```

---

## Running it

```bash
# 1. Database (destructive — drops and re-seeds)
cd backend && python reset_db.py --confirm

# 2. Backend
cd backend && python -m uvicorn main:app --reload --port 8000

# 3. Client
python main.py
```

Clear documents without re-seeding accounts:

```bash
cd backend && python clear_documents.py --confirm
```

## Tests

```bash
cd backend && python tests/test_full_workflow.py     # engine, direct against the DB
cd backend && python tests/test_api_workflow.py      # full HTTP workflow incl. context headers
cd backend && python -m pytest tests/test_context_audit.py -q
cd frontend && python tests/test_ui_smoke.py         # every page, every context, headless
```

The API and UI tests need a server running on port 8123:

```bash
cd backend && python -m uvicorn main:app --port 8123
```

## Seeded accounts

| Username | Password | Contexts |
|---|---|---|
| `exec_user` | `cdtrs@ds` | DS |
| `director` | `cdtrs@director` | Director |
| `hod_eng` | `cdtrs@hod` | HOD Engineering, HOD Customer Experience |
| `emp_rahul` | `cdtrs@emp` | Employee Engineering, HOD Product Strategy |
| `tso_user` | `cdtrs@tso` | TSO, Employee Engineering |
| `corp` | `cdtrs@admin` | Admin |
