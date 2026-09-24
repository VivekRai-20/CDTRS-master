"""Document service: the register, one document, and DS metadata/closure.

Thin over the repository.  The backend is authoritative for permissions, the
active work context and concurrency; this layer exists so pages never touch
HTTP directly.
"""

from typing import Any, Dict, List, Optional

from models.document import DocumentModel
from repositories.provider import get_repository


class DocumentService:

    # ---------------- reading ----------------

    def get_documents(self, **filters: Any) -> List[DocumentModel]:
        """Every document the active context may open."""
        return get_repository().get_documents(**filters)

    def get_inbox(self) -> List[DocumentModel]:
        """Only what the active context must act on now."""
        return get_repository().get_inbox()

    def get_document(self, document_id: int) -> Optional[DocumentModel]:
        """Full detail: branches, every person's work item, remarks, history."""
        return get_repository().get_document(document_id)

    # ---------------- intake / registration (DS) ----------------

    def get_intake_items(self) -> List[Dict[str, Any]]:
        return get_repository().get_intake_items()

    def sync_outlook(self) -> Dict[str, Any]:
        return get_repository().sync_outlook()

    def process_intake(self, intake_id: int, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        return get_repository().process_intake(intake_id, payload)

    def manual_upload(self, fields: Dict[str, Any], file_path: str) -> Optional[DocumentModel]:
        return get_repository().manual_upload(fields, file_path)

    def create_document(self, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        return get_repository().create_document(payload)

    def update_document(self, document_id: int, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        """DS corrects extracted or entered details.  Every change is recorded
        in the document's history."""
        return get_repository().update_document(document_id, payload)

    def register_document(self, document_id: int) -> Optional[DocumentModel]:
        return get_repository().register_document(document_id)

    # ---------------- OCR extraction (advisory; DS verifies) ----------------

    def get_ocr_result(self, document_id: int) -> Dict[str, Any]:
        """OCR text, status and extracted fields (with any DS-verified values)."""
        return get_repository().get_ocr_result(document_id)

    def verify_ocr_field(self, document_id: int, field_name: str, verified_value: str) -> Dict[str, Any]:
        """DS confirms or corrects an OCR-extracted value.  The verified value
        is what the workflow trusts; the original extraction is kept."""
        return get_repository().verify_field(document_id, field_name, verified_value)

    # ---------------- closure (DS only) ----------------

    def close_document(
        self,
        document_id: int,
        remark: Optional[str] = None,
        force: bool = False,
        expected_version: Optional[int] = None,
    ) -> Optional[DocumentModel]:
        """Only the DS closes a document.  `force` is required when workstreams
        are still open, and cancels them explicitly rather than silently."""
        return get_repository().close_document(
            document_id, remark=remark, force=force, expected_version=expected_version
        )

    def reopen_document(self, document_id: int, reason: Optional[str] = None) -> Optional[DocumentModel]:
        return get_repository().reopen_document(document_id, reason)

    # ---------------- history & remarks ----------------

    def get_history(self, document_id: int):
        return get_repository().get_workflow_history(document_id)

    def get_all_history(self, limit: int = 500):
        return get_repository().get_all_audit_history(limit)

    def get_remarks(self, document_id: int):
        return get_repository().get_remarks(document_id)

    def get_director_reviews(self, document_id: int):
        """Every Director review, oldest first.  None replaces another."""
        return get_repository().get_director_reviews(document_id)

    # ---------------- reminders ----------------

    def send_reminder(
        self,
        document_id: int,
        work_item_id: Optional[int] = None,
        recipient_user_id: Optional[int] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        return get_repository().send_document_reminder(
            document_id, work_item_id, recipient_user_id, message
        )


document_service = DocumentService()
