# ==============================================================================
# CDTRS - FINAL INTRANET MAIL TEST
# File: tests/test_intranet_mail.py
#
# Tests the CURRENT CDTRS intranet provider:
#   1. Reads .env
#   2. Verifies DS IMAP configuration
#   3. Connects to DS mailbox
#   4. Fetches unread incoming emails
#   5. Displays subjects/senders/attachments
#   6. Verifies CDTRS SMTP configuration
#   7. Optionally sends a real test email from the CDTRS mailbox
#
# IMPORTANT:
#   - This test does NOT modify/read the CDTRS database.
#   - It tests the mail server connection directly.
#   - Sending is OFF unless you run with --send.
#
# Run from:
#   C:\CDTRS-main\backend
#
# Commands:
#   python tests\test_intranet_mail.py
#   python tests\test_intranet_mail.py --send --recipient your@email.com
#
# If your .env is in backend\.env, it will be loaded automatically.
# ==============================================================================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# ------------------------------------------------------------------------------
# Make "mail" importable when this file is run from backend\tests
# ------------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ------------------------------------------------------------------------------
# Load .env
# ------------------------------------------------------------------------------

try:
    from dotenv import load_dotenv

    env_path = BACKEND_DIR / ".env"

    if env_path.exists():
        load_dotenv(env_path, override=False)
        print(f"[OK] Loaded environment: {env_path}")
    else:
        load_dotenv()
        print("[WARN] backend\\.env was not found. Using existing environment variables.")

except ImportError:
    print("[WARN] python-dotenv is not installed.")
    print("      Continuing with existing environment variables.")
    print()


# ------------------------------------------------------------------------------
# Import current provider
# ------------------------------------------------------------------------------

try:
    from mail.intranet_provider import IntranetMailProvider
    from mail.base import OutgoingEmailDTO

except Exception as exc:
    print("[FAIL] Could not import the CDTRS intranet mail provider.")
    print(f"       {type(exc).__name__}: {exc}")
    sys.exit(1)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def mask(value: str | None) -> str:
    """Hide passwords and sensitive values in console output."""
    if not value:
        return "(empty)"

    if len(value) <= 4:
        return "*" * len(value)

    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_result(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"       {detail}")


# ------------------------------------------------------------------------------
# Argument parsing
# ------------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test CDTRS local/intranet IMAP + SMTP mail integration."
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send a real SMTP test email.",
    )

    parser.add_argument(
        "--recipient",
        default=os.getenv("TEST_MAIL_RECIPIENT", "").strip(),
        help=(
            "Recipient for the SMTP test email. "
            "Can also be set with TEST_MAIL_RECIPIENT in .env."
        ),
    )

    parser.add_argument(
        "--incoming-only",
        action="store_true",
        help="Only test IMAP incoming mail and skip SMTP.",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run IMAP test and SMTP test if TEST_MAIL_RECIPIENT is configured.",
    )

    return parser.parse_args()


# ------------------------------------------------------------------------------
# Configuration display
# ------------------------------------------------------------------------------

def show_configuration(provider: IntranetMailProvider) -> None:
    print_header("CDTRS INTRANET MAIL CONFIGURATION")

    print(f"IMAP host          : {provider.imap_host or '(empty)'}")
    print(f"IMAP port          : {provider.imap_port}")
    print(f"IMAP security      : {provider.imap_security}")
    print(f"IMAP authentication: {provider.imap_auth}")
    print(f"DS mailbox user    : {provider.ds_mail_user or '(empty)'}")
    print(f"DS mailbox pass    : {mask(provider.ds_mail_pass)}")

    print()
    print(f"SMTP host          : {provider.smtp_host or '(empty)'}")
    print(f"SMTP port          : {provider.smtp_port}")
    print(f"SMTP security      : {provider.smtp_security}")
    print(f"SMTP authentication: {provider.smtp_auth}")
    print(f"CDTRS mailbox user  : {provider.cdtrs_mail_user or '(empty)'}")
    print(f"CDTRS mailbox pass  : {mask(provider.cdtrs_mail_pass)}")
    print(f"Sender address     : {provider.sender_address or '(empty)'}")
    print(f"Sender name        : {provider.sender_name or '(empty)'}")
    print(f"Allow self-signed  : {provider.allow_selfsigned}")

    print()
    print("Expected architecture:")
    print("  Incoming: DS mailbox  <- IMAP <- Office mail server")
    print("  Outgoing: CDTRS mailbox -> SMTP -> Recipient")


