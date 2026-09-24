# CDTRS V2 — Backend

**Centralized Document Tracking and Routing System — Version 2**

```text
==================================================
CDTRS V2 — Backend Integration & Architecture
==================================================

Local API Base URL:
  http://127.0.0.1:8000/api/v1

Swagger Documentation:
  http://127.0.0.1:8000/docs

WebSocket Live Events URL:
  ws://127.0.0.1:8000/api/v1/ws

Authentication Method:
  JWT Bearer Token (HMAC-SHA256)

Login Endpoint:
  POST http://127.0.0.1:8000/api/v1/auth/login

Authorization Header:
  Authorization: Bearer <access_token>

Test Accounts:
  - DS:                 username: ds_user          | password: cdtrs@ds
  - DIRECTOR:           username: director         | password: cdtrs@director
  - HOD (Finance):      username: hod_finance      | password: cdtrs@hod
  - HOD (Procurement):  username: hod_procurement  | password: cdtrs@hod
  - EMPLOYEE (Finance): username: emp_rahul        | password: cdtrs@emp
  - EMPLOYEE (Procure): username: emp_priya        | password: cdtrs@emp

Role-Based Scoping:
  DS, DIRECTOR, HOD (Finance / Procurement), EMPLOYEE
==================================================
```

---

# 1. Backend Architecture & File Structure

The CDTRS V2 backend strictly adheres to a modular architecture:

```text
backend/
├── database.py        ← PostgreSQL connection, SQLAlchemy session, engine pooling
├── models.py          ← All 17 database tables & ORM models (V2 consolidated specification)
├── schemas.py         ← All Pydantic v2 request/response validation schemas
├── crud.py            ← Database operations, routing AI, reminders, and event manager
├── main.py            ← FastAPI app, REST endpoints, WebSocket event stream, CORS, file limits & auth guards
├── seed.py            ← Database table initialization & default user seeder
├── clear_documents.py ← Clean-slate test document reset script
├── requirements.txt   ← Python package dependencies
├── .env               ← Environment variable configuration
└── readme.md          ← This file (comprehensive technical guide)
```

### Module Responsibilities Flow

```text
database.py
     ↓  Establishes PostgreSQL connection & session generator
models.py
     ↓  Defines 17 database tables, enums & relational mappings
crud.py
     ↓  Handles queries, mutations, OCR hooks, routing AI, reminders, & WebSocket bus
schemas.py
     ↓  Validates request payloads and formats JSON responses (Pydantic v2)
main.py
     ↓  Exposes REST endpoints, WebSocket stream, role guards, and file handlers (20MB limits)
```

---

# 2. Technologies Used

| Technology | Purpose |
|---|---|
| **Python 3.10+** | Backend programming language |
| **FastAPI** | High-performance async REST API & WebSocket framework. Auto-generates interactive Swagger & OpenAPI documentation. |
| **Uvicorn** | Production-ready ASGI server with hot-reload for development. |
| **SQLAlchemy 2.x** | Object-Relational Mapper (ORM) for PostgreSQL. |
| **PostgreSQL 14–16** | Robust relational database. Tested on local PostgreSQL and cloud databases. |
| **Pydantic v2** | Request validation and response serialization with strong type enforcement. |
| **bcrypt** | Cryptographic password hashing (salt + hash). |
| **python-jose[cryptography]** | Generates and verifies HMAC-SHA256 JWT bearer tokens. |
| **python-multipart** | Enables `multipart/form-data` uploads for physical scan documents and progress attachments. |
| **python-dotenv** | Loads `.env` configuration securely into environment variables. |

---

# 3. Installation and Local Setup

### Step 1 — Prerequisites
- Python 3.10 or higher
- PostgreSQL 14, 15, or 16 installed and running
- `pip` package manager

### Step 2 — Install Python Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Step 3 — Create Local Database
Open `psql` or pgAdmin:
```sql
CREATE DATABASE cdtrs;
```
*(SQLAlchemy automatically creates all 17 tables on the first server startup or when running `seed.py`).*

