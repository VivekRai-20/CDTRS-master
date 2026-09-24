import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mail.service import MailService


print("=" * 70)
print("CDTRS MAIL SERVICE PROVIDER SELECTION TEST")
print("=" * 70)


print("\n[1] Creating MailService...")
service = MailService()
print("PASS - MailService created")


print("\n[2] Available providers")

providers = getattr(service, "_providers", {})

for name, provider in providers.items():
    print(
        f"{name:12} -> "
        f"{type(provider).__module__}."
        f"{type(provider).__name__}"
    )


print("\n[3] Inspecting get_provider()")

get_provider = getattr(service, "get_provider", None)

if get_provider is None:
    print("ERROR: MailService has no get_provider() method")
    raise SystemExit(1)

print("get_provider:", get_provider)


print("\n[4] Testing provider selection")

provider_names = [
    "outlook",
    "intranet",
    "local",
    "smtp_imap",
    "gov_mail",
]

selected = {}

for name in provider_names:
    try:
        provider = get_provider(name)
        selected[name] = provider

        print(
            f"{name:12} -> "
            f"{type(provider).__module__}."
            f"{type(provider).__name__}"
        )

    except Exception as exc:
        print(
            f"{name:12} -> ERROR: "
            f"{type(exc).__name__}: {exc}"
        )


print("\n[5] Testing get_provider() with no argument")

try:
    provider = get_provider()

    print("Returned:")
    print(provider)

    if provider is not None:
        print("Class:", type(provider).__name__)
        print("Module:", type(provider).__module__)
    else:
        print("WARNING: get_provider() returned None")

except Exception as exc:
    print(
        "ERROR:",
        type(exc).__name__,
        exc
    )


print("\n[6] Checking Outlook provider directly from MailService")

outlook = providers.get("outlook")

if outlook is None:
    print("ERROR: No Outlook provider exists")
else:
    print("Outlook provider:")
    print(outlook)

    print("Class:", type(outlook).__name__)
    print("Module:", type(outlook).__module__)

    try:
        print("is_configured():", outlook.is_configured())
    except Exception as exc:
        print(
            "is_configured() ERROR:",
            type(exc).__name__,
            exc
        )


print("\n[7] Checking incoming methods on Outlook provider")

if outlook is not None:

    for method_name in dir(outlook):

        if "incoming" in method_name.lower():
            try:
                value = getattr(outlook, method_name)

                if callable(value):
                    print(
                        method_name,
                        "-> METHOD"
                    )
                else:
                    print(
                        method_name,
                        "->",
                        value
                    )

            except Exception as exc:
                print(
                    method_name,
                    "-> ERROR:",
                    type(exc).__name__,
                    exc
                )


print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)