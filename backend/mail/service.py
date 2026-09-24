# ==============================================================================
# PZ_26/08 - Central Domain Mail Service & Notification Dispatcher
# Coordinates idempotent inbox synchronization, server attachment storage,
# SHA-256 integrity checksums, and workflow email notifications.
# ==============================================================================

import os
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

import models
import schemas
import crud

from .base import BaseMailProvider, EmailAttachmentDTO, IncomingEmailDTO, OutgoingEmailDTO
from .outlook_provider import OutlookGraphProvider
from .intranet_provider import IntranetMailProvider

logger = logging.getLogger("cdtrs.mail.service")


# ==============================================================================
# TEST RECIPIENT EMAIL OVERRIDE
# ==============================================================================
#
# IMPORTANT:
# Disabled by default.
#
# If you explicitly want to redirect ALL outgoing workflow emails to a
# test address, set:
#
# OVERRIDE_TEST_RECIPIENT_EMAIL=test@example.com
#
# Otherwise leave it empty/None/false.
# ==============================================================================

_env_override = os.getenv(
    "OVERRIDE_TEST_RECIPIENT_EMAIL",
    ""
).strip()

OVERRIDE_TEST_RECIPIENT_EMAIL: Optional[str] = (
    None
    if _env_override.lower() in {
        "",
        "none",
        "false",
        "off",
    }
    else _env_override
)


NOTIFICATION_TEMPLATES: Dict[str, tuple] = {
    "DOCUMENT_SENT_TO_DIRECTOR": (
        "Document Sent for Director Review",
        "Document {ref} ('{title}') has been submitted for your executive review."
    ),
    "DOCUMENT_RETURNED_TO_DS": (
        "Director Review Completed",
        "Director has completed review for document {ref} ('{title}') and returned it with guidance."
    ),
    "DOCUMENT_ROUTED_TO_HOD": (
        "Document Routed to Your Department",
        "Document {ref} ('{title}') has been assigned to your department for processing."
    ),
    "EMPLOYEE_ASSIGNED": (
        "New Work Assignment",
        "You have been assigned to execute document {ref} ('{title}')."
    ),
    "EMPLOYEE_UPDATE_PENDING_HOD": (
        "Execution Progress Requires HOD Validation",
        "Staff member {employee_name} has submitted a progress update for document {ref} that requires your review and approval."
    ),
    "HOD_APPROVED_UPDATE": (
        "Progress Update Approved by HOD",
        "Department Head has approved the progress update for document {ref} ('{title}') and forwarded it to DS."
    ),
    "HOD_RETURNED_UPDATE": (
        "Progress Update Returned for Correction",
        "Department Head has reviewed your update for document {ref} and requested corrections:\n{note}"
    ),
    "EMPLOYEE_UPDATE_DIRECT_TO_DS": (
        "Progress Update Submitted",
        "Staff member {employee_name} has submitted an execution progress update for document {ref} ('{title}')."
    ),
    "DIRECTOR_FOLLOWUP_SUBMITTED": (
        "Progress Follow-Up for Director",
        "Execution progress updates for document {ref} ('{title}') have been forwarded for Director review."
    ),
    "ACTION_REMINDER": (
        "Action Reminder",
        "Official action reminder: Action is pending on document {ref} ('{title}')."
    ),
    "DOCUMENT_CLOSED": (
        "Document Lifecycle Closed",
        "Document {ref} ('{title}') has been closed."
    ),
}


