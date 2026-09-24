"""End-to-end exercise of the complete CDTRS workflow (spec section 28).

Runs against the live database.  It creates its own document and asserts the
behaviours the redesign exists to guarantee:

  * one document, many coexisting branches
  * branches sitting at DIFFERENT stages at the same time
  * one work item per person, each with its own stage and progress
  * explicit DS -> Director review gate before work routing
  * OCR-bypass-compatible Director gate (tested separately by backend logic)
  * repeatable Director review, every remark preserved
  * Director branch rounds and review numbers remain aligned
  * DS-only closure
"""

import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import crud
import models
import schemas
import workflow
from database import SessionLocal
from models import (
    BranchStage,
    BranchType,
    DocumentLifecycle,
    ReviewOutcome,
    WorkContextType,
    WorkStage,
)


def ctx_of(db, user, ctype, dept_name=None):
    for m in crud.get_user_context_memberships(db, user.id):
        if m.context_type != ctype:
            continue
        if dept_name is None or m.department_name == dept_name:
            return m
    raise AssertionError(f"{user.username} has no {ctype.value} context for {dept_name}")


def banner(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def step(text):
    print(f"\n--- {text}")


def show_branches(db, doc):
    db.refresh(doc)
    print(f"    Document lifecycle: {workflow.lifecycle_label(doc.lifecycle)}")
    for b in doc.branches:
        flag = "open" if b.is_active else "closed"
        print(f"    [{flag:6}] {b.label:<34} stage = {workflow.branch_stage_label(b.stage)}")
        for w in b.work_items:
            print(
                f"              - {w.assignee_name:<20} {workflow.work_stage_label(w.stage):<14}"
                f" {'(' + (w.latest_progress_text or '')[:38] + '...)' if w.latest_progress_text else ''}"
            )


def run():
    db = SessionLocal()
    failures = []

    def check(label, condition):
        if condition:
            print(f"    PASS  {label}")
        else:
            print(f"    FAIL  {label}")
            failures.append(label)

    try:
        ds = crud.get_user_by_username(db, "exec_user")
        director = crud.get_user_by_username(db, "director")
        hod_eng = crud.get_user_by_username(db, "hod_eng")
        emp_a = crud.get_user_by_username(db, "emp_rahul")    # Engineering
        emp_b = crud.get_user_by_username(db, "emp_sneha")    # Engineering
        emp_c = crud.get_user_by_username(db, "emp_anil")     # Product Strategy
        tso = crud.get_user_by_username(db, "tso_user")

        ds_ctx = ctx_of(db, ds, WorkContextType.DS)
        dir_ctx = ctx_of(db, director, WorkContextType.DIRECTOR)
        hod_ctx = ctx_of(db, hod_eng, WorkContextType.HOD, "Engineering & Innovation")
        a_ctx = ctx_of(db, emp_a, WorkContextType.EMPLOYEE, "Engineering & Innovation")
        b_ctx = ctx_of(db, emp_b, WorkContextType.EMPLOYEE, "Engineering & Innovation")
        c_ctx = ctx_of(db, emp_c, WorkContextType.EMPLOYEE, "Product Strategy")
        tso_ctx = ctx_of(db, tso, WorkContextType.TSO)

        eng_dept = hod_ctx.department_id

        # ---------------------------------------------------------------
        banner("STAGE 1 - INTAKE")
        doc = crud.create_document(
            db,
            schemas.DocumentCreate(
                title="Infrastructure Upgrade Proposal",
                subject="Proposed upgrade of core network infrastructure",
                description="Received from the Ministry for review and action.",
                received_date=date.today(),
                deadline=date.today() + timedelta(days=14),
                source="Ministry of Technology",
                sender_name="Under Secretary (Tech)",
                mode="OUTLOOK",
                priority=models.Priority.HIGH,
            ),
            created_by=ds.id,
            context_id=ds_ctx.id,
        )
        workflow.register_document(db, document_id=doc.doc_id, actor=ds, context_id=ds_ctx.id)
        print(f"    Created {doc.reference_no}")
        check("document starts REGISTERED", doc.lifecycle == DocumentLifecycle.REGISTERED)

        # ---------------------------------------------------------------
        banner("STAGE 1b - DIRECTOR GATE (routing before review must be blocked)")

        gate_doc = crud.create_document(
            db,
            schemas.DocumentCreate(
                title="Director Gate Test",
                subject="Test document",
                description="Must not be routed before Director review.",
                received_date=date.today(),
                deadline=date.today() + timedelta(days=7),
                source="Workflow Test",
                sender_name="Test Sender",
                mode="MANUAL_UPLOAD",
                priority=models.Priority.MEDIUM,
            ),
            created_by=ds.id,
            context_id=ds_ctx.id,
        )
        workflow.register_document(
            db,
            document_id=gate_doc.doc_id,
            actor=ds,
            context_id=ds_ctx.id,
        )

        try:
            workflow.open_branches(
                db,
                document_id=gate_doc.doc_id,
                requests=[
                    {
                        "branch_type": BranchType.DEPARTMENT,
                        "department_id": eng_dept,
                        "instructions": "Should be blocked.",
                    }
                ],
                actor=ds,
                context_id=ds_ctx.id,
            )
            check("routing before Director review is blocked", False)
        except workflow.WorkflowError:
            db.rollback()
            check("routing before Director review is blocked", True)

        # ---------------------------------------------------------------
        banner("STAGE 2 - EXPLICIT SEND TO DIRECTOR (round 1)")
        dir_branch = workflow.send_to_director(
            db,
            document_id=doc.doc_id,
            actor=ds,
            context_id=ds_ctx.id,
        )

        check("Director branch created", dir_branch.branch_type == BranchType.DIRECTOR)
        check("Director branch is round 1", dir_branch.round_no == 1)

        db.refresh(doc)
        check(
            "lifecycle is IN_REVIEW while with Director",
            doc.lifecycle == DocumentLifecycle.IN_REVIEW,
        )

        workflow.start_director_review(
            db,
            branch_id=dir_branch.id,
            actor=director,
            context_id=dir_ctx.id,
        )

        r1 = workflow.submit_director_review(
            db,
            branch_id=dir_branch.id,
            remark_text="Route to Engineering for technical assessment. Also involve TSO.",
            actor=director,
            context_id=dir_ctx.id,
        )

        db.refresh(doc)
        check("director review #1 recorded", r1.review_no == 1)
        check("director branch returned to DS", dir_branch.stage == BranchStage.RETURNED_TO_DS)
        check("lifecycle back to WITH_DS", doc.lifecycle == DocumentLifecycle.WITH_DS)

        # ---------------------------------------------------------------
        banner("STAGE 3 - MULTIPLE ROUTING (HOD + direct employee + TSO, at once)")
        branches = workflow.open_branches(
            db, document_id=doc.doc_id,
            requests=[
                {"branch_type": BranchType.DEPARTMENT, "department_id": eng_dept,
                 "instructions": "Technical assessment required.",
                 "requires_hod_validation": True},
                {"branch_type": BranchType.EMPLOYEE, "target_user_id": emp_c.id,
                 "instructions": "Prepare the cost impact note.",
                 "deadline": date.today() + timedelta(days=5)},
                {"branch_type": BranchType.TSO,
                 "instructions": "Verify technical feasibility."},
            ],
            actor=ds, context_id=ds_ctx.id,
        )
        check("three branches created in one routing action", len(branches) == 3)
        db.refresh(doc)
        check("lifecycle is IN_WORK", doc.lifecycle == DocumentLifecycle.IN_WORK)
        check("all three branches are open simultaneously", len(doc.active_branches) == 3)

        hod_branch = next(b for b in branches if b.branch_type == BranchType.DEPARTMENT)
        emp_branch = next(b for b in branches if b.branch_type == BranchType.EMPLOYEE)
        tso_branch = next(b for b in branches if b.branch_type == BranchType.TSO)
        show_branches(db, doc)

        # ---------------------------------------------------------------
        banner("STAGE 3b - HOD ASSIGNS TWO EMPLOYEES AS A TEAM")
        workflow.add_branch_remark(
            db, branch_id=hod_branch.id,
            remark_text="Splitting this between Rahul (analysis) and Sneha (data).",
            actor=hod_eng, context_id=hod_ctx.id,
        )
        items = workflow.assign_branch_work(
            db, branch_id=hod_branch.id,
            assignee_user_ids=[emp_a.id, emp_b.id],
            actor=hod_eng, context_id=hod_ctx.id,
            instructions="Technical assessment of the proposal.",
            requires_validation=True,
            team_name="Infrastructure Review Team",
        )
        check("a team of 2 produced 2 SEPARATE work items", len(items) == 2)
        check("both items share one team", items[0].team_id == items[1].team_id and items[0].team_id is not None)
        check("each work item has its own id", items[0].id != items[1].id)

        item_a = next(i for i in items if i.assigned_to_user_id == emp_a.id)
        item_b = next(i for i in items if i.assigned_to_user_id == emp_b.id)
        item_c = emp_branch.work_items[0]
        item_t = tso_branch.work_items[0]

        # ---------------------------------------------------------------
        banner("STAGE 4 - INDIVIDUAL WORK (each person moves at their own pace)")

        step("Employee A writes progress (free text)")
        workflow.submit_progress(
            db, work_item_id=item_a.id, actor=emp_a, context_id=a_ctx.id,
            description=(
                "Reviewed the submitted documents and identified three issues in the "
                "existing configuration. I have prepared the required analysis and am "
                "currently working on the proposed changes."
            ),
        )
        check("Employee A is UNDER_WORK", item_a.stage == WorkStage.UNDER_WORK)

        step("Employee B marks themselves as waiting")
        workflow.update_work_stage(
            db, work_item_id=item_b.id, new_stage=WorkStage.WAITING,
            actor=emp_b, context_id=b_ctx.id, note="Blocked on the vendor",
        )
        workflow.submit_progress(
            db, work_item_id=item_b.id, actor=emp_b, context_id=b_ctx.id,
            description="Data collection has been completed. Waiting for confirmation from the concerned department.",
            new_stage=WorkStage.WAITING,
        )
        check("Employee B is WAITING", item_b.stage == WorkStage.WAITING)
        check("A and B are at DIFFERENT stages on the SAME branch", item_a.stage != item_b.stage)

        step("Direct Employee C completes their assignment")
        workflow.submit_progress(
            db, work_item_id=item_c.id, actor=emp_c, context_id=c_ctx.id,
            description="Completed the requested cost impact note.",
        )
        workflow.submit_work(db, work_item_id=item_c.id, actor=emp_c, context_id=c_ctx.id)
        db.refresh(emp_branch)
        check("Employee C work COMPLETED", item_c.stage == WorkStage.COMPLETED)
        check("direct-employee branch is COMPLETED", emp_branch.stage == BranchStage.COMPLETED)
        check("that branch closed without closing the document", not emp_branch.is_active)

        step("TSO completes their own assignment")
        workflow.submit_progress(
            db, work_item_id=item_t.id, actor=tso, context_id=tso_ctx.id,
            description="Technical verification completed. Findings attached.",
        )
        workflow.submit_work(db, work_item_id=item_t.id, actor=tso, context_id=tso_ctx.id)
        db.refresh(tso_branch)
        check("TSO branch COMPLETED", tso_branch.stage == BranchStage.COMPLETED)

        db.refresh(doc)
        check("document still open while branches finish", doc.lifecycle != DocumentLifecycle.CLOSED)

        show_branches(db, doc)

        stages = {b.label: b.stage for b in doc.branches if b.branch_type != BranchType.DIRECTOR}
        check("branches hold DIFFERENT stages at the same time", len(set(stages.values())) > 1)

        # ---------------------------------------------------------------
        banner("STAGE 4b - HOD VALIDATES ONE PERSON'S WORK")
        workflow.submit_work(db, work_item_id=item_a.id, actor=emp_a, context_id=a_ctx.id,
                             note="Analysis complete, submitting for validation.")
        check("A goes to UNDER_REVIEW (validation required)", item_a.stage == WorkStage.UNDER_REVIEW)
        db.refresh(hod_branch)
        check("HOD branch shows HOD_VALIDATION", hod_branch.stage == BranchStage.HOD_VALIDATION)

        workflow.review_work_item(
            db, work_item_id=item_a.id, outcome=ReviewOutcome.ACCEPTED,
            actor=hod_eng, context_id=hod_ctx.id, note="Analysis is sound.",
        )
        check("A accepted -> COMPLETED", item_a.stage == WorkStage.COMPLETED)
        check("B untouched by A's validation", item_b.stage == WorkStage.WAITING)
        db.refresh(doc)
        check("validating one person did NOT close the document", doc.lifecycle != DocumentLifecycle.CLOSED)
        db.refresh(hod_branch)
        check("HOD branch still open because B is still working", hod_branch.is_active)

        # ---------------------------------------------------------------
        banner("STAGE 6 - DIRECTOR REVIEW AGAIN (round 2)")
        (dir_branch_2,) = workflow.open_branches(
            db,
            document_id=doc.doc_id,
            requests=[{
                "branch_type": BranchType.DIRECTOR,
                "target_user_id": director.id,
                "instructions": "Interim review of progress so far.",
            }],
            actor=ds,
            context_id=ds_ctx.id,
        )
        check("a second, separate Director branch opened", dir_branch_2.id != dir_branch.id)
        check("Director branch is round 2", dir_branch_2.round_no == 2)

        r2 = workflow.submit_director_review(
            db, branch_id=dir_branch_2.id,
            remark_text="Good progress. Sneha should complete the pending data confirmation.",
            actor=director, context_id=dir_ctx.id,
        )
        db.refresh(doc)
        check("director review #2 recorded", r2.review_no == 2)
        check("Director review #2 matches branch round #2", dir_branch_2.round_no == r2.review_no)
        check("BOTH director remarks preserved", len(doc.director_reviews) == 2)
        check("first remark not overwritten", doc.director_reviews[0].remark_text == r1.remark_text)

        # ---------------------------------------------------------------
        banner("STAGE 7 - DS SENDS FURTHER WORK")
        before_rounds = hod_branch.round_no
        workflow.open_branches(
            db, document_id=doc.doc_id,
            requests=[{"branch_type": BranchType.DEPARTMENT, "department_id": eng_dept,
                       "instructions": "Please close out the pending data confirmation."}],
            actor=ds, context_id=ds_ctx.id,
        )
        db.refresh(hod_branch)
        check("further work extended the SAME branch (no duplicate)", hod_branch.round_no == before_rounds + 1)
        check("no second open Engineering branch was created",
              sum(1 for b in doc.branches
                  if b.branch_type == BranchType.DEPARTMENT and b.department_id == eng_dept) == 1)
        check("A's completed work survived the further-work round", item_a.stage == WorkStage.COMPLETED)

        step("Employee B finishes")
        workflow.submit_progress(
            db, work_item_id=item_b.id, actor=emp_b, context_id=b_ctx.id,
            description="Confirmation received. Completed the assigned review and submitted the final findings.",
        )
        workflow.submit_work(db, work_item_id=item_b.id, actor=emp_b, context_id=b_ctx.id)
        workflow.review_work_item(
            db, work_item_id=item_b.id, outcome=ReviewOutcome.ACCEPTED,
            actor=hod_eng, context_id=hod_ctx.id, note="Accepted.",
        )
        db.refresh(hod_branch)
        check("HOD branch now COMPLETED (everyone finished)", hod_branch.stage == BranchStage.COMPLETED)

        show_branches(db, doc)

        # ---------------------------------------------------------------
        banner("STAGE 8/9 - FINAL DIRECTOR REVIEW, THEN DS CLOSES")
        (dir_branch_3,) = workflow.open_branches(
            db,
            document_id=doc.doc_id,
            requests=[{
                "branch_type": BranchType.DIRECTOR,
                "target_user_id": director.id,
            }],
            actor=ds,
            context_id=ds_ctx.id,
        )
        check("Director branch is round 3", dir_branch_3.round_no == 3)

        r3 = workflow.submit_director_review(
            db, branch_id=dir_branch_3.id, remark_text="Satisfied. May be closed.",
            actor=director, context_id=dir_ctx.id,
        )
        db.refresh(doc)
        check("three separate Director reviews preserved", len(doc.director_reviews) == 3)
        check("Director review did NOT close the document", doc.lifecycle != DocumentLifecycle.CLOSED)

        step("a non-DS context may not close the document")
        try:
            workflow.close_document(db, document_id=doc.doc_id, actor=director, context_id=dir_ctx.id)
            check("Director blocked from closing", False)
        except workflow.PermissionDenied:
            db.rollback()
            check("Director blocked from closing", True)

        try:
            workflow.close_document(db, document_id=doc.doc_id, actor=emp_a, context_id=a_ctx.id)
            check("Employee blocked from closing", False)
        except workflow.PermissionDenied:
            db.rollback()
            check("Employee blocked from closing", True)

        step("DS closes")
        doc = workflow.close_document(
            db, document_id=doc.doc_id, actor=ds, context_id=ds_ctx.id,
            remark="All required work completed and reviewed by the Director.",
        )
        check("document CLOSED by DS", doc.lifecycle == DocumentLifecycle.CLOSED)
        check("closure attributed to the DS", doc.closed_by_user_id == ds.id)

        # ---------------------------------------------------------------
        banner("TRACEABILITY")
        history = workflow.document_history(db, doc.doc_id)
        print(f"    {len(history)} history entries:")
        for e in history:
            scope = f" [{e.branch_label}]" if e.branch_label else ""
            print(f"      {e.created_at:%H:%M:%S}  {e.event_type:<28}{scope} - {e.summary}")

        check("history covers the whole lifecycle", len(history) >= 20)
        check("every progress update preserved", len(doc.progress_updates) == 6)
        check("every person's work item preserved", len(doc.work_items) == 4)
        check("all branches preserved (3 director + 3 work)", len(doc.branches) == 6)

        director_rounds = sorted(
            b.round_no
            for b in doc.branches
            if b.branch_type == BranchType.DIRECTOR
        )
        director_review_numbers = sorted(
            r.review_no
            for r in doc.director_reviews
        )
        print(f"    Director branch rounds: {director_rounds}")
        print(f"    Director review numbers: {director_review_numbers}")
        check("Director branch rounds are [1, 2, 3]", director_rounds == [1, 2, 3])
        check("Director review numbers are [1, 2, 3]", director_review_numbers == [1, 2, 3])

        per_person = {}
        for w in doc.work_items:
            per_person[w.assignee_name] = len(w.progress_updates)
        print(f"    progress updates per person: {per_person}")
        check("each person's updates stayed on their own record", all(v >= 1 for v in per_person.values()))

        banner(f"RESULT: {len(failures)} failure(s)" if failures else "RESULT: ALL CHECKS PASSED")
        for f in failures:
            print(f"  FAILED: {f}")
        return 1 if failures else 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run())
