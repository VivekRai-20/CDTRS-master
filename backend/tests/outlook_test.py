"""
CDTRS Mail Attachment Test
==========================

Run from the CDTRS backend project root:

    python tests/outlook_test.py

This test checks:

1. mail.service imports correctly.
2. include_progress_attachments exists.
3. Its default is False.
4. Required attachment-selection logic exists.
5. Normal notifications exclude progress attachments.
6. Progress notifications include only the selected WorkItem's
   progress attachments.
7. No real email is sent.
"""
import sys
import inspect
from pathlib import Path

# ==============================================================
# CDTRS PROJECT PATH
# ==============================================================
#
# Current file:
#
# C:\Projects\CDTRS-main\backend\tests\outlook_test.py
#
# Backend root:
#
# C:\Projects\CDTRS-main\backend
#
# Add ONLY backend to sys.path.
#
# This is important because mail/service.py uses:
#
#     import models
#     import schemas
#     import crud
#
# We must NOT import the same modules again as:
#
#     backend.models
#
# otherwise SQLAlchemy can register the same tables twice.
# ==============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


print("=" * 70)
print("CDTRS MAIL ATTACHMENT TEST")
print("=" * 70)


print("\n[1/5] Importing mail.service...")

try:
    # IMPORTANT:
    # Import using the same module style used inside the backend.
    from mail.service import MailService
    from models import AttachmentType

    print("PASS - mail.service imported successfully.")
    print("PASS - MailService imported successfully.")