# ------------------------------------------------------------------------------
# Basic configuration checks
# ------------------------------------------------------------------------------

def check_configuration(provider: IntranetMailProvider) -> bool:
    print_header("1. CONFIGURATION CHECK")

    passed = True

    required_values = [
        ("INTRANET_IMAP_HOST", provider.imap_host),
        ("DS_MAIL_USER", provider.ds_mail_user),
        ("DS_MAIL_PASS", provider.ds_mail_pass),
        ("INTRANET_SMTP_HOST", provider.smtp_host),
        ("CDTRS_MAIL_USER", provider.cdtrs_mail_user),
        ("CDTRS_MAIL_PASS", provider.cdtrs_mail_pass),
        ("CDTRS_SENDER_EMAIL", provider.sender_address),
    ]

    for name, value in required_values:
        ok = bool(value)
        print_result(name, ok, "configured" if ok else "MISSING")
        if not ok:
            passed = False

    for name, value in [
        ("INTRANET_IMAP_SECURITY", provider.imap_security),
        ("INTRANET_SMTP_SECURITY", provider.smtp_security),
        ("INTRANET_IMAP_AUTH", provider.imap_auth),
        ("INTRANET_SMTP_AUTH", provider.smtp_auth),
    ]:
        ok = value in {"ssl", "starttls", "plain"} if "SECURITY" in name else value == "password"
        print_result(name, ok, f"value={value}")

        if not ok:
            passed = False

    provider_ready = provider.is_configured()
    print_result(
        "Provider is_configured()",
        provider_ready,
        "Both IMAP and SMTP basic configuration detected."
        if provider_ready
        else "Provider reports incomplete configuration.",
    )

    return passed and provider_ready


# ------------------------------------------------------------------------------
# IMAP test
# ------------------------------------------------------------------------------

def test_incoming(provider: IntranetMailProvider) -> bool:
    print_header("2. INCOMING MAIL / IMAP TEST")

    print("Connecting to DS mailbox...")
    print(f"Server : {provider.imap_host}:{provider.imap_port}")
    print(f"Mode   : {provider.imap_security}")
    print(f"User   : {provider.ds_mail_user}")

    emails = provider.fetch_incoming_emails(
        max_count=10,
        unread_only=True,
    )

    # The provider returns [] both when there are no unread messages and when
    # the connection failed internally, so perform a direct connection check
    # as well for an unambiguous result.

    client = provider._connect_imap()

    if client is None:
        print_result(
            "IMAP connection",
            False,
            "Could not connect/login to the DS mailbox. Check host, port, security mode and credentials.",
        )
        return False

    try:
        status, mailbox_info = client.select("INBOX")

        if status != "OK":
            print_result(
                "IMAP INBOX selection",
                False,
                f"Server returned status={status}.",
            )
            return False

        print_result(
            "IMAP connection + login",
            True,
            "Successfully connected and authenticated to the DS mailbox.",
        )

        print_result(
            "IMAP INBOX selection",
            True,
            "DS mailbox INBOX opened successfully.",
        )

        status, data = client.search(None, "UNSEEN")

        if status == "OK" and data and data[0]:
            unread_count = len(data[0].split())
        else:
            unread_count = 0

        print_result(
            "Unread message search",
            status == "OK",
            f"Unread messages currently available: {unread_count}",
        )

    finally:
        try:
            client.close()
        except Exception:
            pass

        try:
            client.logout()
        except Exception:
            pass

    print()
    print(f"Fetched DTOs: {len(emails)}")

    if not emails:
        print("NOTE: No unread emails were returned.")
        print("      This is NOT an error if the DS mailbox has no unread mail.")
        print()
        print("For a complete test tomorrow:")
        print("  1. Send an email to the DS mailbox from another account.")
        print("  2. Keep it unread.")
        print("  3. Run this test again.")

        return True

    print()
    print("Unread incoming messages:")

    for index, item in enumerate(emails, start=1):
        print()
        print(f"--- Message {index} ---")
        print(f"Message ID : {item.message_id}")
        print(f"From       : {item.sender_name or ''} <{item.sender_email or ''}>")
        print(f"Subject    : {item.subject}")
        print(f"Received   : {item.received_at}")
        print(f"Attachments: {len(item.attachments)}")

        for attachment in item.attachments:
            print(
                f"  - {attachment.filename} | "
                f"{attachment.size_bytes} bytes | "
                f"{attachment.content_type}"
            )

        if item.body_text:
            preview = " ".join(item.body_text.split())
            if len(preview) > 160:
                preview = preview[:160] + "..."
            print(f"Body       : {preview}")

    print()
    print_result(
        "Incoming mail parsing",
        True,
        f"Successfully parsed {len(emails)} unread message(s).",
    )

    return True


