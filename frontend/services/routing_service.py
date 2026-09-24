"""Routing service: opening workstreams, assigning people, Director review.

Routing in CDTRS means opening BRANCHES.  A single routing action may open
several at once - a Director review, one or more HODs, direct employees and
the TSO - and they then run independently at their own stages.
"""

from typing import Any, Dict, List, Optional

from models import BranchModel, DirectorReviewModel, RemarkModel, WorkItemModel
from repositories.provider import get_repository


class RoutingService:

    # =========================================================
    # READING BRANCHES
    # =========================================================

    def get_branches(self, document_id: int) -> List[BranchModel]:
        return get_repository().get_document_branches(document_id)

    # =========================================================
    # DS ROUTING
    # =========================================================

    def route(
        self,
        document_id: int,
        branches: List[Dict[str, Any]],
        expected_version: Optional[int] = None,
    ) -> List[BranchModel]:
        """Open every requested workstream in one action.

        Each entry: {branch_type, department_id?, target_user_id?,
        instructions?, requires_hod_validation?, deadline?}.

        Routing to a target that already has an open branch extends that
        branch with a new round instead of duplicating it, so its earlier
        work and remarks are preserved.
        """
        return get_repository().route_document(document_id, branches, expected_version)

    def send_to_director(
        self,
        document_id: int,
        director_user_id: Optional[int] = None,
        instructions: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> List[BranchModel]:
        """Request a Director review.  Repeatable: each request is its own
        branch and each remark is kept separately."""
        return self.route(
            document_id,
            [{
                "branch_type": "DIRECTOR",
                "target_user_id": director_user_id,
                "instructions": instructions,
            }],
            expected_version,
        )

    def send_to_department(
        self,
        document_id: int,
        department_id: int,
        instructions: Optional[str] = None,
        requires_hod_validation: bool = False,
        deadline: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> List[BranchModel]:
        return self.route(
            document_id,
            [{
                "branch_type": "DEPARTMENT",
                "department_id": department_id,
                "instructions": instructions,
                "requires_hod_validation": requires_hod_validation,
                "deadline": deadline,
            }],
            expected_version,
        )

    def send_to_employee(
        self,
        document_id: int,
        user_id: int,
        instructions: Optional[str] = None,
        requires_hod_validation: bool = False,
        deadline: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> List[BranchModel]:
        """DS assigns an employee directly, with no HOD in the chain."""
        return self.route(
            document_id,
            [{
                "branch_type": "EMPLOYEE",
                "target_user_id": user_id,
                "instructions": instructions,
                "requires_hod_validation": requires_hod_validation,
                "deadline": deadline,
            }],
            expected_version,
        )

    def send_to_tso(
        self,
        document_id: int,
        instructions: Optional[str] = None,
        deadline: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> List[BranchModel]:
        """DS assigns the designated TSO directly.  TSO work stays separate
        from Employee work."""
        return self.route(
            document_id,
            [{"branch_type": "TSO", "instructions": instructions, "deadline": deadline}],
            expected_version,
        )

    def close_branch(self, branch_id: int, reason: Optional[str] = None) -> Optional[BranchModel]:
        """End one workstream.  The document and every other branch carry on."""
        return get_repository().close_branch(branch_id, reason)

    # =========================================================
    # ASSIGNMENT (DS or HOD)
    # =========================================================

    def assign(
        self,
        branch_id: int,
        assignee_user_ids: List[int],
        instructions: Optional[str] = None,
        deadline: Optional[str] = None,
        requires_validation: bool = False,
        team_name: Optional[str] = None,
    ) -> List[WorkItemModel]:
        """Assign one or more people to a workstream.

        Three people produce three work items, each with its own stage,
        deadline, progress and attachments.  `team_name` labels the group; it
        never merges their records.
        """
        return get_repository().assign_work(
            branch_id, assignee_user_ids, instructions, deadline, requires_validation, team_name
        )

    # =========================================================
    # REMARKS
    # =========================================================

    def add_remark(self, branch_id: int, remark_text: str) -> Optional[RemarkModel]:
        """Append a remark to a workstream.  Nothing is overwritten."""
        return get_repository().add_branch_remark(branch_id, remark_text)

    # =========================================================
    # DIRECTOR REVIEW
    # =========================================================

    def start_director_review(self, branch_id: int) -> Optional[BranchModel]:
        """Mark that the Director has opened the document."""
        return get_repository().start_director_review(branch_id)

    def submit_director_review(
        self, branch_id: int, remark_text: str, expected_version: Optional[int] = None
    ) -> Optional[DirectorReviewModel]:
        """Record the Director's remark and return the document to the DS.

        There is no approve/close decision here by design: the Director
        reviews and remarks, the DS decides what happens next.
        """
        return get_repository().submit_director_review(branch_id, remark_text, expected_version)

    # =========================================================
    # ROUTING INTELLIGENCE (advisory)
    # =========================================================

    def get_suggestion(self, document_id: int) -> Optional[Dict[str, Any]]:
        return get_repository().get_routing_suggestion(document_id)

    def analyze(self, document_id: int) -> Optional[Dict[str, Any]]:
        return get_repository().analyze_routing(document_id)


routing_service = RoutingService()