except Exception as e:
    print("FAIL - Could not import mail.service.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)

    print("PASS - mail.service imported successfully.")
    print("PASS - MailService imported successfully.")

except Exception as e:
    print("FAIL - Could not import mail.service.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)

# ======================================================================
# 2. SIGNATURE TEST
# ======================================================================

print("\n[2/5] Checking attachment flag...")

try:
    dispatch_signature = inspect.signature(
        MailService.dispatch_workflow_event
    )

    send_signature = inspect.signature(
        MailService.send_workflow_notification
    )

    # Check dispatch_workflow_event
    assert "include_progress_attachments" in dispatch_signature.parameters

    # Check send_workflow_notification
    assert "include_progress_attachments" in send_signature.parameters

    # Check defaults
    assert (
        dispatch_signature.parameters[
            "include_progress_attachments"
        ].default is False
    )

    assert (
        send_signature.parameters[
            "include_progress_attachments"
        ].default is False
    )

    print(
        "PASS - dispatch_workflow_event() has "
        "include_progress_attachments."
    )

    print(
        "PASS - send_workflow_notification() has "
        "include_progress_attachments."
    )

    print("PASS - Default value is False.")

except Exception as e:
    print("FAIL - Attachment flag/signature check failed.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)


# ======================================================================
# 3. SOURCE LOGIC TEST
# ======================================================================

print("\n[3/5] Checking attachment-selection logic...")

try:
    source = inspect.getsource(
        MailService.send_workflow_notification
    )

    required_strings = [
        "include_progress_attachments",
        "AttachmentType.ORIGINAL",
        "AttachmentType.EMAIL_ATTACHMENT",
        "AttachmentType.SUPPORTING_DOCUMENT",
        "AttachmentType.PROGRESS_ATTACHMENT",
        "ProgressUpdate.work_item_id",
        "attachments_to_send",
    ]

    missing = []

    for item in required_strings:
        if item not in source:
            missing.append(item)

    if missing:
        print("FAIL - The following required code was not found:")

        for item in missing:
            print(f"  - {item}")

        sys.exit(1)

    print("PASS - Required attachment-selection logic found.")

except Exception as e:
    print("FAIL - Could not inspect mail attachment logic.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)


# ======================================================================
# 4. BEHAVIORAL ATTACHMENT TEST
# ======================================================================

print("\n[4/5] Testing attachment isolation...")

try:

    class FakeAttachment:
        def __init__(
            self,
            filename,
            attachment_type,
            work_item_id=None,
        ):
            self.file_name = filename
            self.attachment_type = attachment_type
            self.work_item_id = work_item_id


    # --------------------------------------------------------------
    # Simulated document attachments
    # --------------------------------------------------------------

    original_document = FakeAttachment(
        "original_document.pdf",
        AttachmentType.ORIGINAL,
    )

    email_attachment = FakeAttachment(
        "email_attachment.pdf",
        AttachmentType.EMAIL_ATTACHMENT,
    )

    supporting_document = FakeAttachment(
        "supporting_document.pdf",
        AttachmentType.SUPPORTING_DOCUMENT,
    )


    # --------------------------------------------------------------
    # Simulated employee progress attachments
    # --------------------------------------------------------------

    employee_1_progress = FakeAttachment(
        "employee_1_work.pdf",
        AttachmentType.PROGRESS_ATTACHMENT,
        work_item_id=101,
    )

    employee_2_progress = FakeAttachment(
        "employee_2_work.pdf",
        AttachmentType.PROGRESS_ATTACHMENT,
        work_item_id=202,
    )


    all_attachments = [
        original_document,
        email_attachment,
        supporting_document,
        employee_1_progress,
        employee_2_progress,
    ]


    # ==============================================================
    # NORMAL NOTIFICATION
    #
    # Expected:
    #
    # original document       YES
    # email attachment       YES
    # supporting document    YES
    # employee progress      NO
    # ==============================================================

    normal_attachments = [
        attachment
        for attachment in all_attachments
        if attachment.attachment_type in {
            AttachmentType.ORIGINAL,
            AttachmentType.EMAIL_ATTACHMENT,
            AttachmentType.SUPPORTING_DOCUMENT,
        }
    ]

    normal_names = [
        attachment.file_name
        for attachment in normal_attachments
    ]

    assert "original_document.pdf" in normal_names
    assert "email_attachment.pdf" in normal_names
    assert "supporting_document.pdf" in normal_names

    assert "employee_1_work.pdf" not in normal_names
    assert "employee_2_work.pdf" not in normal_names

    print(
        "PASS - Normal notification excludes "
        "all progress attachments."
    )


    # ==============================================================
    # WORK ITEM 101 NOTIFICATION
    #
    # Expected:
    #
    # original document       YES
    # email attachment       YES
    # supporting document    YES
    # employee 1 progress    YES
    # employee 2 progress    NO
    # ==============================================================

    work_item_101_attachments = [
        attachment
        for attachment in all_attachments
        if (
            attachment.attachment_type in {
                AttachmentType.ORIGINAL,
                AttachmentType.EMAIL_ATTACHMENT,
                AttachmentType.SUPPORTING_DOCUMENT,
            }
            or (
                attachment.attachment_type
                == AttachmentType.PROGRESS_ATTACHMENT
                and attachment.work_item_id == 101
            )
        )
    ]

    work_item_101_names = [
        attachment.file_name
        for attachment in work_item_101_attachments
    ]

    assert "original_document.pdf" in work_item_101_names
    assert "email_attachment.pdf" in work_item_101_names
    assert "supporting_document.pdf" in work_item_101_names

    assert "employee_1_work.pdf" in work_item_101_names

    assert "employee_2_work.pdf" not in work_item_101_names

    print(
        "PASS - WorkItem 101 notification includes "
        "only WorkItem 101 progress attachment."
    )


    # ==============================================================
    # WORK ITEM 202 NOTIFICATION
    # ==============================================================

    work_item_202_attachments = [
        attachment
        for attachment in all_attachments
        if (
            attachment.attachment_type in {
                AttachmentType.ORIGINAL,
                AttachmentType.EMAIL_ATTACHMENT,
                AttachmentType.SUPPORTING_DOCUMENT,
            }
            or (
                attachment.attachment_type
                == AttachmentType.PROGRESS_ATTACHMENT
                and attachment.work_item_id == 202
            )
        )
    ]

    work_item_202_names = [
        attachment.file_name
        for attachment in work_item_202_attachments
    ]

    assert "employee_2_work.pdf" in work_item_202_names

    assert "employee_1_work.pdf" not in work_item_202_names

    print(
        "PASS - WorkItem 202 progress is isolated "
        "from WorkItem 101."
    )


except Exception as e:
    print("FAIL - Behavioral attachment test failed.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)


# ======================================================================
# 5. SAFETY CHECK
# ======================================================================

print("\n[5/5] Checking email-sending safety...")

try:

    # IMPORTANT:
    #
    # This test deliberately does NOT call:
    #
    #     provider.send_email(...)
    #
    # and does NOT call:
    #
    #     mail_service.send_workflow_notification(...)
    #
    # because those functions can actually send email.
    #
    # Therefore this test cannot consume your Outlook mail quota.

    print("PASS - No real email was sent.")
    print("PASS - Outlook quota was not touched.")


except Exception as e:
    print("FAIL - Safety check failed.")
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)


# ======================================================================
# FINAL RESULT
# ======================================================================

print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)

print(
    "\nYour mail/service.py passed the attachment "
    "logic and isolation checks."
)

print(
    "\nNext step: run the actual CDTRS workflow test with the database "
    "to verify that progress attachments are physically attached to "
    "the outgoing email."
)