"""CDTRS API.

Endpoint shape mirrors the model:

    /documents                      the register
    /documents/{id}/branches        routing - open independent workstreams
    /branches/{id}/work-items       assign people (one work item each)
    /work-items/{id}/...            one person's stage, progress, submission
    /branches/{id}/director-review  the Director's remark
    /documents/{id}/close           DS closure - the only way a document closes

Every mutating endpoint takes the caller's active work context from the
X-Work-Context-Id header; the workflow engine decides what that context may do.
"""

import warnings

# requests 2.32.3 warns about the installed chardet 7.x / urllib3 2.7 at import
# time.  Both work with it; the versions are fixed by the deployment, so the
# warning is silenced before anything imports requests.
warnings.filterwarnings(
    "ignore", message=r"urllib3 \(.*\) or chardet \(.*\)/charset_normalizer \(.*\) doesn't match a supported version"
)

# Windows: pyarrow must be loaded before PaddleOCR and the other native
# libraries.  When it is first imported later (sentence-transformers imports it
# while the OCR engine warms up), its DLL start-up crashes the whole server
# process with an access violation about 45 s after start: the backend then
# disappears without an error and the desktop app reports "WebSocket error:
# The remote host closed the connection".  Loading it here, first, avoids that.
try:
    import pyarrow  # noqa: F401
    import pyarrow.dataset  # noqa: F401
    import pandas  # noqa: F401
except Exception:
    pass

import asyncio
import json
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import date as _date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OCR_DIR = _PROJECT_ROOT / "OCR_new"
for _p in (str(_OCR_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crud
import intelligence
import models
import schemas
import serializers
import workflow
from database import engine, ensure_enum_compatibility, ensure_schema_columns, get_db
from models import (
    AttachmentType,
    BranchType,
    Priority,
    ReviewOutcome,
    UserRole,
    WorkContextType,
    WorkStage,
)

API_V1 = "/api/v1"


# =========================================================
# HELPERS
# =========================================================

def _parse_flexible_date(value: Optional[str]) -> _date:
    if not value:
        return datetime.utcnow().date()
    s = str(value).strip().split("T")[0]
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d",
        "%d.%m.%Y", "%Y.%m.%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return datetime.utcnow().date()


def _optional_date(value: Optional[str]) -> Optional[_date]:
    if not value or not str(value).strip():
        return None
    return _parse_flexible_date(value)


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 20 * 1024 * 1024))

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".png", ".jpg", ".jpeg",
    ".tif", ".tiff", ".bmp", ".webp", ".txt", ".csv", ".zip",
}

# File types the OCR engine can read (desktop intake analysis).
OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".docx", ".txt"}


def _parse_priority(value: Optional[str]) -> Priority:
    """Accept any case / common aliases; unknown values fall back to MEDIUM
    instead of failing the whole registration."""
    text = str(value or "").strip().upper()
    aliases = {"URGENT": "CRITICAL", "IMMEDIATE": "CRITICAL", "NORMAL": "MEDIUM", "ROUTINE": "LOW"}
    try:
        return Priority(aliases.get(text, text))
    except ValueError:
        return Priority.MEDIUM


def _store_upload(doc_id: int, filename: str, contents: bytes) -> str:
    """Store an uploaded file under uploads/<year>/<doc_id>/.  A file with the
    same name is kept as name_1.ext, name_2.ext, ... (never overwritten)."""
    dest_dir = UPLOAD_DIR / str(datetime.utcnow().year) / str(doc_id)
    dest_path = crud.save_file_unique(dest_dir, filename, contents)
    return dest_path.relative_to(UPLOAD_DIR).as_posix()


def _validate_upload(file: UploadFile, contents: bytes) -> None:
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
        )
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"'{ext}' files are not accepted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


# =========================================================
# LIFESPAN
# =========================================================

_MAIL_SYNC_LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from database import SessionLocal
        models.Base.metadata.create_all(bind=engine)
        ensure_enum_compatibility(engine)
        ensure_schema_columns(engine)
        db = SessionLocal()
        try:
            if db.query(models.Department).count() == 0 or db.query(models.User).count() == 0:
                print("[STARTUP] Database unseeded - seeding now...", flush=True)
            crud.seed_data(db)
        finally:
            db.close()
    except Exception as e:
        print(f"[STARTUP WARN] {e}", flush=True)

    # Mail sync and reminders do blocking network / database work.  They run
    # in worker threads so they never stall the event loop (which serves
    # every request and keeps the WebSocket connections alive).
    def _mailbox_sync_once():
        if not _MAIL_SYNC_LOCK.acquire(blocking=False):
            return  # a sync (periodic or manual) is already running
        try:
            from database import SessionLocal
            from mail.service import mail_service
            db = SessionLocal()
            try:
                if mail_service.is_configured():
                    mail_service.sync_ds_mailbox(db)
            finally:
                db.close()
        finally:
            _MAIL_SYNC_LOCK.release()

    def _reminders_once():
        from database import SessionLocal
        db = SessionLocal()
        try:
            workflow.generate_deadline_reminders(db)
        finally:
            db.close()

    async def _periodic_mailbox_sync():
        while True:
            try:
                await asyncio.sleep(30)
                await asyncio.to_thread(_mailbox_sync_once)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _periodic_reminders():
        while True:
            try:
                await asyncio.sleep(3600)
                await asyncio.to_thread(_reminders_once)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    # Load the OCR / embedding models in the background so the first upload
    # does not have to wait for them.
    threading.Thread(target=intelligence.warm_up_ocr_engine, name="ocr-warm-up", daemon=True).start()

    sync_task = asyncio.create_task(_periodic_mailbox_sync())
    reminder_task = asyncio.create_task(_periodic_reminders())
    yield
    sync_task.cancel()
    reminder_task.cancel()


app = FastAPI(
    title="CDTRS Backend",
    description="Centralised Document Tracking and Routing System",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS_ORIGINS in backend/.env: "*" (default) or a comma-separated list such as
# "http://192.168.1.20:8000,http://cdtrs-server:8000".  The desktop client does
# not need CORS; it matters only for browser-based clients.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# AUTH & CONTEXT DEPENDENCIES
# =========================================================

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    payload = crud.decode_access_token(credentials.credentials)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = crud.get_user_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is inactive.",
        )
    return user


