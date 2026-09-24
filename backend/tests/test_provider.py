import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mail.outlook_provider import OutlookGraphProvider
from mail.base import OutgoingEmailDTO


print("=" * 70)
print("CDTRS OUTLOOK SEND TEST")
print("=" * 70)


print("\n[1] Creating OutlookGraphProvider...")

provider = OutlookGraphProvider()

print("Provider:", provider)
print("Class:", type(provider).__name__)
print("Configured:", provider.is_configured())


print("\n[2] Getting access token...")

token = provider._get_access_token()

if not token:
    print("FAILED: No access token")
    raise SystemExit(1)

print("Access token obtained")
print("Token length:", len(token))


print("\n[3] Preparing test email...")

email = OutgoingEmailDTO(
    recipient_email="zodgepratiksha575@gmail.com",
    recipient_name="Pratiksha",
    subject="CDTRS Graph Send Test",
    body_text=(
        "This is a test email from the CDTRS OutlookGraphProvider. "
        "It is being used to verify Microsoft Graph sendMail."
    ),
    body_html=None,
    attachments=None,
)

print("Recipient:", email.recipient_email)
print("Subject:", email.subject)
print("Attachments:", 0)


print("\n[4] Calling provider.send_email()")
print("-" * 70)

try:

    result = provider.send_email(email)

    print()
    print("send_email() returned:", result)

    if result:
        print()
        print("=" * 70)
        print("SEND SUCCESS")
        print("=" * 70)
        print("Microsoft Graph accepted the email.")
        print("Expected Graph success response: HTTP 202.")
    else:
        print()
        print("=" * 70)
        print("SEND FAILED")
        print("=" * 70)
        print("Check the Graph error printed by OutlookGraphProvider.")

except Exception as exc:

    print()
    print("=" * 70)
    print("SEND TEST EXCEPTION")
    print("=" * 70)

    print(type(exc).__name__, ":", exc)

    import traceback
    traceback.print_exc()


print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)