class MailService:
    """
    Central Domain Mail Service for CDTRS.
    Manages incoming mailbox sync, idempotent ingestion, attachment persistence,
    and workflow-state triggered notifications.
    """

    def __init__(self):
        self._providers: Dict[str, BaseMailProvider] = {
            "outlook": OutlookGraphProvider(),
            "intranet": IntranetMailProvider(),
            "local": IntranetMailProvider(),
            "smtp_imap": IntranetMailProvider(),
            "gov_mail": IntranetMailProvider(),
        }
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def get_default_channel(self) -> str:
        return os.getenv("MAIL_CHANNEL", "outlook").lower()

    def get_provider(self, channel: Optional[str] = None) -> BaseMailProvider:
        target_channel = (channel or self.get_default_channel()).lower()
        return self._providers.get(target_channel) or self._providers["outlook"]

    def is_configured(self, channel: Optional[str] = None) -> bool:
        provider = self.get_provider(channel)
        return provider.is_configured()

    def sync_ds_mailbox(self, db: Session, max_count: int = 50, channel: Optional[str] = None) -> schemas.OutlookSyncResponse:
        """
        Synchronizes the DS mailbox (via Cloud Outlook Graph API or Local Intranet IMAP):
        1. Checks configuration.
        2. Retrieves new incoming messages with attachments.
        3. Enforces idempotency via external_message_id.
        4. Persists attachments to server filesystem (uploads/<year>/intake_<msg_id>/<file>).
        5. Registers IncomingMessage and Attachment records.
        """
        active_channel = channel or self.get_default_channel()
        provider = self.get_provider(active_channel)
        channel_label = "Intranet IMAP" if active_channel in ("intranet", "local", "smtp_imap") else "Outlook"

        if not provider.is_configured():
            return schemas.OutlookSyncResponse(
                status="not_configured",
                synced_count=0,
                ignored_duplicates=0,
                message=f"{channel_label} mail integration is not configured. Check your environment settings."
            )

        try:
            incoming_emails = provider.fetch_incoming_emails(max_count=max_count, unread_only=True)
        except Exception as ex:
            logger.error(f"Mail sync exception: {ex}")
            return schemas.OutlookSyncResponse(
                status="error",
                synced_count=0,
                ignored_duplicates=0,
                message=f"{channel_label} sync failed: {str(ex)}"
            )

        synced_count = 0
        ignored_count = 0
        details: List[dict] = []

        for email in incoming_emails:
            # Idempotency check: Skip if external message ID already stored
            existing = db.query(models.IncomingMessage).filter(
                models.IncomingMessage.external_message_id == email.message_id
            ).first()

            if existing:
                ignored_count += 1
                continue

            # 1. Create IncomingMessage
            inc_msg = models.IncomingMessage(
                source_type=models.SourceType.OUTLOOK,
                external_message_id=email.message_id,
                sender_name=email.sender_name or email.sender_email or "Outlook Dispatch",
                sender_email=email.sender_email,
                subject=email.subject,
                received_at=email.received_at,
                body_reference=email.body_text,
                has_attachments=bool(email.attachments),
                processing_status=models.MessageProcessingStatus.NEW,
                created_at=datetime.now()
            )
            db.add(inc_msg)
            db.commit()
            db.refresh(inc_msg)

            # 2. Persist Attachments
            if email.attachments:
                dest_dir = self.upload_dir / str(datetime.utcnow().year) / f"intake_{inc_msg.id}"
                dest_dir.mkdir(parents=True, exist_ok=True)

                for att in email.attachments:
                    sanitized_name = "".join(c for c in att.filename if c.isalnum() or c in "._- ") or "attachment.pdf"
                    dest_path = dest_dir / sanitized_name
                    with open(dest_path, "wb") as fh:
                        fh.write(att.content_bytes)

                    checksum = hashlib.sha256(att.content_bytes).hexdigest()
                    storage_key = str(dest_path.relative_to(self.upload_dir))

                    db_att = models.Attachment(
                        document_id=None,  # Nullable until canonical document is registered
                        progress_update_id=None,
                        uploaded_by_user_id=1,  # Default system/DS user ID
                        file_name=att.filename,
                        storage_key=storage_key,
                        file_type=att.content_type,
                        file_size=att.size_bytes,
                        checksum=checksum,
                        attachment_type=models.AttachmentType.ORIGINAL,
                        source_message_id=inc_msg.id,
                        created_at=datetime.now()
                    )
                    db.add(db_att)

                db.commit()

            # Mark as read in remote mailbox
            try:
                provider.mark_as_read(email.message_id)
            except Exception:
                pass

            synced_count += 1
            details.append({
                "id": inc_msg.id,
                "subject": inc_msg.subject,
                "sender": inc_msg.sender_email,
                "attachments_count": len(email.attachments)
            })

        msg_text = f"Successfully synced {synced_count} new email(s) from DS Outlook mailbox."
        if ignored_count > 0:
            msg_text += f" ({ignored_count} duplicate(s) skipped)."

        return schemas.OutlookSyncResponse(
            status="success",
            synced_count=synced_count,
            ignored_duplicates=ignored_count,
            message=msg_text,
            details=details
        )

    def resolve_user_email(self, user: models.User) -> Optional[str]:
        """
        Resolves the authoritative email address for a user according to preferred channel.
        If OVERRIDE_TEST_RECIPIENT_EMAIL is configured, routes all test emails to that address.
        """
        if OVERRIDE_TEST_RECIPIENT_EMAIL:
            return OVERRIDE_TEST_RECIPIENT_EMAIL

        if not user:
            return None
        pref = (user.preferred_mail_channel or "outlook").lower()
        if pref == "outlook" and user.outlook_email:
            return user.outlook_email
        elif pref == "gov_mail" and user.gov_email:
            return user.gov_email
        return user.email or user.outlook_email or user.gov_email

    def dispatch_workflow_event(
        self,
        db: Session,
        event_type: str,
        doc_id: int,
        recipient_user_id: int,
        context: Optional[Dict[str, Any]] = None,
        channel: Optional[str] = None,
        work_item_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        include_progress_attachments: bool = False,
    ) -> bool:
        """
        Centrally dispatches in-app notification and email notification for a workflow event.
        Template is resolved from NOTIFICATION_TEMPLATES.
        """
        ctx = context or {}
        template_info = NOTIFICATION_TEMPLATES.get(event_type)
        if not template_info:
            title = ctx.get("title", f"Workflow Notice ({event_type})")
            message = ctx.get("message", "A workflow action was performed on this document.")
        else:
            title_tpl, msg_tpl = template_info
            try:
                title = title_tpl.format(**ctx)
                message = msg_tpl.format(**ctx)
            except Exception:
                title = title_tpl
                message = msg_tpl

        # 1. Create In-App Notification (Always succeeds)
        try:
            notif = models.Notification(
                user_id=recipient_user_id,
                document_id=doc_id,
                title=title,
                message=message,
                is_read=False,
                created_at=datetime.now()
            )
            db.add(notif)
            db.commit()
        except Exception as ex:
            logger.warning(f"Failed to create in-app notification: {ex}")
            db.rollback()

        # 2. Dispatch Email (if provider is configured and recipient email exists)
        try:
            return self.send_workflow_notification(
                db=db,
                doc_id=doc_id,
                recipient_user_id=recipient_user_id,
                title=title,
                message=message,
                channel=channel,
                work_item_id=work_item_id,
                branch_id=branch_id,
                include_progress_attachments=include_progress_attachments
            )
        except Exception as ex:
            logger.warning(f"Failed to dispatch workflow email for event '{event_type}': {ex}")
            return False

    def send_workflow_notification(
    self,
    db: Session,
    doc_id: int,
    recipient_user_id: int,
    title: str,
    message: str,
    work_item_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    include_progress_attachments: bool = False,
    channel: Optional[str] = None,
) -> bool:
        """
        Dispatches an outgoing workflow notification email to the responsible user.
        """
        user = db.query(models.User).filter(models.User.id == recipient_user_id).first()
        doc = db.query(models.Document).filter(models.Document.doc_id == doc_id).first()
        if not user or not doc:
            return False

        recipient_email = self.resolve_user_email(user)
        if not recipient_email:
            logger.warning(f"User {user.username} (ID: {user.id}) has no configured email address. Email skipped.")
            return False

        use_channel = channel or user.preferred_mail_channel or self.get_default_channel()
        provider = self.get_provider(use_channel)

        if not provider.is_configured():
            logger.info(f"Mail provider '{use_channel}' not configured. Notification logged to database only.")
            return False

        subject = f"[CDTRS] {title} - {doc.reference_no}"
        body_text = f"""Central Document Tracking & Routing System (CDTRS)
-----------------------------------------------------------
Action Notice: {title}
Document Ref : {doc.reference_no}
Title / Subj : {doc.title}
Priority     : {doc.priority.value}
Deadline     : {doc.deadline or 'Not Specified'}
Lifecycle    : {doc.lifecycle.value}

Message / Instructions:
{message}

Please log in to CDTRS to view or process this document.
"""
        body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #E2E8F0; border-radius: 8px;">
  <h2 style="color: #0F172A; margin-bottom: 4px;">CDTRS Official Action Notice</h2>
  <p style="color: #64748B; font-size: 13px; margin-top: 0;">Central Document Tracking & Routing System</p>
  <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 16px 0;" />
  <p style="font-size: 15px; font-weight: 600; color: #1E293B;">{title}</p>
  <table style="width: 100%; font-size: 13px; color: #334155; margin: 16px 0; border-collapse: collapse;">
    <tr><td style="padding: 6px 0; font-weight: 600; width: 140px;">Reference No:</td><td>{doc.reference_no}</td></tr>
    <tr><td style="padding: 6px 0; font-weight: 600;">Title / Subject:</td><td>{doc.title}</td></tr>
    <tr><td style="padding: 6px 0; font-weight: 600;">Priority:</td><td><span style="background: #0F172A; color: white; padding: 2px 8px; border-radius: 4px; font-weight: 600;">{doc.priority.value}</span></td></tr>
    <tr><td style="padding: 6px 0; font-weight: 600;">Deadline:</td><td>{doc.deadline or 'Not Specified'}</td></tr>
    <tr><td style="padding: 6px 0; font-weight: 600;">Lifecycle:</td><td>{doc.lifecycle.value}</td></tr>
  </table>
  <div style="background-color: #F8FAFC; border-left: 4px solid #0F172A; padding: 12px; margin: 16px 0; font-size: 13px; color: #1E293B;">
    <strong>Instructions / Directives:</strong><br/>
    {message}
  </div>
  <p style="font-size: 12px; color: #94A3B8; margin-top: 24px;">This is an automated workflow notification from the CDTRS Institutional Management Server.</p>
