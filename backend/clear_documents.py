"""Delete every document and all of its workflow data, keeping accounts,
departments, work contexts and settings.

Use this to start workflow testing from a clean register without re-seeding.

    python clear_documents.py --confirm
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import models
from database import SessionLocal


def clear_all_documents() -> None:
    print("=" * 62)
    print("CDTRS - clearing documents and workflow data")
    print("=" * 62)

    db = SessionLocal()
    try:
        # Children first, so foreign keys stay satisfied.
        order = [
            models.Notification,
            models.Reminder,
            models.WorkflowEvent,
            models.Attachment,
            models.WorkStageChange,
            models.WorkItemReview,
            models.ProgressUpdate,
            models.WorkItem,
            models.WorkTeam,
            models.DocumentRemark,
            models.DirectorReview,
            models.DocumentBranch,
            models.RoutingSuggestion,
            models.DocumentExtractedField,
            models.DocumentOCR,
            models.IncomingMessage,
        ]
        for model in order:
            removed = db.query(model).delete(synchronize_session=False)
            print(f"  {model.__tablename__:<26} {removed} row(s)")

        documents = db.query(models.Document).delete(synchronize_session=False)
        db.commit()

        print(f"\n[OK] {documents} document(s) removed.")
        print("[OK] Accounts, departments, work contexts and settings preserved.")
        print("=" * 62)
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if "--confirm" not in sys.argv:
        print(__doc__)
        print("Refusing to run: pass --confirm to proceed.")
        sys.exit(1)
    clear_all_documents()
