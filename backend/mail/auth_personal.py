# ==============================================================================
# PZ_26/08 - Microsoft OAuth 2.0 Device Code Flow Authenticator for Personal Outlook
# Allows connecting @outlook.com / @hotmail.com accounts for testing with zero Azure setup
# ==============================================================================

import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests

# Microsoft Graph Public Client ID for Personal / Consumer accounts
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"  # Microsoft Graph Public Client
SCOPES = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read offline_access"
DEVICE_CODE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

def authenticate_personal_outlook():
    print("=" * 65)
    print("CDTRS Personal Outlook Account Authentication (Testing Mode)")
    print("=" * 65)
    print("Requesting Microsoft Device Code...")

    payload = {
        "client_id": CLIENT_ID,
        "scope": SCOPES
    }

    try:
        resp = requests.post(DEVICE_CODE_URL, data=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to obtain device code: {resp.status_code} - {resp.text}")
            return False

        data = resp.json()
        user_code = data.get("user_code")
        device_code = data.get("device_code")
        verification_uri = data.get("verification_uri", "https://microsoft.com/devicelogin")
        expires_in = data.get("expires_in", 900)
        interval = data.get("interval", 5)

        print("\n" + "-" * 65)
        print("ACTION REQUIRED ON YOUR BROWSER:")
        print(f"1. Open this URL in any browser: {verification_uri}")
        print(f"2. Enter this Code:              {user_code}")
        print("3. Sign in to your Outlook account and click 'Accept' / 'Continue'")
        print("-" * 65 + "\n")
        print(f"Waiting for your authorization (code expires in {expires_in // 60} minutes)...")

        # Poll token endpoint
        token_payload = {
            "client_id": CLIENT_ID,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code
        }

        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(interval)
            t_resp = requests.post(TOKEN_URL, data=token_payload, timeout=15)
            t_data = t_resp.json()

            if t_resp.status_code == 200:
                access_token = t_data.get("access_token")
                refresh_token = t_data.get("refresh_token")

                # Get user profile info
                headers = {"Authorization": f"Bearer {access_token}"}
                me_resp = requests.get(GRAPH_ME_URL, headers=headers, timeout=15)
                me_email = "your-account@outlook.com"
                me_name = "Outlook User"
                if me_resp.status_code == 200:
                    me_data = me_resp.json()
                    me_email = me_data.get("mail") or me_data.get("userPrincipalName") or me_email
                    me_name = me_data.get("displayName") or me_name

                # Save token cache
                token_file = Path(__file__).parent / ".token_cache.json"
                cache_payload = {
                    "client_id": CLIENT_ID,
                    "user_email": me_email,
                    "user_name": me_name,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": (datetime.utcnow() + timedelta(seconds=t_data.get("expires_in", 3600))).isoformat() if "datetime" in globals() else ""
                }
                with open(token_file, "w", encoding="utf-8") as fw:
                    json.dump(cache_payload, fw, indent=2)

                print("\n" + "=" * 65)
                print("[SUCCESS] Outlook Account Connected Successfully!")
                print(f"Connected Account: {me_name} ({me_email})")
                print(f"Token Saved:      {token_file}")
                print("=" * 65)
                return True

            err = t_data.get("error")
            if err == "authorization_pending":
                sys.stdout.write(".")
                sys.stdout.flush()
            elif err == "slow_down":
                interval += 5
            elif err in ("expired_token", "access_denied"):
                print(f"\n[ERROR] Authorization stopped: {err}")
                return False
            else:
                print(f"\n[ERROR] Token error: {t_data}")
                return False

    except Exception as ex:
        print(f"\n[ERROR] Exception during auth: {ex}")
        return False

if __name__ == "__main__":
    authenticate_personal_outlook()