</div>
"""
        # ==============================================================
        # SELECT EMAIL ATTACHMENTS
        # ==============================================================
        # Rules:
        # 1. If this notification is NOT tied to a WorkItem:
        #    - send only the original/source document attachments.
        #    - NEVER attach employee progress files.
        #
        # 2. If this notification IS tied to a WorkItem:
        #    - send the original/source document attachments
        #    - PLUS progress attachments belonging ONLY to that WorkItem.
        #
        # This prevents one employee's submitted files from being sent
        # to unrelated users or branches.

        attachments_to_send: List[EmailAttachmentDTO] = []

        attachment_query = db.query(models.Attachment).filter(
            models.Attachment.document_id == doc.doc_id
        )

        if include_progress_attachments and work_item_id is not None:
            # ----------------------------------------------------------
            # Work-specific notification:
            # original document + this person's progress attachments
            # ----------------------------------------------------------
            document_attachments = attachment_query.filter(
                models.Attachment.attachment_type.in_([
                    models.AttachmentType.ORIGINAL,
                    models.AttachmentType.EMAIL_ATTACHMENT,
                    models.AttachmentType.SUPPORTING_DOCUMENT,
                ])
            ).all()

            progress_attachments = (
                db.query(models.Attachment)
                .join(
                    models.ProgressUpdate,
                    models.ProgressUpdate.id == models.Attachment.progress_update_id,
                )
                .filter(
                    models.ProgressUpdate.work_item_id == work_item_id,
                    models.ProgressUpdate.document_id == doc.doc_id,
                    models.Attachment.attachment_type == models.AttachmentType.PROGRESS_ATTACHMENT,
                )
                .all()
            )

            selected_attachments = document_attachments + progress_attachments

        else:
            # ----------------------------------------------------------
            # Normal routing / assignment / reminder / Director notice:
            # NEVER send employee progress attachments.
            # ----------------------------------------------------------
            selected_attachments = attachment_query.filter(
                models.Attachment.attachment_type.in_([
                    models.AttachmentType.ORIGINAL,
                    models.AttachmentType.EMAIL_ATTACHMENT,
                    models.AttachmentType.SUPPORTING_DOCUMENT,
                ])
            ).all()

        for att in selected_attachments:
            if not att.storage_key:
                continue

            att_file_path = self.upload_dir / att.storage_key

            if not att_file_path.exists():
                logger.warning(
                    f"Attachment file not found: {att.file_name} "
                    f"(storage_key={att.storage_key})"
                )
                continue

            try:
                with open(att_file_path, "rb") as fh:
                    raw_bytes = fh.read()

                attachments_to_send.append(
                    EmailAttachmentDTO(
                        filename=att.file_name or "document.pdf",
                        content_type=att.file_type or "application/pdf",
                        size_bytes=len(raw_bytes),
                        content_bytes=raw_bytes,
                    )
                )

            except Exception as ex:
                logger.warning(
                    f"Could not load attachment {att.file_name} "
                    f"for email: {ex}"
                )
        outgoing_dto = OutgoingEmailDTO(
            recipient_email=recipient_email,
            recipient_name=user.full_name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments_to_send if attachments_to_send else None
        )

        return provider.send_email(outgoing_dto)


mail_service = MailService()
