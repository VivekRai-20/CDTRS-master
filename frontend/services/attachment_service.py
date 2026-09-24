from typing import List, Optional

from models import AttachmentModel
from repositories.provider import get_repository


class AttachmentService:
    """Supporting documents."""

    def get_attachments(self, document_id: int) -> List[AttachmentModel]:
        return get_repository().get_attachments(document_id)

    def get_document_attachments(
        self,
        document_id: int,
    ) -> List[AttachmentModel]:
        return self.get_attachments(document_id)

    def upload(
        self,
        document_id: int,
        file_path: str,
        attachment_type: str = "SUPPORTING_DOCUMENT",
        progress_update_id: Optional[int] = None,
    ) -> Optional[AttachmentModel]:
        return get_repository().upload_attachment(
            document_id,
            file_path,
            attachment_type,
            progress_update_id,
        )

    def download(
        self,
        attachment_id: int,
        dest_path: str,
    ) -> Optional[str]:
        return get_repository().download_attachment(
            attachment_id,
            dest_path,
        )


attachment_service = AttachmentService()