def get_active_context(
    x_work_context_id: Optional[str] = Header(None, alias="X-Work-Context-Id"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Optional[models.WorkContextMembership]:
    """The hat the caller says they are wearing.  Validated against their own
    memberships; never trusted blindly."""
    if x_work_context_id:
        try:
            cid = int(x_work_context_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Work-Context-Id header.")
        membership = crud.validate_user_context(db, current_user.id, cid)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="That work context does not belong to you, or is inactive.",
            )
        return membership
    return workflow.resolve_context(db, current_user)


def _context_id(ctx: Optional[models.WorkContextMembership]) -> Optional[int]:
    return ctx.id if ctx else None


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, workflow.PermissionDenied):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, (workflow.WorkflowError, ValueError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _authorized_document(
    db: Session,
    doc_id: int,
    user: models.User,
    ctx: Optional[models.WorkContextMembership],
) -> models.Document:
    doc = crud.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not workflow.can_access_document(db, doc, user, _context_id(ctx)):
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    return doc


# =========================================================
# HEALTH
# =========================================================

@app.get("/", tags=["Health"])
def root():
    return {"service": "CDTRS", "version": "3.0.0", "status": "ok"}


@app.get("/health", tags=["Health"])
def health(db: Session = Depends(get_db)):
    return {
        "status": "healthy",
        "documents": db.query(models.Document).count(),
        "open_branches": db.query(models.DocumentBranch).filter(
            models.DocumentBranch.is_active.is_(True)).count(),
        "open_work_items": db.query(models.WorkItem).filter(
            models.WorkItem.is_active.is_(True)).count(),
    }


@app.websocket(f"{API_V1}/ws")
async def websocket_endpoint(websocket: WebSocket):
    await crud.event_manager.connect(websocket)
    try:
        while True:
            # Client heartbeats keep the connection active; nothing to reply.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        crud.event_manager.disconnect(websocket)


@app.get(f"{API_V1}/events/recent", tags=["Events"])
def recent_events(limit: int = 20, current_user: models.User = Depends(get_current_user)):
    return crud.event_manager.get_recent_events(limit)


# =========================================================
# AUTH
# =========================================================

@app.post(f"{API_V1}/auth/login", response_model=schemas.LoginResponse, tags=["Auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    contexts = crud.get_user_context_memberships(db, user.id)
    if not contexts:
        raise HTTPException(
            status_code=403,
            detail="This account has no active work context. Contact an administrator.",
        )
    active = workflow.resolve_context(db, user)
    return schemas.LoginResponse(
        access_token=crud.create_access_token({"sub": str(user.id)}),
        user=serializers.user(user, contexts),
        contexts=[serializers.context(c) for c in contexts],
        active_context=serializers.context(active) if active else None,
    )


@app.get(f"{API_V1}/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
def me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serializers.user(current_user, crud.get_user_context_memberships(db, current_user.id))


@app.get(f"{API_V1}/auth/contexts", response_model=List[schemas.WorkContextResponse], tags=["Auth"])
def my_contexts(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serializers.context(c) for c in crud.get_user_context_memberships(db, current_user.id)]


@app.post(f"{API_V1}/auth/switch-context", response_model=schemas.WorkContextResponse, tags=["Auth"])
def switch_context(
    payload: schemas.WorkContextSwitchRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = crud.validate_user_context(db, current_user.id, payload.context_membership_id)
    if not membership:
        raise HTTPException(status_code=403, detail="That work context is not available to you.")
    return serializers.context(membership)


@app.post(f"{API_V1}/auth/change-password", tags=["Auth"])
def change_password(
    payload: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not crud.verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    crud.update_user_password(db, current_user.id, payload.new_password)
    return {"detail": "Password updated."}


# =========================================================
# REFERENCE DATA
# =========================================================

@app.get(f"{API_V1}/users", response_model=List[schemas.UserResponse], tags=["Reference"])
def list_users(
    context_type: Optional[WorkContextType] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Routing and assignment pickers use this.  Filtering by context_type is
    the correct way to find 'employees of department X' - work contexts, not
    the account's nominal role, decide who can receive work."""
    if context_type:
        users = crud.get_users_by_context(db, context_type, department_id)
    else:
        users = crud.get_users(db, include_inactive=False)
    return [serializers.user(u) for u in users]


@app.get(f"{API_V1}/departments", response_model=List[schemas.DepartmentResponse], tags=["Reference"])
def list_departments(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return crud.get_departments(db)


@app.get(
    f"{API_V1}/departments/{{department_id}}/employees",
    response_model=List[schemas.UserResponse],
    tags=["Reference"],
)
def department_employees(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        serializers.user(u)
        for u in crud.get_users_by_context(db, WorkContextType.EMPLOYEE, department_id)
    ]


@app.get(f"{API_V1}/employees", response_model=List[schemas.EmployeeResponse], tags=["Reference"])
def list_employee_directory(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return crud.get_employees(db)


@app.get(f"{API_V1}/workflow/vocabulary", tags=["Reference"])
def workflow_vocabulary(current_user: models.User = Depends(get_current_user)):
    """Stage vocabulary so the UI never has to hardcode stage names."""
    return {
        "branch_stages": {
            bt.value: [
                {"value": s.value, "label": workflow.branch_stage_label(s)}
                for s in stages
            ]
            for bt, stages in workflow.BRANCH_STAGES.items()
        },
        "work_stages": [
            {"value": s.value, "label": workflow.work_stage_label(s)} for s in WorkStage
        ],
        "worker_selectable_stages": [
            {"value": s.value, "label": workflow.work_stage_label(s)}
            for s in workflow.WORKER_SELECTABLE_STAGES
        ],
        "lifecycles": [
            {"value": v, "label": label} for v, label in workflow.LIFECYCLE_LABELS.items()
        ],
    }


# =========================================================
# INTAKE
# =========================================================

@app.get(f"{API_V1}/intake", response_model=List[schemas.IntakeResponse], tags=["Intake"])
def list_intake(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Intake is handled in the DS context.")
    return crud.get_incoming_messages(db)


@app.post(f"{API_V1}/intake/sync-outlook", tags=["Intake"])
def sync_outlook(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Mailbox sync is a DS action.")
    from mail.service import mail_service
    with _MAIL_SYNC_LOCK:
        return mail_service.sync_ds_mailbox(db)


@app.post(
    f"{API_V1}/intake/manual-upload",
    response_model=schemas.DocumentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Intake"],
)
async def manual_upload(
    title: str = Form(...),
    received_date: str = Form(...),
    mode: str = Form(default="MANUAL_UPLOAD"),
    priority: str = Form(default="MEDIUM"),
    subject: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    source: Optional[str] = Form(default="Manual Intake"),
    sender_name: Optional[str] = Form(default=None),
    sender_reference: Optional[str] = Form(default=None),
    deadline: Optional[str] = Form(default=None),
    ocr_text: Optional[str] = Form(default=None),
    confidence: Optional[str] = Form(default=None),
    ocr_fields: Optional[str] = Form(default=None),
    suggested_department_id: Optional[str] = Form(default=None),
    suggested_employee_id: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Only the DS can register documents.")

    contents = await file.read()
    _validate_upload(file, contents)

    # The same scanned letter registered twice would create two workflows.
    duplicate = crud.find_duplicate_attachment(
        db, crud.compute_checksum(contents), attachment_type=AttachmentType.ORIGINAL
    )
    if duplicate is not None and duplicate.document is not None:
        existing = duplicate.document
        raise HTTPException(
            status_code=409,
            detail=(
                f"This file is already registered as document {existing.reference_no} "
                f"(\"{existing.title}\"). Open that document instead of registering it again."
            ),
        )

    dept_hint = int(suggested_department_id) if (suggested_department_id or "").strip().isdigit() else None
    emp_hint = int(suggested_employee_id) if (suggested_employee_id or "").strip().isdigit() else None
    parsed_conf = None
    if confidence:
        try:
            c = float(confidence.strip())
            parsed_conf = c / 100.0 if c > 1.0 else c
        except ValueError:
            parsed_conf = None

    doc = crud.create_document(
        db,
        schemas.DocumentCreate(
            title=title,
            subject=subject,
            description=description,
            received_date=_parse_flexible_date(received_date),
            deadline=_optional_date(deadline),
            source=source,
            sender_name=sender_name,
            sender_reference=sender_reference,
            mode=mode,
            priority=_parse_priority(priority),
        ),
        created_by=current_user.id,
        context_id=ctx.id,
    )

    crud.create_attachment(
        db=db,
        doc_id=doc.doc_id,
        progress_update_id=None,
        uploaded_by=current_user.id,
        file_name=file.filename,
        storage_key=_store_upload(doc.doc_id, file.filename, contents),
        file_type=file.content_type,
        file_size=len(contents),
        checksum=crud.compute_checksum(contents),
        attachment_type=AttachmentType.ORIGINAL,
        context_id=ctx.id,
    )

    intake_fields = None
    if ocr_fields:
        try:
            parsed_fields = json.loads(ocr_fields)
            if isinstance(parsed_fields, dict):
                intake_fields = parsed_fields
        except ValueError:
            intake_fields = None

    # OCR / routing intelligence can take a while; keep the event loop free.
    await run_in_threadpool(
        intelligence.trigger_ocr_processing,
        db, doc.doc_id,
        intake_ocr_text=ocr_text,
        intake_ocr_confidence=parsed_conf,
        preferred_dept_id=dept_hint,
        preferred_emp_id=emp_hint,
        intake_fields=intake_fields,
    )

    await crud.event_manager.broadcast("DOCUMENT_CREATED", document_id=doc.doc_id, user_id=current_user.id)
    db.refresh(doc)
    return serializers.document_detail(db, doc)


# ---------------------------------------------------------------------------
# Intake analysis (desktop intake form pre-fill).  The desktop app sends the
# file here instead of running the OCR models itself: one OCR engine, loaded
# once, on the server.  Nothing is stored.
# ---------------------------------------------------------------------------

@app.post(f"{API_V1}/intelligence/analyze", tags=["OCR"])
def analyze_intake_file(
    file: UploadFile = File(...),
    body: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Document intake is a DS action.")
    contents = file.file.read()
    _validate_upload(file, contents)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in OCR_EXTENSIONS:
        return {"success": False, "error": f"'{ext}' files cannot be read by OCR."}

    tmp_dir = UPLOAD_DIR / "_analysis"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{ext}"
    try:
        with open(tmp_path, "wb") as fh:
            fh.write(contents)
        return intelligence.analyze_document_file(db, str(tmp_path), extra_text=body or "")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


@app.post(f"{API_V1}/intelligence/analyze-text", tags=["OCR"])
def analyze_intake_text(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Document intake is a DS action.")
    text = str((payload or {}).get("text") or "")[:200_000]
    return intelligence.analyze_text(db, text)


@app.post(
    f"{API_V1}/intake/{{message_id}}/process",
    response_model=schemas.DocumentDetailResponse,
    tags=["Intake"],
)
async def process_intake(
    message_id: int,
    payload: schemas.IntakeProcessRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Only the DS can process intake.")
    try:
        doc = crud.process_intake_to_document(db, message_id, payload, current_user, ctx.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not doc:
        raise HTTPException(status_code=404, detail="Intake item not found.")
    await run_in_threadpool(intelligence.trigger_ocr_processing, db, doc.doc_id)
    await crud.event_manager.broadcast("DOCUMENT_CREATED", document_id=doc.doc_id, user_id=current_user.id)
    db.refresh(doc)
    return serializers.document_detail(db, doc)


# =========================================================
# DOCUMENTS
# =========================================================

@app.get(f"{API_V1}/documents", response_model=List[schemas.DocumentListResponse], tags=["Documents"])
def list_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    docs = workflow.documents_for_context(db, current_user, _context_id(ctx))
    return serializers.documents_with_my_work(db, docs, current_user.id, _context_id(ctx))


@app.get(f"{API_V1}/documents/inbox", response_model=List[schemas.DocumentListResponse], tags=["Documents"])
def inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """What the active context must act on now."""
    docs = workflow.inbox_for_context(db, current_user, _context_id(ctx))
    return serializers.documents_with_my_work(db, docs, current_user.id, _context_id(ctx))


@app.post(
    f"{API_V1}/documents",
    response_model=schemas.DocumentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
)
def create_document(
    payload: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Only the DS can register documents.")
    doc = crud.create_document(db, payload, created_by=current_user.id, context_id=ctx.id)
    return serializers.document_detail(db, doc)


@app.get(
    f"{API_V1}/documents/{{document_id}}",
    response_model=schemas.DocumentDetailResponse,
    tags=["Documents"],
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    doc = _authorized_document(db, document_id, current_user, ctx)
    return serializers.document_detail(db, doc)


@app.patch(
    f"{API_V1}/documents/{{document_id}}",
    response_model=schemas.DocumentDetailResponse,
    tags=["Documents"],
)
def update_document(
    document_id: int,
    payload: schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """DS corrects document details, including anything OCR mis-read."""
    try:
        doc = crud.update_document_metadata(db, document_id, payload, current_user, _context_id(ctx))
    except Exception as exc:
        raise _handle(exc)
    return serializers.document_detail(db, doc)


@app.post(
    f"{API_V1}/documents/{{document_id}}/register",
    response_model=schemas.DocumentDetailResponse,
    tags=["Documents"],
)
def register_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        doc = workflow.register_document(
            db, document_id=document_id, actor=current_user, context_id=_context_id(ctx)
        )
    except Exception as exc:
        raise _handle(exc)
    return serializers.document_detail(db, doc)

@app.post(
    f"{API_V1}/documents/{{document_id}}/send-to-director",
    response_model=schemas.BranchResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Director"],
)
async def send_to_director(
    document_id: int,
    payload: schemas.SendToDirectorRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        branch = workflow.send_to_director(
            db,
            document_id=document_id,
            actor=current_user,
            context_id=_context_id(ctx),
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        raise _handle(exc)

    await crud.event_manager.broadcast(
        "DIRECTOR_REVIEW_REQUESTED",
        document_id=document_id,
        user_id=current_user.id,
    )

    return serializers.branch(branch)

@app.post(
    f"{API_V1}/documents/{{document_id}}/close",
    response_model=schemas.DocumentDetailResponse,
    tags=["Documents"],
)
async def close_document(
    document_id: int,
    payload: schemas.CloseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Only the DS closes a document, and only when the DS decides the work is
    finished.  No Director approval is required."""
    try:
        doc = workflow.close_document(
            db,
            document_id=document_id,
            actor=current_user,
            context_id=_context_id(ctx),
            remark=payload.remark,
            force=payload.force,
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast("DOCUMENT_CLOSED", document_id=document_id, user_id=current_user.id)
    return serializers.document_detail(db, doc)


@app.post(
    f"{API_V1}/documents/{{document_id}}/reopen",
    response_model=schemas.DocumentDetailResponse,
    tags=["Documents"],
)
def reopen_document(
    document_id: int,
    payload: schemas.ReopenRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        doc = workflow.reopen_document(
            db, document_id=document_id, actor=current_user,
            context_id=_context_id(ctx), reason=payload.reason,
        )
    except Exception as exc:
        raise _handle(exc)
    return serializers.document_detail(db, doc)


@app.get(
    f"{API_V1}/documents/{{document_id}}/history",
    response_model=List[schemas.WorkflowEventResponse],
    tags=["Documents"],
)
def document_history(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _authorized_document(db, document_id, current_user, ctx)
    return [serializers.event(e) for e in workflow.document_history(db, document_id)]


@app.get(f"{API_V1}/history", response_model=List[schemas.WorkflowEventResponse], tags=["Documents"])
def all_history(
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    return [
        serializers.event(e)
        for e in workflow.visible_history(db, current_user, _context_id(ctx), limit)
    ]


@app.get(
    f"{API_V1}/documents/{{document_id}}/remarks",
    response_model=List[schemas.RemarkResponse],
    tags=["Documents"],
)
def document_remarks(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    doc = _authorized_document(db, document_id, current_user, ctx)
    return [serializers.remark(r) for r in doc.remarks]


# =========================================================
# BRANCHES (routing)
# =========================================================

@app.get(
    f"{API_V1}/documents/{{document_id}}/branches",
    response_model=List[schemas.BranchResponse],
    tags=["Branches"],
)
def list_branches(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    doc = _authorized_document(db, document_id, current_user, ctx)
    return [serializers.branch(b) for b in doc.branches]


@app.post(
    f"{API_V1}/documents/{{document_id}}/branches",
    response_model=List[schemas.BranchResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Branches"],
)
async def route_document(
    document_id: int,
    payload: schemas.RouteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """DS routing.  Send one target or many at once - to the Director, to HODs,
    to employees directly and to TSO - and they all become independent
    workstreams that coexist and progress at their own pace."""
    try:
        branches = workflow.open_branches(
            db,
            document_id=document_id,
            requests=[b.model_dump() for b in payload.branches],
            actor=current_user,
            context_id=_context_id(ctx),
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast("DOCUMENT_ROUTED", document_id=document_id, user_id=current_user.id)
    return [serializers.branch(b) for b in branches]


@app.post(
    f"{API_V1}/branches/{{branch_id}}/work-items",
    response_model=List[schemas.WorkItemResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Branches"],
)
async def assign_work(
    branch_id: int,
    payload: schemas.BranchAssignRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """HOD (or DS) assigns people.  One work item is created per person, each
    with its own stage, deadline and progress trail.  `team_name` only groups
    them for display."""
    try:
        items = workflow.assign_branch_work(
            db,
            branch_id=branch_id,
            assignee_user_ids=payload.assignee_user_ids,
            actor=current_user,
            context_id=_context_id(ctx),
            instructions=payload.instructions,
            deadline=payload.deadline,
            requires_validation=payload.requires_validation,
            team_name=payload.team_name,
        )
    except Exception as exc:
        raise _handle(exc)
    if items:
        await crud.event_manager.broadcast(
            "WORK_ASSIGNED", document_id=items[0].document_id, user_id=current_user.id
        )
    return [serializers.work_item(i) for i in items]


@app.post(
    f"{API_V1}/branches/{{branch_id}}/remark",
    response_model=schemas.RemarkResponse,
    tags=["Branches"],
)
def branch_remark(
    branch_id: int,
    payload: schemas.BranchRemarkRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        remark = workflow.add_branch_remark(
            db, branch_id=branch_id, remark_text=payload.remark_text,
            actor=current_user, context_id=_context_id(ctx),
        )
    except Exception as exc:
        raise _handle(exc)
    return serializers.remark(remark)


@app.post(
    f"{API_V1}/branches/{{branch_id}}/close",
    response_model=schemas.BranchResponse,
    tags=["Branches"],
)
def close_branch(
    branch_id: int,
    payload: schemas.BranchCloseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Ends one workstream.  Other branches on the document keep running and
    the document itself stays open."""
    try:
        branch = workflow.close_branch(
            db, branch_id=branch_id, actor=current_user,
            context_id=_context_id(ctx), reason=payload.reason,
        )
    except Exception as exc:
        raise _handle(exc)
    return serializers.branch(branch)


# =========================================================
# DIRECTOR REVIEW
# =========================================================

@app.post(
    f"{API_V1}/branches/{{branch_id}}/director-review/start",
    response_model=schemas.BranchResponse,
    tags=["Director"],
)
def start_review(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        branch = workflow.start_director_review(
            db, branch_id=branch_id, actor=current_user, context_id=_context_id(ctx)
        )
    except Exception as exc:
        raise _handle(exc)
    return serializers.branch(branch)


@app.post(
    f"{API_V1}/branches/{{branch_id}}/director-review",
    response_model=schemas.DirectorReviewResponse,
    tags=["Director"],
)
async def submit_director_review(
    branch_id: int,
    payload: schemas.DirectorReviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """The Director records a remark and hands the document back to the DS.
    There is no decision field: the Director does not close documents and does
    not stop work on other branches."""
    try:
        review = workflow.submit_director_review(
            db,
            branch_id=branch_id,
            remark_text=payload.remark_text,
            actor=current_user,
            context_id=_context_id(ctx),
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast(
        "DIRECTOR_REMARK", document_id=review.document_id, user_id=current_user.id
    )
    # Refresh routing intelligence now that a new Director remark exists.
    try:
        await run_in_threadpool(
            intelligence.generate_routing_suggestion,
            db, review.document_id, include_director_remark=True,
        )
    except Exception:
        db.rollback()
    return serializers.director_review(review)


@app.get(
    f"{API_V1}/documents/{{document_id}}/director-reviews",
    response_model=List[schemas.DirectorReviewResponse],
    tags=["Director"],
)
def list_director_reviews(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Every review ever made on this document, oldest first.  None replaces
    another."""
    doc = _authorized_document(db, document_id, current_user, ctx)
    return [serializers.director_review(r) for r in doc.director_reviews]


# =========================================================
# WORK ITEMS (one person's work)
# =========================================================

@app.get(f"{API_V1}/work-items/mine", response_model=List[schemas.WorkItemResponse], tags=["Work"])
def my_work_items(
    include_finished: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """The caller's own task list for the hat they are currently wearing."""
    items = workflow.work_items_for_context(db, current_user, _context_id(ctx), include_finished)
    return [serializers.work_item(i) for i in items]


@app.get(f"{API_V1}/work-items/department", response_model=List[schemas.WorkItemResponse], tags=["Work"])
def department_work_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """For an HOD: every individual's work across their department's
    workstreams, so each person's contribution stays visible."""
    items = workflow.branch_work_items_for_context(db, current_user, _context_id(ctx))
    return [serializers.work_item(i) for i in items]


@app.get(
    f"{API_V1}/documents/{{document_id}}/work-items",
    response_model=List[schemas.WorkItemResponse],
    tags=["Work"],
)
def document_work_items(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    doc = _authorized_document(db, document_id, current_user, ctx)
    return [serializers.work_item(i) for i in doc.work_items]


@app.get(f"{API_V1}/work-items/{{work_item_id}}", response_model=schemas.WorkItemResponse, tags=["Work"])
def get_work_item(
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    item = db.query(models.WorkItem).filter(models.WorkItem.id == work_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found.")
    _authorized_document(db, item.document_id, current_user, ctx)
    return serializers.work_item(item)


@app.patch(
    f"{API_V1}/work-items/{{work_item_id}}/stage",
    response_model=schemas.WorkItemResponse,
    tags=["Work"],
)
async def set_work_stage(
    work_item_id: int,
    payload: schemas.WorkStageUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """The worker moves their own work through its stages.  Affects nobody
    else's work item."""
    try:
        item = workflow.update_work_stage(
            db, work_item_id=work_item_id, new_stage=payload.stage,
            actor=current_user, context_id=_context_id(ctx), note=payload.note,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast(
        "WORK_STAGE_CHANGED", document_id=item.document_id, user_id=current_user.id
    )
    return serializers.work_item(item)


@app.post(
    f"{API_V1}/work-items/{{work_item_id}}/progress",
    response_model=schemas.ProgressResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Work"],
)
async def add_progress(
    work_item_id: int,
    payload: schemas.ProgressCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Free-text progress written by the person doing the work.  Stored as
    written - never converted to a number or merged with anyone else's."""
    try:
        update = workflow.submit_progress(
            db, work_item_id=work_item_id, description=payload.description,
            actor=current_user, context_id=_context_id(ctx), new_stage=payload.new_stage,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast(
        "PROGRESS_UPDATED", document_id=update.document_id, user_id=current_user.id
    )
    return serializers.progress(update)


@app.post(
    f"{API_V1}/work-items/{{work_item_id}}/progress-with-file",
    response_model=schemas.ProgressResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Work"],
)
async def add_progress_with_attachment(
    work_item_id: int,
    description: str = Form(...),
    new_stage: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Progress plus a supporting document in one step, so the file stays tied
    to the update it belongs to."""
    contents = b""
    if file is not None and file.filename:
        # Check the file first: a rejected file must not leave a progress
        # update (and its notification) behind.
        contents = await file.read()
        _validate_upload(file, contents)
    try:
        update = workflow.submit_progress(
            db, work_item_id=work_item_id, description=description,
            actor=current_user, context_id=_context_id(ctx),
            new_stage=WorkStage(new_stage) if new_stage else None,
        )
    except Exception as exc:
        raise _handle(exc)

    if file is not None and file.filename:
        crud.create_attachment(
            db=db,
            doc_id=update.document_id,
            progress_update_id=update.id,
            uploaded_by=current_user.id,
            file_name=file.filename,
            storage_key=_store_upload(update.document_id, file.filename, contents),
            file_type=file.content_type,
            file_size=len(contents),
            checksum=crud.compute_checksum(contents),
            attachment_type=AttachmentType.PROGRESS_ATTACHMENT,
            context_id=_context_id(ctx),
        )
        db.refresh(update)

    await crud.event_manager.broadcast(
        "PROGRESS_UPDATED", document_id=update.document_id, user_id=current_user.id
    )
    return serializers.progress(update)


@app.post(
    f"{API_V1}/work-items/{{work_item_id}}/submit",
    response_model=schemas.WorkItemResponse,
    tags=["Work"],
)
async def submit_work(
    work_item_id: int,
    payload: schemas.WorkSubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Hand in this person's work.  Goes to the HOD if validation is required,
    otherwise completes.  Neither closes the document."""
    try:
        item = workflow.submit_work(
            db, work_item_id=work_item_id, actor=current_user,
            context_id=_context_id(ctx), note=payload.note,
        )
    except Exception as exc:
        raise _handle(exc)
    await crud.event_manager.broadcast(
        "WORK_SUBMITTED", document_id=item.document_id, user_id=current_user.id
    )
    return serializers.work_item(item)


@app.post(
    f"{API_V1}/work-items/{{work_item_id}}/review",
    response_model=schemas.WorkReviewResponse,
    tags=["Work"],
)
async def review_work(
    work_item_id: int,
    payload: schemas.WorkReviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """HOD accepts or returns ONE person's work.  Accepting completes that
    person's item only - it never closes the branch's other work, and never
    closes the document."""
    try:
        review = workflow.review_work_item(
            db, work_item_id=work_item_id, outcome=payload.outcome,
            actor=current_user, context_id=_context_id(ctx), note=payload.note,
        )
    except Exception as exc:
        raise _handle(exc)
    item = db.query(models.WorkItem).filter(models.WorkItem.id == work_item_id).first()
    await crud.event_manager.broadcast(
        "WORK_REVIEWED", document_id=item.document_id if item else None, user_id=current_user.id
    )
    return serializers.work_review(review)


# =========================================================
# ATTACHMENTS
# =========================================================

@app.get(
    f"{API_V1}/documents/{{document_id}}/attachments",
    response_model=List[schemas.AttachmentResponse],
    tags=["Attachments"],
)
def list_attachments(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _authorized_document(db, document_id, current_user, ctx)
    return [serializers.attachment(a) for a in crud.get_attachments(db, document_id)]


@app.post(
    f"{API_V1}/documents/{{document_id}}/attachments",
    response_model=schemas.AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Attachments"],
)
async def upload_attachment(
    document_id: int,
    file: UploadFile = File(...),
    attachment_type: str = Form(default="SUPPORTING_DOCUMENT"),
    progress_update_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _authorized_document(db, document_id, current_user, ctx)
    try:
        kind = AttachmentType(str(attachment_type or "").strip().upper())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"attachment_type must be one of {', '.join(t.value for t in AttachmentType)}.",
        )
    if kind == AttachmentType.ORIGINAL and (not ctx or ctx.context_type != WorkContextType.DS):
        raise HTTPException(status_code=403, detail="Only the DS can add the original document.")
    if progress_update_id is not None:
        update = db.query(models.ProgressUpdate).filter(models.ProgressUpdate.id == progress_update_id).first()
        if update is None or update.document_id != document_id:
            raise HTTPException(status_code=422, detail="progress_update_id does not belong to this document.")
    contents = await file.read()
    _validate_upload(file, contents)
    duplicate = crud.find_duplicate_attachment(db, crud.compute_checksum(contents), document_id=document_id)
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This file is already attached to this document as \"{duplicate.file_name}\".",
        )
    att = crud.create_attachment(
        db=db,
        doc_id=document_id,
        progress_update_id=progress_update_id,
        uploaded_by=current_user.id,
        file_name=file.filename,
        storage_key=_store_upload(document_id, file.filename, contents),
        file_type=file.content_type,
        file_size=len(contents),
        checksum=crud.compute_checksum(contents),
        attachment_type=kind,
        context_id=_context_id(ctx),
    )
    await crud.event_manager.broadcast(
        "ATTACHMENT_ADDED", document_id=document_id, user_id=current_user.id
    )
    return serializers.attachment(att)


@app.get(f"{API_V1}/attachments/{{attachment_id}}/download", tags=["Attachments"])
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    att = crud.get_attachment(db, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    if att.document_id:
        _authorized_document(db, att.document_id, current_user, ctx)
    elif not ctx or ctx.context_type not in (WorkContextType.DS, WorkContextType.ADMIN):
        # Mailbox attachments not yet registered as a document: DS intake only.
        raise HTTPException(status_code=403, detail="Only the DS can open unregistered intake attachments.")

    for base in (UPLOAD_DIR, Path(__file__).parent / "uploads", _PROJECT_ROOT / "uploads"):
        candidate = Path(base) / att.storage_key
        if candidate.exists():
            return FileResponse(
                path=str(candidate),
                filename=att.file_name,
                media_type=att.file_type or "application/octet-stream",
            )
    raise HTTPException(status_code=404, detail="Stored file is missing from disk.")


# =========================================================
# OCR & ROUTING INTELLIGENCE (assistive only)
# =========================================================

@app.get(f"{API_V1}/documents/{{document_id}}/ocr", response_model=schemas.OCRResponse, tags=["OCR"])
def get_ocr(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    doc = _authorized_document(db, document_id, current_user, ctx)
    record = intelligence.get_document_ocr(db, document_id)
    fields = [
        schemas.ExtractedFieldResponse(
            id=f.id, document_id=f.document_id, field_name=f.field_name,
            extracted_value=f.extracted_value, verified_value=f.verified_value,
            effective_value=f.effective_value, confidence=f.confidence,
            source_page=f.source_page, verified_by=f.verified_by, verified_at=f.verified_at,
        )
        for f in doc.extracted_fields
    ]
    if not record:
        return schemas.OCRResponse(document_id=document_id, ocr_status=doc.ocr_status, fields=fields)
    return schemas.OCRResponse(
        id=record.id, document_id=document_id, extracted_text=record.extracted_text,
        ocr_status=record.ocr_status, ocr_engine=record.ocr_engine, confidence=record.confidence,
        processed_at=record.processed_at, error_message=record.error_message, fields=fields,
    )


@app.post(f"{API_V1}/documents/{{document_id}}/ocr/run", response_model=schemas.OCRResponse, tags=["OCR"])
def run_ocr(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Document processing is a DS action.")
    _authorized_document(db, document_id, current_user, ctx)
    intelligence.reanalyze_document_ocr(db, document_id)
    return get_ocr(document_id, db, current_user, ctx)


@app.post(
    f"{API_V1}/documents/{{document_id}}/verify-field",
    response_model=schemas.ExtractedFieldResponse,
    tags=["OCR"],
)
def verify_field(
    document_id: int,
    payload: schemas.FieldVerifyRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """The DS corrects an extracted value.  The original is kept for
    provenance; the verified value is what the system trusts."""
    if not ctx or ctx.context_type != WorkContextType.DS:
        raise HTTPException(status_code=403, detail="Only the DS verifies extracted fields.")
    _authorized_document(db, document_id, current_user, ctx)
    field = intelligence.verify_extracted_field(
        db, document_id, payload.field_name, payload.verified_value, current_user
    )
    return schemas.ExtractedFieldResponse(
        id=field.id, document_id=field.document_id, field_name=field.field_name,
        extracted_value=field.extracted_value, verified_value=field.verified_value,
        effective_value=field.effective_value, confidence=field.confidence,
        source_page=field.source_page, verified_by=field.verified_by, verified_at=field.verified_at,
    )


@app.get(
    f"{API_V1}/documents/{{document_id}}/routing-suggestion",
    response_model=Optional[schemas.RoutingSuggestionResponse],
    tags=["OCR"],
)
def routing_suggestion(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _authorized_document(db, document_id, current_user, ctx)
    suggestion = intelligence.get_routing_suggestion(db, document_id)
    if not suggestion:
        return None
    return schemas.RoutingSuggestionResponse(
        id=suggestion.id, document_id=suggestion.document_id,
        suggested_department_id=suggestion.suggested_department_id,
        suggested_department_name=suggestion.suggested_department_name,
        suggested_employee_id=suggestion.suggested_employee_id,
        suggested_employee_name=suggestion.suggested_employee_name,
        routing_confidence=suggestion.routing_confidence,
        routing_reason=suggestion.routing_reason,
        routing_source=suggestion.routing_source,
        is_director_instruction=bool(suggestion.is_director_instruction),
        ranked_departments=suggestion.ranked_departments or [],
        generated_at=suggestion.generated_at,
    )


@app.post(
    f"{API_V1}/documents/{{document_id}}/analyze-routing",
    response_model=Optional[schemas.RoutingSuggestionResponse],
    tags=["OCR"],
)
def analyze_routing(
    document_id: int,
    payload: schemas.RoutingAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _authorized_document(db, document_id, current_user, ctx)
    intelligence.generate_routing_suggestion(
        db, document_id, include_director_remark=payload.include_director_remark
    )
    return routing_suggestion(document_id, db, current_user, ctx)


# =========================================================
# NOTIFICATIONS & REMINDERS
# =========================================================

@app.get(f"{API_V1}/notifications", response_model=List[schemas.NotificationResponse], tags=["Notifications"])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    return [
        serializers.notification(n)
        for n in crud.get_notifications(db, current_user.id, _context_id(ctx))
    ]


@app.get(
    f"{API_V1}/notifications/unread",
    response_model=List[schemas.NotificationResponse],
    tags=["Notifications"],
)
def unread_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    return [
        serializers.notification(n)
        for n in crud.get_unread_notifications(db, current_user.id, _context_id(ctx))
    ]


@app.patch(f"{API_V1}/notifications/{{notification_id}}/read", tags=["Notifications"])
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    note = crud.mark_notification_read(db, notification_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"detail": "Marked as read."}


@app.patch(f"{API_V1}/notifications/read-all", tags=["Notifications"])
def read_all_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    return {"updated": crud.mark_all_notifications_read(db, current_user.id, _context_id(ctx))}


@app.get(f"{API_V1}/reminders", response_model=List[schemas.ReminderResponse], tags=["Reminders"])
def list_reminders(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return [serializers.reminder(r) for r in crud.get_reminders(db, current_user.id)]


@app.post(f"{API_V1}/reminders/check", response_model=schemas.ReminderCheckResponse, tags=["Reminders"])
def check_reminders(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Raise reminders for work items that are due soon or overdue.  Reminders
    are per work item so each person hears about their own deadline."""
    created = workflow.generate_deadline_reminders(db)
    return schemas.ReminderCheckResponse(
        generated=len(created), reminders=[serializers.reminder(r) for r in created]
    )


@app.patch(f"{API_V1}/reminders/{{reminder_id}}/read", tags=["Reminders"])
def read_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rem = crud.mark_reminder_read(db, reminder_id, current_user.id)
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"detail": "Marked as read."}


@app.post(
    f"{API_V1}/documents/{{document_id}}/remind",
    response_model=schemas.ReminderSendResponse,
    tags=["Reminders"],
)
def send_reminder(
    document_id: int,
    payload: schemas.ReminderSendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    try:
        sent = crud.send_manual_reminder(
            db, document_id, current_user, _context_id(ctx),
            payload.work_item_id, payload.recipient_user_id, payload.message,
        )
    except Exception as exc:
        raise _handle(exc)
    return schemas.ReminderSendResponse(sent=sent, detail=f"Reminder sent to {sent} recipient(s).")


# =========================================================
# DASHBOARD
# =========================================================

@app.get(f"{API_V1}/dashboard", response_model=schemas.DashboardResponse, tags=["Dashboard"])
def dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    return serializers.dashboard(
        db, workflow.dashboard_for_context(db, current_user, _context_id(ctx))
    )


# =========================================================
# ADMINISTRATION
# =========================================================

def _require_admin(ctx: Optional[models.WorkContextMembership]) -> models.WorkContextMembership:
    if not ctx or ctx.context_type != WorkContextType.ADMIN:
        raise HTTPException(status_code=403, detail="Administration requires the Admin context.")
    return ctx


@app.get(f"{API_V1}/admin/users", response_model=List[schemas.UserResponse], tags=["Admin"])
def admin_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    return [
        serializers.user(u, crud.get_user_context_memberships(db, u.id))
        for u in crud.get_users(db)
    ]


@app.post(
    f"{API_V1}/admin/users",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin"],
)
def admin_create_user(
    payload: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    try:
        user = crud.create_admin_user(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return serializers.user(user)


@app.put(f"{API_V1}/admin/users/{{user_id}}", response_model=schemas.UserResponse, tags=["Admin"])
def admin_update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    user = crud.update_admin_user(db, user_id, payload, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return serializers.user(user, crud.get_user_context_memberships(db, user.id))


@app.post(f"{API_V1}/admin/users/{{user_id}}/reset-password", tags=["Admin"])
def admin_reset_password(
    user_id: int,
    payload: schemas.AdminPasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    if not crud.reset_user_password(db, user_id, payload.new_password, current_user.id):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"detail": "Password reset."}


@app.post(f"{API_V1}/admin/users/{{user_id}}/toggle-active", tags=["Admin"])
def admin_toggle_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    result = crud.toggle_user_active(db, user_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"is_active": result}


@app.get(
    f"{API_V1}/admin/users/{{user_id}}/contexts",
    response_model=List[schemas.WorkContextResponse],
    tags=["Admin"],
)
def admin_user_contexts(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    return [serializers.context(c) for c in crud.get_user_context_memberships(db, user_id)]


@app.post(
    f"{API_V1}/admin/users/{{user_id}}/contexts",
    response_model=schemas.WorkContextResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin"],
)
def admin_grant_context(
    user_id: int,
    payload: schemas.WorkContextCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Give a user another hat, e.g. HOD-Engineering on top of
    Employee-Product."""
    _require_admin(ctx)
    payload.user_id = user_id
    try:
        membership = crud.create_work_context_membership(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return serializers.context(membership)


@app.delete(f"{API_V1}/admin/users/{{user_id}}/contexts/{{context_id}}", tags=["Admin"])
def admin_revoke_context(
    user_id: int,
    context_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    try:
        membership = crud.deactivate_work_context_membership(db, context_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not membership:
        raise HTTPException(status_code=404, detail="Work context not found.")
    return {"detail": "Work context revoked."}


@app.get(f"{API_V1}/admin/tso", response_model=Optional[schemas.WorkContextResponse], tags=["Admin"])
def admin_get_tso(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """The organisation designates exactly one TSO at a time."""
    _require_admin(ctx)
    tso = crud.get_single_active_tso(db)
    return serializers.context(tso) if tso else None


@app.post(f"{API_V1}/admin/tso/{{user_id}}/activate", response_model=schemas.WorkContextResponse, tags=["Admin"])
def admin_set_tso(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    try:
        membership = crud.set_active_tso(db, user_id, current_user.id)
    except Exception as exc:
        raise _handle(exc)
    return serializers.context(membership)


@app.get(f"{API_V1}/admin/departments", response_model=List[schemas.DepartmentResponse], tags=["Admin"])
def admin_departments(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    return crud.get_departments(db, include_inactive=include_inactive)


@app.post(
    f"{API_V1}/admin/departments",
    response_model=schemas.DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin"],
)
def admin_create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    try:
        return crud.create_admin_department(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put(f"{API_V1}/admin/departments/{{dept_id}}", response_model=schemas.DepartmentResponse, tags=["Admin"])
def admin_update_department(
    dept_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    dept = crud.update_admin_department(db, dept_id, payload, current_user.id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    return dept


@app.get(f"{API_V1}/admin/settings", tags=["Admin"])
def admin_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    return crud.get_system_settings(db)


@app.post(f"{API_V1}/admin/settings", tags=["Admin"])
def admin_update_setting(
    payload: schemas.SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    _require_admin(ctx)
    setting = crud.update_system_setting(
        db, payload.key, payload.value, payload.description, current_user.id
    )
    return {"key": setting.key, "value": setting.value}


@app.get(f"{API_V1}/admin/audit-logs", response_model=List[schemas.AuditLogResponse], tags=["Admin"])
def admin_audit_logs(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    ctx: Optional[models.WorkContextMembership] = Depends(get_active_context),
):
    """Administrative and configuration activity only.  Document workflow
    activity lives in the document's own history."""
    _require_admin(ctx)
    logs = crud.get_audit_logs(db, limit, offset)
    for log in logs:
        if log.user:
            log.user_name = log.user.username
    return logs
