"""
CDTRS Microsoft Graph Mail Endpoint Diagnostic

Tests the SAME cached access token against:
1. /me
2. /me/mailFolders
3. /me/mailFolders/Inbox/messages

No email is sent.
No token is printed.
"""

import sys
import json
from pathlib import Path

import requests


# ============================================================
# PATH
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================
# TOKEN CACHE
# ============================================================

TOKEN_FILE = BACKEND_DIR / "mail" / ".token_cache.json"

print("=" * 70)
print("CDTRS MICROSOFT GRAPH MAIL ENDPOINT TEST")
print("=" * 70)

print("\nToken file:")
print(TOKEN_FILE)

if not TOKEN_FILE.exists():
    print("ERROR: token cache does not exist.")
    sys.exit(1)

with open(TOKEN_FILE, "r", encoding="utf-8") as f:
    token_data = json.load(f)

access_token = token_data.get("access_token")

if not access_token:
    print("ERROR: access_token missing.")
    sys.exit(1)

print("Access token present: YES")
print("Token length:", len(access_token))
print("Token dot count:", access_token.count("."))


# ============================================================
# COMMON HEADERS
# ============================================================

headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
}


# ============================================================
# TEST HELPER
# ============================================================

def test_endpoint(number, name, url, params=None):
    print("\n" + "-" * 70)
    print(f"[{number}] {name}")
    print("URL:", url)

    if params:
        print("Params:", params)

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30,
        )

        print("HTTP STATUS:", response.status_code)

        request_url = response.request.url
        print("REQUEST URL:", request_url)

        print("\nResponse:")

        try:
            data = response.json()
            print(
                json.dumps(
                    data,
                    indent=2,
                    ensure_ascii=False,
                )
            )
        except Exception:
            print(response.text[:3000])

        return response

    except Exception as exc:
        print("REQUEST FAILED")
        print(type(exc).__name__, exc)
        return None


# ============================================================
# 1. /me
# ============================================================

response_me = test_endpoint(
    1,
    "Basic Graph identity endpoint",
    "https://graph.microsoft.com/v1.0/me",
)


# ============================================================
# 2. /me/mailFolders
# ============================================================

response_folders = test_endpoint(
    2,
    "Mail folders endpoint",
    "https://graph.microsoft.com/v1.0/me/mailFolders",
    params={
        "$top": "10",
        "$select": "id,displayName,totalItemCount,unreadItemCount",
    },
)


# ============================================================
# 3. /me/mailFolders/Inbox/messages
# ============================================================

response_messages = test_endpoint(
    3,
    "Inbox messages endpoint",
    "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages",
    params={
        "$top": "5",
        "$select": (
            "id,subject,bodyPreview,body,from,"
            "receivedDateTime,hasAttachments,isRead"
        ),
        "$orderby": "receivedDateTime desc",
    },
)


# ============================================================
# 4. UNREAD MESSAGES
# ============================================================

response_unread = test_endpoint(
    4,
    "Unread inbox messages",
    "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages",
    params={
        "$top": "5",
        "$filter": "isRead eq false",
        "$select": (
            "id,subject,bodyPreview,from,"
            "receivedDateTime,hasAttachments,isRead"
        ),
        "$orderby": "receivedDateTime desc",
    },
)


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 70)
print("SUMMARY")
print("=" * 70)

def status(response):
    if response is None:
        return "REQUEST FAILED"
    return str(response.status_code)


print("/me                         :", status(response_me))
print("/me/mailFolders             :", status(response_folders))
print("/me/mailFolders/Inbox/messages :", status(response_messages))
print("Unread messages             :", status(response_unread))

print("\nInterpretation:")

if response_me is not None and response_me.status_code == 200:
    print("✓ Token is accepted by Microsoft Graph /me.")

if (
    response_folders is not None
    and response_folders.status_code == 200
):
    print("✓ Token can access mail folders.")

if (
    response_messages is not None
    and response_messages.status_code == 200
):
    print("✓ Token can access inbox messages.")

if (
    response_folders is not None
    and response_folders.status_code == 401
):
    print(
        "⚠ /me works but /me/mailFolders returns 401."
    )

if (
    response_messages is not None
    and response_messages.status_code == 401
):
    print(
        "⚠ /me works but inbox messages return 401."
    )

if (
    response_folders is not None
    and response_folders.status_code == 403
):
    print(
        "⚠ Mail folders are authenticated but permission is denied (403)."
    )

if (
    response_messages is not None
    and response_messages.status_code == 403
):
    print(
        "⚠ Mail messages are authenticated but permission is denied (403)."
    )

print("=" * 70)