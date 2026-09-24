"""Work service: one person's work item - stages, progress, submission and
HOD validation.

This is the service behind Employee Tasks, TSO Tasks and the per-person cards
in the document view.  Everything it does is scoped to a single work item, so
one person's actions can never overwrite another's.
"""

from typing import Any, Dict, List, Optional

from models import ProgressModel, WorkItemModel
from models.enums import WorkStageEnum
from repositories.provider import get_repository


class WorkService:

    # =========================================================
    # READING
    # =========================================================

    def my_work_items(self, include_finished: bool = False) -> List[WorkItemModel]:
        """The caller's own tasks, for the hat they are currently wearing.

        A user who is Employee-Product and also TSO sees two entirely
        separate task lists depending on the active context.
        """
        return get_repository().get_my_work_items(include_finished)

    def department_work_items(self) -> List[WorkItemModel]:
        """HOD view: every individual's work across the department's
        workstreams, so nobody's contribution is hidden behind a team."""
        return get_repository().get_department_work_items()

    def document_work_items(self, document_id: int) -> List[WorkItemModel]:
        return get_repository().get_document_work_items(document_id)

    def get_work_item(self, work_item_id: int) -> Optional[WorkItemModel]:
        return get_repository().get_work_item(work_item_id)

    # =========================================================
    # WORKER ACTIONS
    # =========================================================

    @staticmethod
    def selectable_stages() -> List[WorkStageEnum]:
        """Stages a worker may set on their own work.  Finishing goes through
        Submit; only an HOD or the DS can return or cancel work."""
        return WorkStageEnum.worker_selectable()

    def set_stage(
        self, work_item_id: int, stage: str, note: Optional[str] = None
    ) -> Optional[WorkItemModel]:
        return get_repository().set_work_stage(work_item_id, stage, note)

    def add_progress(
        self,
        work_item_id: int,
        description: str,
        new_stage: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Optional[ProgressModel]:
        """Write a free-text progress update, optionally with a supporting
        file attached to that update.

        The text is stored exactly as written.  There is no percentage in this
        system and no combined or averaged figure anywhere.
        """
        if file_path:
            return get_repository().submit_progress_with_file(
                work_item_id, description, file_path, new_stage
            )
        return get_repository().submit_progress(work_item_id, description, new_stage)

    def submit(self, work_item_id: int, note: Optional[str] = None) -> Optional[WorkItemModel]:
        """Hand this person's work in.

        If the work needs HOD validation it moves to Under Review; otherwise
        it completes.  Neither outcome closes the document - only the DS
        does that.
        """
        return get_repository().submit_work(work_item_id, note)

    # =========================================================
    # HOD VALIDATION
    # =========================================================

    def accept(self, work_item_id: int, note: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Accept ONE person's work.  Completes their item only; other people
        on the same workstream are untouched."""
        return get_repository().review_work_item(work_item_id, "ACCEPTED", note)

    def return_for_rework(
        self, work_item_id: int, note: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Send ONE person's work back to them, with a note explaining why."""
        return get_repository().review_work_item(work_item_id, "RETURNED", note)


work_service = WorkService()
