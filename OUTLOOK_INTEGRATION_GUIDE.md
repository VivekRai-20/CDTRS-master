# Connecting an Outlook / Microsoft 365 mailbox

CDTRS can read the Director's Secretary (DS) mailbox through **Microsoft Graph**
and send workflow notification e-mails from it. For an office mail server
(IMAP/SMTP), see [Intranet_testing.md](Intranet_testing.md) instead.

Mail is optional. Without it, documents are uploaded by hand and notifications
appear only inside the app.

---

## 1. What the integration does

| Direction | Behaviour |
|---|---|
| **Incoming** | Every 30 seconds while the backend runs (or at once with **Sync Now** in the DS Inbox), CDTRS reads the **unread** messages of the configured folder. Each message becomes an intake item. Its attachments are saved under `backend\uploads\<year>\intake_<message id>\` with a SHA-256 checksum. The message is then marked as read. A message already imported is recognised by its Graph message id and never imported twice |
| **Registering** | The DS turns an intake item into a document. Registering the same message twice is refused (HTTP 409) |
| **Outgoing** | Workflow notifications (assignment, review, reminders, …) are e-mailed through the mail channel set in `MAIL_CHANNEL`. The address used is the account's *Outlook e-mail*, or its main e-mail if that is empty |

The provider code is in `backend\mail\outlook_provider.py` and the sync logic in
`backend\mail\service.py`.

---

## 2. Choose a mode

| Mode | For | Sign-in |
|---|---|---|
| **A. Personal** | Testing with an @outlook.com / @hotmail.com mailbox | You sign in once in a browser; CDTRS keeps a refresh token |
| **B. Organisation** | A Microsoft 365 mailbox of the office | An app registration with a client secret; no user sign-in |

In both modes, set this in `backend\.env`:

```
MAIL_CHANNEL=outlook
```

---

## 3. Mode A: personal Outlook.com mailbox (testing)

1. Put these in `backend\.env`:

   ```
   MAIL_CHANNEL=outlook
   OUTLOOK_AUTH_MODE=personal
   OUTLOOK_MAILBOX=your.address@outlook.com
   OUTLOOK_FOLDER=Inbox
   ```

2. Sign in once (the PC needs internet access):

   ```
   cd /d C:\CDTRS-main\backend
   python mail\auth_personal.py
   ```

   The script prints a web address and a code. Open the address in any browser,
   enter the code and sign in to the mailbox. The script then saves
   `backend\mail\.token_cache.json`, which git ignores. It uses Microsoft's public
   Graph client, with permission to read and update mail (so imported messages can be marked
   as read), send mail and read your profile.

3. Restart the backend. The mailbox is synced from then on, and the token refreshes
   itself.

To disconnect, delete `backend\mail\.token_cache.json` and restart. **While that
file exists, CDTRS treats Outlook as configured**, even if the other `OUTLOOK_`
settings are empty.

---

## 4. Mode B: Microsoft 365 organisation mailbox

### 4.1 Register an application (Azure portal / Microsoft Entra ID)

1. Go to https://portal.azure.com → **Microsoft Entra ID** → **App registrations**
   → **New registration**.
2. Name it, for example `CDTRS Mail Integration`. Choose *Accounts in this
   organizational directory only*. Leave the Redirect URI empty. Click **Register**.
3. On the overview page, copy:
   - the **Application (client) ID**, which goes in `OUTLOOK_CLIENT_ID`
   - the **Directory (tenant) ID**, which goes in `OUTLOOK_TENANT_ID`
4. Go to **Certificates & secrets** → **New client secret**. Choose an expiry (12 or
   24 months) and copy the **Value** (not the Secret ID) into `OUTLOOK_CLIENT_SECRET`.
   Put a reminder in your calendar to renew it before it expires.
5. Go to **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Application permissions**, and add:
   - `Mail.ReadWrite`: to read the DS mailbox **and mark imported messages as read**
     (`Mail.Read` alone cannot mark them).
   - `Mail.Send`: to send notifications.
6. Click **Grant admin consent** and confirm.

Application permissions allow access to *every* mailbox in the organisation. Ask
your Exchange administrator to limit the app to the DS mailbox with an application
access policy (Exchange Online PowerShell `New-ApplicationAccessPolicy`, with
`-AccessRight RestrictAccess` and a mail-enabled security group containing the DS
mailbox).

### 4.2 Settings in `backend\.env`

```
MAIL_CHANNEL=outlook
OUTLOOK_AUTH_MODE=organizational
OUTLOOK_TENANT_ID=<directory (tenant) id>
OUTLOOK_CLIENT_ID=<application (client) id>
OUTLOOK_CLIENT_SECRET=<client secret value>
OUTLOOK_MAILBOX=ds.office@yourdomain.gov.in
OUTLOOK_FOLDER=Inbox
```

- `OUTLOOK_MAILBOX` is the DS mailbox that is read and that sends the notifications.
- Make sure `backend\mail\.token_cache.json` does **not** exist. A leftover personal
  token is tried first and would be used against the organisation mailbox.
- `OUTLOOK_AUTH_MODE` documents the mode you chose. CDTRS decides by what is
  present: a token cache file means personal mode; tenant id, client id, secret and
  mailbox mean organisation mode.

Restart the backend after any change to `.env`.

---

## 5. Test it

From `C:\CDTRS-main\backend`:

| Command | What it checks |
|---|---|
| `python tests\test_mail_service.py` | Which mail provider CDTRS selects and whether it counts as configured |
| `python tests\test1.py` | With a personal token: that it works for `/me`, the mail folders and the Inbox messages. Nothing is sent |
| `python tests\test_provider.py someone@example.com` | Sends **one real** test e-mail through Graph to that address |

Then send a test e-mail with an attachment to the DS mailbox. Leave it **unread**,
and click **Sync Now** in the DS Inbox. It should appear with its attachment.

A second backend (for example a test server on port 8123) that uses the same
`backend\.env` would also sync the DS mailbox. Start such servers with
`python run_server.py --port 8123 --host 127.0.0.1 --no-mail`. `MAIL_CHANNEL=off`
switches mail off completely.

While testing notifications, add
`OVERRIDE_TEST_RECIPIENT_EMAIL=you@example.com` to `backend\.env`. All notification
e-mails then go to you instead of real staff. Remove it before going live.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Sync says *"Outlook mail integration is not configured"* | `MAIL_CHANNEL` is not `outlook`; or no token cache (mode A) or a missing tenant/client/secret/mailbox value (mode B). Restart the backend after editing `.env` |
| `Personal token refresh HTTP 400: … invalid_grant …` in the backend window | The refresh token has expired or been revoked. Run `python mail\auth_personal.py` again |
| `401` / `403` from Graph in mode B | Admin consent not granted; `Mail.ReadWrite` / `Mail.Send` missing; the application access policy excludes the mailbox; or the secret expired |
| Imported messages stay unread in the mailbox | CDTRS cannot mark them as read. Mode B: give the app `Mail.ReadWrite`. Mode A: sign in again with `python mail\auth_personal.py` (tokens from before this version only had `Mail.Read`). They are never imported twice either way |
| Nothing is imported | Only **unread** messages in `OUTLOOK_FOLDER` are read. Check the folder name (for example `Inbox`) |
| Proxy / certificate errors | The server needs HTTPS access to `login.microsoftonline.com` and `graph.microsoft.com`; ask IT to allow them |
| Notifications are not sent | The account has no Outlook or main e-mail address (Admin → User Configuration); or the system setting `mail.notifications_enabled` is `false` |

Without mail settings, CDTRS reports the mailbox as *not configured* and keeps
working: manual uploads, in-app notifications and reminders are unaffected.
