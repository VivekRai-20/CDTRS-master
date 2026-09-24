"""Headless UI smoke test.

Signs in as each role against a running backend, builds the real pages and
widgets that role uses, and reports anything that fails to construct or
populate.  Renders offscreen, so it needs no display.

    python -m uvicorn main:app --port 8123      (from backend/)
    python tests/test_ui_smoke.py               (from frontend/)
"""

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FRONTEND_DIR = Path(__file__).resolve().parent.parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

os.environ.setdefault("CDTRS_API_URL", "http://127.0.0.1:8123/api/v1")

from PySide6.QtWidgets import QApplication  # noqa: E402

failures = []
passes = 0


def check(label, fn):
    """Build something and report whether it worked."""
    global passes
    try:
        result = fn()
        passes += 1
        detail = f" -> {result}" if result else ""
        print(f"    PASS  {label}{detail}")
        return True
    except Exception as exc:
        failures.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"    FAIL  {label}: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        return False


def banner(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    from core.context.context_manager import context_manager
    from services.auth_service import auth_service

    accounts = [
        ("exec_user", "cdtrs@ds", "DS"),
        ("director", "cdtrs@director", "DIRECTOR"),
        ("hod_eng", "cdtrs@hod", "HOD"),
        ("emp_rahul", "cdtrs@emp", "EMPLOYEE"),
        ("tso_user", "cdtrs@tso", "TSO"),
        ("corp", "cdtrs@admin", "ADMIN"),
    ]

    for username, password, expected_context in accounts:
        banner(f"{expected_context} - signed in as {username}")

        user = auth_service.login(username, password)
        if not user:
            failures.append(f"{username}: login failed")
            print(f"    FAIL  login as {username}")
            continue

        contexts = auth_service.get_contexts()
        target = next(
            (c for c in contexts
             if str(getattr(c, "context_type", "")).upper() == expected_context),
            None,
        )
        if target is None:
            failures.append(f"{username}: no {expected_context} context")
            print(f"    FAIL  no {expected_context} context available")
            continue

        auth_service.set_active_context(target.id)
        context_manager.refresh(expected_context)
        check(
            f"active context is {expected_context}",
            lambda: context_manager.active_context_type(expected_context),
        )

        # ---- pages this context actually uses ----
        from core.navigation.navigation_registry import NavigationRegistry
        menu = NavigationRegistry.get_menu(expected_context)
        print(f"    navigation: {menu}")

        from pages.dashboard import DashboardPage
        check("Dashboard builds and loads", lambda: (
            DashboardPage(expected_context).load() or "ok"
        ))

        if expected_context != "ADMIN":
            from pages.documents import DocumentsPage
            check("Documents page builds and loads", lambda: (
                _count_rows(DocumentsPage(expected_context))
            ))

            from pages.history import HistoryPage
            check("History page builds and loads", lambda: (
                _count_history(HistoryPage())
            ))

        if expected_context == "DS":
            from pages.document_intake import DocumentIntakePage
            check("Document Intake builds", lambda: DocumentIntakePage() and "ok")
            from pages.inbox import InboxPage
            check("Inbox builds", lambda: InboxPage() and "ok")
            from pages.priority import PriorityPage
            check("Deadlines page builds and loads", lambda: (
                _count_priority(PriorityPage())
            ))

        if expected_context == "DIRECTOR":
            from pages.director_inbox import DirectorInboxPage
            check("Director inbox builds and loads", lambda: (
                _count_director(DirectorInboxPage())
            ))
            from pages.director_reviewed import DirectorReviewedPage
            check("My Reviews builds and loads", lambda: (
                _count_reviews(DirectorReviewedPage())
            ))

        if expected_context == "HOD":
            from pages.hod_inbox import HODInboxPage
            check("HOD workspace builds and loads", lambda: _count_hod(HODInboxPage()))

        if expected_context in ("EMPLOYEE", "TSO"):
            from pages.my_tasks import MyTasksPage
            check(f"{expected_context} tasks build and load",
                  lambda: _count_tasks(MyTasksPage(expected_context)))

        if expected_context == "ADMIN":
            from pages.user_configuration import UserConfigurationPage
            check("User Configuration builds", lambda: UserConfigurationPage() and "ok")
            from pages.department_configuration import DepartmentConfigurationPage
            check("Department Configuration builds", lambda: DepartmentConfigurationPage() and "ok")
            from pages.system_configuration import SystemConfigurationPage
            check("System Configuration builds", lambda: SystemConfigurationPage() and "ok")
            from pages.audit_history import AuditHistoryPage
            check("Audit History builds", lambda: AuditHistoryPage() and "ok")

        # ---- the document viewer, which is where the workflow is shown ----
        if expected_context != "ADMIN":
            from services.document_service import document_service
            docs = document_service.get_documents()
            if docs:
                doc = document_service.get_document(docs[0].id) or docs[0]
                check(
                    f"Document viewer renders {doc.reference} "
                    f"({len(doc.branches)} workstream(s), {len(doc.all_work_items)} work item(s))",
                    lambda: _build_viewer(doc, expected_context),
                )
            else:
                print("    note: no documents visible in this context")

        auth_service.logout()

    banner(f"RESULT: {passes} passed, {len(failures)} failed")
    for f in failures:
        print(f"  FAILED: {f}")
    return 1 if failures else 0


def _shown_count(page, noun):
    """Rows in a table page, or the result counter on a card-based page."""
    table = getattr(page, "table", None)
    if table is not None:
        return f"{table.rowCount()} {noun}(s)"
    counter = getattr(page, "result_count", None)
    if counter is not None:
        return counter.text()
    raise AssertionError(f"{type(page).__name__} shows neither a table nor a result count")


def _count_rows(page):
    page.load_documents()
    return _shown_count(page, "row")


def _count_history(page):
    page.load()
    return _shown_count(page, "event")


def _count_priority(page):
    page.load_documents()
    return f"{page.table.rowCount()} row(s)"


def _count_director(page):
    page.load()
    return f"{page.table.rowCount()} awaiting review"


def _count_reviews(page):
    page.load()
    return f"{page.table.rowCount()} review(s)"


def _count_hod(page):
    page.load()
    return f"{page.branch_table.rowCount()} workstream(s), {page.staff_table.rowCount()} staff record(s)"


def _count_tasks(page):
    page.load_tasks()
    return f"{page.table.rowCount()} assignment(s)"


def _build_viewer(doc, role):
    from components.document_viewer import DocumentViewer
    viewer = DocumentViewer(doc, role=role)
    viewer.refresh(reload_from_server=False)
    branch_cards = viewer.branches_section["layout"].count()
    viewer.cleanup()
    return f"{branch_cards} section widget(s)"


if __name__ == "__main__":
    sys.exit(main())