# ------------------------------------------------------------------------------
# SMTP test
# ------------------------------------------------------------------------------

def test_outgoing(
    provider: IntranetMailProvider,
    recipient: str,
) -> bool:
    print_header("3. OUTGOING MAIL / SMTP TEST")

    if not recipient:
        print_result(
            "SMTP test recipient",
            False,
            "No recipient supplied. Use --recipient someone@example.com or set TEST_MAIL_RECIPIENT in .env.",
        )
        return False

    print("A REAL EMAIL WILL BE SENT.")
    print()
    print(f"SMTP server : {provider.smtp_host}:{provider.smtp_port}")
    print(f"Security    : {provider.smtp_security}")
    print(f"Sender      : {provider.sender_address}")
    print(f"Recipient   : {recipient}")
    print()

    confirm = input(
        "Type SEND to actually send the test email: "
    ).strip()

    if confirm != "SEND":
        print()
        print("[SKIPPED] SMTP send cancelled. No email was sent.")
        return True

    test_email = OutgoingEmailDTO(
        recipient_email=recipient,
        recipient_name="CDTRS Test Recipient",
        subject="[CDTRS] Intranet Mail Integration Test",
        body_text=(
            "This is a test email from the CDTRS application mailbox.\n\n"
            "If you received this message, the CDTRS SMTP integration "
            "is able to authenticate and send mail through the office "
            "mail server.\n\n"
            "This message was generated by tests/test_intranet_mail.py."
        ),
        body_html="""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2>CDTRS Intranet Mail Test</h2>
    <p>
        This is a test email from the <b>CDTRS application mailbox</b>.
    </p>
    <p>
        If you received this message, the CDTRS SMTP integration
        successfully authenticated and sent mail through the office
        mail server.
    </p>
    <hr>
    <p style="font-size: 12px; color: #666;">
        Generated by tests/test_intranet_mail.py
    </p>
</body>
</html>
""",
        attachments=None,
    )

    try:
        result = provider.send_email(test_email)
    except Exception as exc:
        print_result(
            "SMTP send",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        return False

    print_result(
        "SMTP send",
        result,
        (
            "Test email was accepted by the provider."
            if result
            else "Provider failed to send the test email. Check the server logs/configuration."
        ),
    )

    return result


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    print_header("CDTRS FINAL INTRANET MAIL TEST")

    print("This test uses the current intranet_provider.py implementation.")
    print("It uses two independent office mail accounts:")
    print("  DS_MAIL_USER / DS_MAIL_PASS   -> incoming IMAP")
    print("  CDTRS_MAIL_USER / PASS        -> outgoing SMTP")

    try:
        provider = IntranetMailProvider()
    except Exception as exc:
        print_result(
            "Provider initialization",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        return 1

    show_configuration(provider)

    config_ok = check_configuration(provider)

    if not config_ok:
        print_header("RESULT")
        print("INTRANET TEST STOPPED.")
        print()
        print("Fix the missing/invalid .env values above, then run the test again.")
        return 1

    incoming_ok = True
    smtp_ok = True

    run_smtp = (args.send or args.all) and not args.incoming_only

    incoming_ok = test_incoming(provider)

    if run_smtp:
        smtp_ok = test_outgoing(
            provider,
            args.recipient,
        )

    print_header("FINAL RESULT")

    print_result(
        "Configuration",
        config_ok,
    )

    print_result(
        "Incoming IMAP",
        incoming_ok,
    )

    if run_smtp:
        print_result(
            "Outgoing SMTP",
            smtp_ok,
        )
    elif args.incoming_only:
        print("[SKIPPED] Outgoing SMTP send (--incoming-only was supplied).")
    else:
        print("[SKIPPED] Outgoing SMTP send.")
        print("          Run with --send --recipient <email> to test it.")

    overall_ok = config_ok and incoming_ok and smtp_ok

    print()
    if overall_ok:
        print("ALL REQUESTED INTRANET MAIL TESTS PASSED.")
        return 0

    print("ONE OR MORE INTRANET MAIL TESTS FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