### Step 4 — Configure Environment Variables
Edit [`backend/.env`](file:///c:/CDTRS-master/backend/.env):
```ini
DATABASE_URL=postgresql+psycopg2://postgres:nmrl@localhost:5432/cdtrs
HOST=0.0.0.0
PORT=8000
SECRET_KEY=cdtrs-super-secret-key-change-in-production-2026
ACCESS_TOKEN_EXPIRE_MINUTES=480
MAX_FILE_SIZE=20971520
CORS_ORIGINS=*
```

### Step 5 — Seed Default Accounts
```bash
python seed.py
```

### Step 6 — Start Local Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

# 4. Environment Variables Explained

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:nmrl@localhost:5432/cdtrs` | PostgreSQL connection string. Supports `postgres://`, `postgresql://`, and `postgresql+psycopg2://` formats automatically. |
| `HOST` | `0.0.0.0` | Host IP binding (`0.0.0.0` allows LAN connections from client PCs). |
| `PORT` | `8000` | Port for FastAPI HTTP server. |
| `SECRET_KEY` | `cdtrs-super-secret-key...` | Cryptographic secret for signing JWT tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT token validity lifetime (in minutes). |
| `MAX_FILE_SIZE` | `20971520` | Maximum file upload size in bytes (default 20 MB). |
| `UPLOAD_DIR` | `./uploads` | Storage directory for original documents and progress attachments. |
| `CORS_ORIGINS` | `*` | Allowed CORS origins for cross-origin client requests. |

---

# 5. Core Architectural Principles (V2)

1. **Document-Centric Single Canonical Record:** There is only one document record (`documents.doc_id`). No separate DirectorDocument or HODDocument copies.
2. **Routing $\neq$ Assignment:** DS decides where a document goes (`document_routes`). HOD delegates work to staff (`work_assignments`).
3. **Suggestion $\neq$ Routing:** OCR and Routing Intelligence recommend departments and employees, but DS explicitly confirms all routes.
4. **Director Remarks are Independent of Return:** Saving a Director remark (`PUT /director-remark`) is separate from the workflow transition of returning to DS (`POST /return-to-ds`).
5. **HOD Remarks are Independent of Assignment:** HOD can save remarks independently of assigning employees.
6. **Progress Updates are Append-Only:** Employee progress entries are never overwritten; full audit history is preserved.
7. **Strict Scope Isolation:** Backend enforces role and department filters in SQL queries. Finance HOD cannot view Procurement documents (returns `403`/`404`).
8. **Real-Time Event Driven:** WebSockets broadcast workflow transitions so PySide6 screens update automatically without manual refresh buttons.
9. **Optimistic Concurrency Control:** `version` column prevents concurrent overwrite conflicts (`409 Conflict`).
10. **File Size Safeguards:** Attachment uploads and manual intake files are validated against `MAX_FILE_SIZE` (20 MB limit).
11. **Closed Means Closed:** Once closed by DS, normal workflow mutations are rejected.

---

# 6. Database Design (17 Tables & Enums)

## 6.1 Enums (Controlled Vocabulary)

### `UserRole`
- `DS` — Director Secretary (Document Intake, Routing, Follow-up, Closure).
- `DIRECTOR` — The Director (Review, Remarks, Return to DS).
- `HOD` — Head of Department (Department Remarks, Employee Assignment).
- `EMPLOYEE` — Staff member (Task execution, Progress updates, File uploads).

### `DocumentStatus` (User-Facing Status)
- `RECEIVED` — Registered by DS.
- `UNDER_DIRECTOR_REVIEW` — Sent to Director for review.
- `DIRECTOR_REVIEW_COMPLETED` — Returned to DS by Director.
- `UNDER_HOD_PROCESSING` — Routed to Department HOD.
- `ASSIGNED_FOR_EXECUTION` — Assigned to Employee by HOD.
- `IN_PROGRESS` — Employee submitted progress.
- `PROGRESS_UPDATED` — Follow-up forwarded to Director.
- `REVIEW_COMPLETED` — Director completed follow-up review.
- `CLOSED` — Permanently closed by DS.

### `WorkflowStage` (Internal Stage)
- `DS`, `DIRECTOR`, `HOD`, `EMPLOYEE`, `CLOSED`.

### `Priority`
- `HIGH`, `MEDIUM`, `LOW`.

### `RouteType`
- `INITIAL_DIRECTOR_REVIEW`, `RETURN_TO_DS`, `POST_REVIEW_TO_HOD`, `POST_REVIEW_TO_EMPLOYEE`, `FOLLOW_UP_TO_DIRECTOR`.

### `SourceType`
- `OUTLOOK`, `GOVERNMENT_MAIL`, `MANUAL_UPLOAD`, `OTHER_APPROVED_SOURCE`.

### `AttachmentType`
- `ORIGINAL`, `EMAIL_ATTACHMENT`, `SUPPORTING_DOCUMENT`, `PROGRESS_ATTACHMENT`.

### `OCRStatus`
- `NONE`, `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`.

### `RoutingSource`
- `DOCUMENT_CONTENT`, `DIRECTOR_REMARK`, `SOURCE_METADATA`, `MANUAL`.

---

## 6.2 Table Specifications

### 1. `departments`
- `id` (Integer, PK)
- `name` (String(100), Unique, Required)
- `code` (String(20), Unique, Optional, e.g. `FIN`, `PROC`, `ADMIN`)
- `is_active` (Boolean, default `true`)
- `created_at` (DateTime)

### 2. `employees`
- `id` (Integer, PK)
- `employee_code` (String(50), Unique, Required, e.g. `EMP-001`)
- `full_name` (String(100), Required)
- `department_id` (Integer, FK $\to$ `departments.id`)
- `designation` (String(100), Required)
- `user_id` (Integer, FK $\to$ `users.id`, Nullable)
- `is_active` (Boolean, default `true`)

### 3. `users`
- `id` (Integer, PK)
- `username` (String(50), Unique, Indexed)
- `password_hash` (String(255), bcrypt hash)
- `full_name` (String(100))
- `role` (Enum `UserRole`)
- `department_id` (Integer, FK $\to$ `departments.id`, Nullable)
- `employee_id` (Integer, Nullable)
- `is_active` (Boolean, default `true`)

### 4. `documents` (Canonical Single Record)
- `doc_id` (Integer, PK)
- `reference_number` (String(100), Unique, Indexed)
- `subject` (String(500), Required)
- `document_date` (Date, Required)
- `source_type` (Enum `SourceType`)
- `sender_name` (String(200), Nullable)
- `sender_organization` (String(200), Nullable)
- `priority` (Enum `Priority`, default `MEDIUM`)
- `deadline` (Date, Nullable)
- `status` (Enum `DocumentStatus`, default `RECEIVED`)
- `current_stage` (Enum `WorkflowStage`, default `DS`)
- `current_owner_id` (Integer, FK $\to$ `users.id`, Nullable)
- `current_department_id` (Integer, FK $\to$ `departments.id`, Nullable)
- `created_by_user_id` (Integer, FK $\to$ `users.id`)
- `version` (Integer, default 1, Optimistic Locking)
- `created_at`, `updated_at` (DateTime)

### 5. `document_attachments`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `progress_update_id` (Integer, FK $\to$ `progress_updates.id`, Nullable)
- `uploaded_by` (Integer, FK $\to$ `users.id`)
- `file_name` (String(255))
- `storage_key` (String(500))
- `file_type` (String(100))
- `file_size` (Integer)
- `checksum` (String(64), SHA-256)
- `attachment_type` (Enum `AttachmentType`)
- `created_at` (DateTime)

### 6. `document_routes`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `from_user_id` (Integer, FK $\to$ `users.id`)
- `to_user_id` (Integer, FK $\to$ `users.id`, Nullable)
- `to_department_id` (Integer, FK $\to$ `departments.id`, Nullable)
- `route_type` (Enum `RouteType`)
- `instructions` (Text, Nullable)
- `created_at` (DateTime)

### 7. `work_assignments`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `department_id` (Integer, FK $\to$ `departments.id`)
- `assigned_by_user_id` (Integer, FK $\to$ `users.id`)
- `assigned_to_user_id` (Integer, FK $\to$ `users.id`)
- `instructions` (Text, Nullable)
- `assigned_at` (DateTime)
- `is_active` (Boolean, default `true`)

### 8. `progress_updates`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `work_assignment_id` (Integer, FK $\to$ `work_assignments.id`, Nullable)
- `submitted_by_user_id` (Integer, FK $\to$ `users.id`)
- `description` (Text, Required)
- `submitted_at` (DateTime)

### 9. `document_remarks`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `user_id` (Integer, FK $\to$ `users.id`)
- `role_at_creation` (Enum `UserRole`)
- `remark_text` (Text)
- `created_at`, `updated_at` (DateTime)

### 10. `workflow_history`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `performed_by_user_id` (Integer, FK $\to$ `users.id`)
- `action` (String(100))
- `previous_status`, `new_status` (Enum `DocumentStatus`, Nullable)
- `details` (Text, Nullable)
- `timestamp` (DateTime)

### 11. `ocr_extractions`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`, Unique)
- `raw_text` (Text)
- `status` (Enum `OCRStatus`)
- `processed_at` (DateTime)

### 12. `ocr_structured_fields`
- `id` (Integer, PK)
- `ocr_id` (Integer, FK $\to$ `ocr_extractions.id`)
- `field_name` (String(50))
- `field_value` (Text)
- `confidence` (Float)
- `is_verified` (Boolean, default `false`)
- `verified_by_user_id` (Integer, FK $\to$ `users.id`, Nullable)

### 13. `routing_suggestions`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`, Unique)
- `suggested_department_id` (Integer, FK $\to$ `departments.id`, Nullable)
- `suggested_employee_id` (Integer, FK $\to$ `employees.id`, Nullable)
- `confidence_score` (Float)
- `reason` (Text)
- `source` (Enum `RoutingSource`)
- `is_director_instruction` (Boolean, default `false`)

### 14. `reminders`
- `id` (Integer, PK)
- `doc_id` (Integer, FK $\to$ `documents.doc_id`)
- `recipient_user_id` (Integer, FK $\to$ `users.id`)
- `reason` (String(200))
- `is_read` (Boolean, default `false`)
- `created_at` (DateTime)

### 15. `notifications`
- `id` (Integer, PK)
- `user_id` (Integer, FK $\to$ `users.id`)
- `document_id` (Integer, FK $\to$ `documents.doc_id`, Nullable)
- `title` (String(200)), `message` (Text)
- `is_read` (Boolean, default `false`)
- `created_at` (DateTime)

---

# 7. Consolidated API Reference

### Authentication
| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Public | Login with username/password, returns JWT token |
| GET | `/api/v1/auth/me` | All | Get profile of logged-in user |
| POST | `/api/v1/auth/logout` | All | Logout (client discards token) |

### Intake & Mail
| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/intake` | DS | List all incoming mail/intake items |
| POST | `/api/v1/intake/manual-upload` | DS | Upload document file + metadata (20MB limit) |
| POST | `/api/v1/intake/{id}/process` | DS | Process intake item into canonical document |

### Documents
| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/api/v1/documents` | DS | Register new document |
| GET | `/api/v1/documents` | DS | Get all documents |
| GET | `/api/v1/documents/inbox` | All | Role-scoped inbox for current user |
| GET | `/api/v1/documents/{id}` | All | Get single document (Authorized) |
| POST | `/api/v1/documents/{id}/route` | DS | Route document to Director/HOD/Employee |
| PUT | `/api/v1/documents/{id}/director-remark` | DIRECTOR | Save/edit Director remark |
| POST | `/api/v1/documents/{id}/return-to-ds` | DIRECTOR | Return document to DS |
| PUT | `/api/v1/documents/{id}/hod-remark` | HOD | Save/edit HOD remark |
| POST | `/api/v1/documents/{id}/assign` | HOD | Assign employee to document |
| POST | `/api/v1/documents/{id}/progress` | EMPLOYEE | Submit progress update |
| GET | `/api/v1/documents/{id}/progress` | All | Get progress updates |
| POST | `/api/v1/documents/{id}/attachments` | All | Upload attachment file (Multipart, 20MB limit) |
| GET | `/api/v1/documents/{id}/attachments` | All | List attachments for document |
| GET | `/api/v1/documents/{id}/remarks` | All | Get remark history |
| POST | `/api/v1/documents/{id}/follow-up` | DS | Forward progress follow-up to Director |
| GET | `/api/v1/documents/{id}/history` | All | Get workflow history |
| POST | `/api/v1/documents/{id}/close` | DS | Permanently close document |

### OCR & Intelligence
| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/api/v1/documents/{id}/process-ocr` | DS | Trigger PaddleOCR processing |
| GET | `/api/v1/documents/{id}/ocr` | All | Get OCR raw text & structured fields |
| POST | `/api/v1/documents/{id}/verify-field` | DS | Verify/edit extracted field |
| POST | `/api/v1/documents/{id}/reanalyze` | DS | Re-run OCR preserving verified fields |
| POST | `/api/v1/documents/{id}/analyze-routing` | DS | Generate routing suggestion |
| GET | `/api/v1/documents/{id}/routing-suggestion` | All | Get current routing suggestion & confidence |

### Attachments
| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/attachments/{id}` | All | Get attachment metadata |
| GET | `/api/v1/attachments/{id}/download` | All | Authorized streaming file download |

### Reminders & Notifications
| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/reminders` | All | Get user action/deadline reminders |
| POST | `/api/v1/reminders/check` | DS | Trigger reminder scan & escalation |
| PATCH | `/api/v1/reminders/{id}/read` | All | Mark reminder as read |
| GET | `/api/v1/notifications` | All | Get all notifications |
| GET | `/api/v1/notifications/unread` | All | Get unread notifications |
| PATCH | `/api/v1/notifications/{id}/read` | All | Mark notification as read |
| PATCH | `/api/v1/notifications/read-all` | All | Mark all notifications as read |

### Dashboard & Events
| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/dashboard` | All | Get role-specific dashboard metrics |
| WebSocket | `/api/v1/ws` | All | Real-time live event stream |
| GET | `/api/v1/events/recent` | All | Polling fallback for recent events |

---

# 8. Test Accounts (Seed Data)

| Role | Department | Username | Password |
|---|---|---|---|
| **DS** | Administration | `ds_user` | `cdtrs@ds` |
| **DIRECTOR** | Executive | `director` | `cdtrs@director` |
| **HOD** | Finance | `hod_finance` | `cdtrs@hod` |
| **HOD** | Procurement | `hod_procurement` | `cdtrs@hod` |
| **EMPLOYEE** | Finance | `emp_rahul` | `cdtrs@emp` |
| **EMPLOYEE** | Procurement | `emp_priya` | `cdtrs@emp` |