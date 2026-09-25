# CDTRS on the office intranet: LAN setup and mail testing

This guide is for the office IT person who sets up CDTRS on the office network and tests the office mail integration. It assumes CDTRS is already installed and working on one PC (PostgreSQL, Python 3.12 and the packages from `imp.txt`), in `C:\CDTRS-main`.

All backend settings are in **`backend\.env`**. There is no project-wide `.env` in the project root any more. The desktop app has its own **`frontend\.env`**.

---

## 1. What "intranet" means here

```
 +---------------------------------+   office LAN   +---------------------------+
 | SERVER PC                       |     (HTTP)     | CLIENT PCs                |
 |  PostgreSQL (database "cdtrs")  |                |  CDTRS desktop app        |
 |  CDTRS backend, port 8000  <----+----------------+  (start_frontend.bat)     |
 +----------------+----------------+                +---------------------------+
                  |
                  | IMAP in / SMTP out   (optional)
                  v
 +---------------------------------------------------------+
 | OFFICE MAIL SERVER                                      |
 |  DS mailbox     -> CDTRS reads new documents over IMAP  |
 |  CDTRS mailbox  -> CDTRS sends notifications over SMTP  |
 +---------------------------------------------------------+
```

- **One server PC** runs PostgreSQL and the CDTRS backend. Client PCs never connect to PostgreSQL; they only talk to the backend port (8000 by default).
- **Other PCs** run the desktop app and connect to the server over the LAN.
- **Optional office mail server**: CDTRS reads incoming documents from the **DS mailbox** (IMAP) and sends workflow notifications from the **CDTRS mailbox** (SMTP). The two mailboxes are separate accounts with separate passwords.

What each part of the testing needs:

| Test | Office LAN (or VPN) needed | Documents in the database needed |
|------|:---:|:---:|
| Configuration check (`test_intranet_mail.py`) | No | No |
| IMAP connect, login, read DS mailbox | Yes | No |
| SMTP send of a test email | Yes | No |
| Mailbox sync from CDTRS, intake, workflow | Yes | No (an empty database is fine; records are created by the test) |

If the mail server is only reachable inside the office, the real IMAP/SMTP tests will not work from home unless the organisation provides a VPN that routes to it.

---

## 2. Server PC setup for the LAN

### 2.1 Set HOST and PORT

Open `C:\CDTRS-main\backend\.env` in Notepad and check:

```
HOST=0.0.0.0
PORT=8000
```

- `HOST=0.0.0.0` lets other PCs connect. `HOST=127.0.0.1` allows this PC only.
- If you change `PORT`, use the same number in the firewall rule and in every client's `CDTRS_API_URL`.

If `backend\.env` does not exist yet: `cd /d C:\CDTRS-main\backend` then `copy .env.example .env`, and fill in `DATABASE_URL` and `SECRET_KEY`.

### 2.2 Start the backend

Double-click `C:\CDTRS-main\start_backend.bat`. It runs `backend\run_server.py` with HOST and PORT from `backend\.env`.

- **Keep this window open.** Closing it stops the server for everybody.
- The backend reads `backend\.env` only when it starts. After any change to `backend\.env`, close the window and start it again.

### 2.3 Allow the port in Windows Firewall

Open an **Administrator Command Prompt** (Start, type `cmd`, right-click Command Prompt, Run as administrator) and run:

```
netsh advfirewall firewall add rule name="CDTRS backend" dir=in action=allow protocol=TCP localport=8000
```

This only needs to be done once. To confirm the rule exists:

```
netsh advfirewall firewall show rule name="CDTRS backend"
```

Only the backend port needs to be opened. PostgreSQL (5432) does not need to be reachable from the LAN.

### 2.4 Find the server's IP address

On the server PC, in a Command Prompt:

```
ipconfig
```

Note the **IPv4 Address** of the network adapter connected to the office LAN, for example `192.168.1.50`. Ask the network administrator to give the server a fixed IP address (or a DHCP reservation); if the address changes, every client stops connecting.

### 2.5 Check from a client PC

1. On the server itself, open a browser at `http://127.0.0.1:8000/health`.
2. On a client PC, open a browser at `http://192.168.1.50:8000/health` (use your server IP).

Both should show a short JSON reply in which `status` is `healthy`. If step 1 works but step 2 does not, the problem is the firewall or the network, not CDTRS (see section 6). From PowerShell on the client you can also test the port:

```
Test-NetConnection 192.168.1.50 -Port 8000
```

`TcpTestSucceeded : True` means the port is reachable.

---

## 3. Client PC setup

Do this on every PC that will run the desktop app.

1. Install **Python 3.12 (64-bit)** for the current user (default location `%LOCALAPPDATA%\Programs\Python\Python312\`).
2. Copy the CDTRS project folder to `C:\CDTRS-main` on the client.
3. Install the pinned packages (the versions are identical to `C:\CDTRS-main\imp.txt`, the list of installed packages; do not upgrade or add others):

   ```
   cd /d C:\CDTRS-main
   python -m pip install -r frontend\requirements.txt
   ```

   This is the same pinned set as on the server, so the download is large. If `python` is not recognised, use `py -3.12` instead of `python`, or the full path `"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"`.
4. Create the client settings file:

   ```
   cd /d C:\CDTRS-main\frontend
   copy .env.example .env
   ```

5. Edit `frontend\.env` and set the server address (keep the value alone on the line, with no comment after it):

   ```
   CDTRS_API_URL=http://192.168.1.50:8000/api/v1
   ```

   `CDTRS_API_TIMEOUT` (seconds, default 15.0) can be raised on a slow network.
6. Double-click `C:\CDTRS-main\start_frontend.bat` and log in.

Note: the desktop app reads `frontend\.env`. Only if that file does not exist does it try a `.env` in the current folder (`C:\CDTRS-main` when started with `start_frontend.bat`). If an old `C:\CDTRS-main\.env` from earlier versions is still there, move its settings into `backend\.env` / `frontend\.env` and delete or rename it (for example to `.env.old`) to avoid confusion.

The server PC can run the desktop app too, with `CDTRS_API_URL=http://127.0.0.1:8000/api/v1`.

---

## 4. Mail over the intranet: settings

### 4.1 Variables in backend\.env

The template is section 6 "MAIL" of `backend\.env.example`. Everything there is commented out with `#`:

1. Remove the `#` in front of the `# MAIL_CHANNEL=intranet` line. It is a separate line at the top of section 6, above the Mode A (Outlook) and Mode B (intranet) blocks.
2. In the "Mode B" block (and, if wanted, the "Testing" block), remove the `#` only in front of the `KEY=value` lines. Lines that are only explanations (for example `# Incoming: the DS mailbox that receives documents`) stay commented. Leave the Mode A (Outlook) lines commented.
3. Fill in your values. The result should look like this:

```
MAIL_CHANNEL=intranet

# Incoming: DS mailbox (IMAP)
INTRANET_IMAP_HOST=192.168.1.100
INTRANET_IMAP_PORT=993
INTRANET_IMAP_SECURITY=ssl
INTRANET_IMAP_AUTH=password
DS_MAIL_USER=ds_office@intranet.gov.in
DS_MAIL_PASS=<DS mailbox password>
IMAP_TIMEOUT=20

# Outgoing: CDTRS mailbox (SMTP)
INTRANET_SMTP_HOST=192.168.1.100
INTRANET_SMTP_PORT=587
INTRANET_SMTP_SECURITY=starttls
INTRANET_SMTP_AUTH=password
CDTRS_MAIL_USER=cdtrs@intranet.gov.in
CDTRS_MAIL_PASS=<CDTRS mailbox password>
CDTRS_SENDER_EMAIL=cdtrs@intranet.gov.in
CDTRS_SENDER_NAME=CDTRS

INTRANET_ALLOW_SELFSIGNED=true

# Testing
OVERRIDE_TEST_RECIPIENT_EMAIL=
TEST_MAIL_RECIPIENT=
```

`INTRANET_ALLOW_SELFSIGNED=true` is what the template shows. Keep it `true` only if the mail server uses a self-signed certificate; set it to `false` if the server's certificate is issued by a trusted authority (see 4.3).

| Variable | Meaning | Default if missing |
|----------|---------|--------------------|
| `MAIL_CHANNEL` | `intranet` = office IMAP/SMTP; `outlook` = Microsoft Graph (see OUTLOOK_INTEGRATION_GUIDE.md); `off` (also `none`, `disabled`) = no mailbox sync and no emails at all | `outlook` |
| `INTRANET_IMAP_HOST` / `_PORT` | Mail server name or IP, and IMAP port | (empty) / `993` |
| `INTRANET_IMAP_SECURITY` | `ssl`, `starttls` or `plain` | `ssl` |
| `INTRANET_IMAP_AUTH` | Only `password` is supported | `password` |
| `DS_MAIL_USER` / `DS_MAIL_PASS` | Login of the **DS mailbox** (incoming) | (empty) |
| `IMAP_TIMEOUT` | Seconds to wait for the IMAP server | `20` |
| `INTRANET_SMTP_HOST` / `_PORT` | Mail server name or IP, and SMTP port | (empty) / `587` |
| `INTRANET_SMTP_SECURITY` | `ssl`, `starttls` or `plain` | `starttls` |
| `INTRANET_SMTP_AUTH` | Only `password` is supported | `password` |
| `CDTRS_MAIL_USER` / `CDTRS_MAIL_PASS` | Login of the **CDTRS mailbox** (outgoing) | (empty) |
| `CDTRS_SENDER_EMAIL` | "From" address of CDTRS emails | value of `CDTRS_MAIL_USER` |
| `CDTRS_SENDER_NAME` | "From" display name | `CDTRS` |
| `INTRANET_ALLOW_SELFSIGNED` | `true` = accept a self-signed server certificate | `false` |
| `OVERRIDE_TEST_RECIPIENT_EMAIL` | Send every workflow notification to this one address | (empty = off) |
| `TEST_MAIL_RECIPIENT` | Default recipient for `tests\test_intranet_mail.py --send` (not used by CDTRS itself) | (empty) |

Notes:

- CDTRS treats the mail integration as configured only when the IMAP host, DS user, SMTP host, CDTRS user and sender address are all set. Do not leave `CDTRS_SENDER_EMAIL=` empty: an empty line is not the same as a missing line, and the sender would then be blank. Fill it in or delete the line.
- Do not mix up the two accounts: IMAP logs in with `DS_MAIL_*`, SMTP logs in with `CDTRS_MAIL_*`.
- Workflow notification emails always go out through the office-wide `MAIL_CHANNEL`. With `MAIL_CHANNEL=intranet`, each account's main **email** field is used as the address (if it is empty: the government email, then the Outlook email). Make sure the user accounts have their office email address filled in.
- Keep real passwords only in `backend\.env`. It is git-ignored; never paste it into chat, email or screenshots.

### 4.2 Security modes

The value must match what the mail server offers. Ask the mail administrator; do not guess.

| Value | What happens | Usual port |
|-------|--------------|-----------|
| `ssl` | Encrypted from the first byte (implicit TLS) | IMAP 993, SMTP 465 |
| `starttls` | Plain connection upgraded with STARTTLS | IMAP 143, SMTP 587 |
| `plain` | No encryption (only on a trusted internal network) | IMAP 143, SMTP 25 |

The spellings `tls` (= `starttls`), `ssl/tls` (= `ssl`) and `none` (= `plain`) are also accepted.

### 4.3 Self-signed certificates

Internal mail servers often use a self-signed certificate. CDTRS then refuses the `ssl`/`starttls` connection with a certificate verification error. Set:

```
INTRANET_ALLOW_SELFSIGNED=true
```

This switches off certificate and host-name checking for the mail connection. Use it only for a mail server on the office network that you trust.

### 4.4 Safe testing with OVERRIDE_TEST_RECIPIENT_EMAIL

While testing, set:

```
OVERRIDE_TEST_RECIPIENT_EMAIL=your.test.address@intranet.gov.in
```

Every workflow notification email is then sent to this one address instead of to the real users. Leave it empty (or `none` / `false` / `off`) for normal operation, and restart the backend after changing it. It does not affect the `--send` test in section 5.7, which always uses the recipient you give it.

---

## 5. Testing mail step by step

Test one layer at a time: first the mail server connection, then CDTRS mailbox sync, then the workflow. Keep the number of test emails small: one simple email, one email with an attachment, one outgoing test.

### 5.1 Before you start

You need:

- `backend\.env` filled in as in section 4.1 (both the IMAP and the SMTP part; the test stops if any required value is missing).
- A PC on the office LAN (or VPN) that can reach the mail server.
- Another mail account to send test emails to the DS mailbox, and a mail client (or webmail) where you can see the DS mailbox and mark messages as unread.
- A test recipient address for the SMTP test.

For sections 5.2 to 5.7, **stop the CDTRS backend**, or run it with mail switched off (`start_backend.bat --no-mail`, or `MAIL_CHANNEL=off` in `backend\.env`). A running backend with `MAIL_CHANNEL=intranet` checks the DS mailbox every 30 seconds and would pick up your test emails first.

**Warning for second or test backends.** Every backend that runs with `MAIL_CHANNEL=intranet` syncs the real DS mailbox into **its own** database and marks those emails as read, so the live server never sees them. A second backend for tests (for example on port 8123) must always be started with mail switched off:

```
cd /d C:\CDTRS-main\backend
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

### 5.2 Check that the mail server is reachable

In PowerShell (use your mail server address and ports):

```
Test-NetConnection 192.168.1.100 -Port 993
Test-NetConnection 192.168.1.100 -Port 587
```

`TcpTestSucceeded : True` is needed for both. If it is `False`, fix the network, VPN or firewall first; changing CDTRS settings will not help.

### 5.3 Run the connection test (configuration + IMAP)

```
cd /d C:\CDTRS-main\backend
python tests\test_intranet_mail.py
```

The script loads `backend\.env` (the first line says which file it loaded) and does not touch the CDTRS database. It then:

1. Prints the configuration, with passwords masked.
2. **Configuration check**: the seven required values (`INTRANET_IMAP_HOST`, `DS_MAIL_USER`, `DS_MAIL_PASS`, `INTRANET_SMTP_HOST`, `CDTRS_MAIL_USER`, `CDTRS_MAIL_PASS`, `CDTRS_SENDER_EMAIL`), the two security values (`ssl`/`starttls`/`plain`) and the two auth values (`password`). If anything fails here, the script stops.
3. **IMAP test**: connects, logs in to the DS mailbox, opens INBOX, and fetches up to 10 **unread** messages. For each one it shows Message ID, sender, subject, received time, the attachments (name, size, type) and the start of the body.
4. Prints a final result. No email is sent without `--send`.

"No unread emails were returned" is not an error; it only means the DS mailbox has no unread mail.

### 5.4 Read a simple test email

1. From another account, send an email to the DS mailbox, subject `CDTRS Intranet Test`, with one line of body text.
2. Do not open it (it must stay unread).
3. Run `python tests\test_intranet_mail.py` again.
4. Check that the sender, subject, time and body text are shown correctly.

### 5.5 Read an email with an attachment

1. Send another email to the DS mailbox, subject `CDTRS Attachment Test`, with a small harmless file attached (for example a one-page PDF).
2. Run the test again.
3. Check that the message shows `Attachments: 1` with the correct file name and a plausible size.

### 5.6 Read/unread behaviour

- CDTRS and the test script only look at **unread** messages.
- Reading a message this way marks it as **read** on the mail server. So after one test run the same email will not appear again. The "Unread messages currently available" count is taken after the messages have been fetched, so it can show 0 even though messages were just listed.
- An email opened in a mail client, or already picked up by a running backend (including a second or test backend that was not started with `--no-mail`), is also read.
- To repeat a test, mark the email as unread again in the mail client.

### 5.7 Send a test email over SMTP

```
python tests\test_intranet_mail.py --send --recipient your.test.address@intranet.gov.in
```

The script shows the SMTP server, security mode, sender and recipient, and asks you to type `SEND` (in capitals). Anything else cancels without sending. The email has the subject `[CDTRS] Intranet Mail Integration Test`.

In the received email check that:

- the sender is `CDTRS_SENDER_NAME <CDTRS_SENDER_EMAIL>`;
- the subject and the short test text are correct;
- it did not land in the spam or junk folder.

Command-line options of `tests\test_intranet_mail.py`:

| Option | Effect |
|--------|--------|
| (none) | Configuration check + IMAP test. No email is sent. |
| `--send` | Also sends one real test email (after you type `SEND`). |
| `--recipient <address>` | Recipient for `--send`. Can instead be set as `TEST_MAIL_RECIPIENT=` in `backend\.env` (listed, commented out, in the "Testing" part of `backend\.env.example`). |
| `--all` | Same as `--send`, using `--recipient` or `TEST_MAIL_RECIPIENT`. |
| `--incoming-only` | IMAP test only; SMTP is skipped even if `--send` or `--all` is also given. |

The IMAP test always runs. The script exits with code 0 when all requested tests pass and 1 otherwise.

### 5.8 Check that CDTRS selects the intranet provider

With `MAIL_CHANNEL=intranet` in `backend\.env`:

```
cd /d C:\CDTRS-main\backend
python tests\test_mail_service.py
```

In block `[5] Testing get_provider() with no argument` the class must be `IntranetMailProvider`. If it shows `OutlookGraphProvider`, `MAIL_CHANNEL` is missing or misspelled. The later blocks about Outlook can be ignored for intranet mail. This script does not contact the mail server.

### 5.9 Mailbox sync from CDTRS

1. Make sure PostgreSQL is running and `DATABASE_URL` in `backend\.env` points to the right database. An empty database (no documents) is fine.
2. Send a fresh test email (with an attachment) to the DS mailbox and leave it unread.
3. Start the backend with `start_backend.bat` and check that it starts without database errors.
4. Log in to the desktop app with the DS account (seeded username `exec_user`) in the DS context.
5. Open **Inbox** ("Incoming Communications") and click **Sync Now**.
6. A dialog shows the result, including `New communications: 1`. The message appears in the list.

Also note:

- The backend also syncs automatically every 30 seconds while it runs, so the email may already be in the list before you click Sync Now.
- The Sync Now button calls `POST /api/v1/intake/sync-outlook`. Despite "outlook" in the name (and in some dialog titles), it uses whatever `MAIL_CHANNEL` selects.
- "not configured" in the dialog means `MAIL_CHANNEL` or one of the required mail values is missing, mail is switched off (`MAIL_CHANNEL=off` or `--no-mail`), or the backend was not restarted after editing `backend\.env`.

To check the database directly (adjust `18` to your PostgreSQL version; psql asks for the postgres password):

```
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d cdtrs -c "SELECT id, subject, sender_email, has_attachments, received_at FROM incoming_messages ORDER BY id DESC LIMIT 5;"
```

### 5.10 Duplicate handling

CDTRS remembers each synced email by its Message-ID and never stores the same email twice.

1. After the sync in 5.9, mark the same email as **unread** again in the mail client.
2. Click **Sync Now** again.
3. The result should report 0 new emails and `(1 duplicate(s) skipped)`. No second record appears in the Inbox or in `incoming_messages`.

(The separate checksum check that rejects the same file uploaded twice, with HTTP 409, applies to manual upload and to adding attachments, not to mailbox sync.)

### 5.11 Attachment storage

Attachments of synced emails are saved under the upload folder (`UPLOAD_DIR`, relative to `backend\`):

```
C:\CDTRS-main\backend\uploads\<year>\intake_<message id>\<file name>
```

Two attachments with the same name are stored as `name.pdf`, `name_1.pdf`, and so on; nothing is overwritten. Each attachment is recorded with its size and a SHA-256 checksum:

```
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d cdtrs -c "SELECT id, file_name, storage_key, file_size, source_message_id FROM attachments WHERE source_message_id IS NOT NULL ORDER BY id DESC LIMIT 5;"
```

Check that the file exists at `backend\uploads\<storage_key>` and opens correctly. In the desktop app, an attachment of a synced email that is not yet registered as a document can only be opened in the DS or Admin context; other users get "Only the DS can open unregistered intake attachments." (HTTP 403).

### 5.12 Full workflow

Only when 5.9 to 5.11 work, test the workflow with the synced email:

1. DS opens the message from the Inbox (it opens in **Document Intake**), completes the details and sends it on for Director review. The document is created and OCR runs on it in the background. A message can be registered only once: processing it again is refused with "This message was already registered as document ..." (HTTP 409).
2. Director reviews and returns it to DS; DS routes it to the department(s).
3. HOD assigns work; employee submits progress; HOD reviews; DS closes the document.
4. At each step check the in-app notifications, and (with `OVERRIDE_TEST_RECIPIENT_EMAIL` set) the notification emails at the test address.

Notification emails are sent over intranet SMTP to each account's main **email** field (see 4.1), or to `OVERRIDE_TEST_RECIPIENT_EMAIL` while that is set. They are only sent while the system setting `mail.notifications_enabled` is `true` (the default).

Test OCR, department suggestions and Director handwriting detection separately from mail; mixing them makes failures hard to trace.

---

## 6. Troubleshooting

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Client browser cannot open `http://<server-ip>:8000/health` (times out) | Firewall rule missing, or client on a different network | Add the rule (2.3) in an Administrator Command Prompt; check `Test-NetConnection <server-ip> -Port 8000` |
| "Connection refused" from a client | Backend not running, `HOST=127.0.0.1`, or a different `PORT` | Start `start_backend.bat`; set `HOST=0.0.0.0`; use the same port everywhere |
| Works on the server (`127.0.0.1`) but not from clients | Wrong IP, or firewall | Run `ipconfig` on the server again; the IP may have changed (ask for a fixed IP) |
| Desktop app still connects to `127.0.0.1` | `frontend\.env` missing or `CDTRS_API_URL` not set in it | Create or fix `frontend\.env` (section 3); remove any old root `.env` |
| All clients suddenly lose the connection | Backend window was closed, or the server PC restarted/slept | Start `start_backend.bat` again and keep the window open |
| Backend window closes or shows database errors at start | PostgreSQL stopped, or wrong `DATABASE_URL` | Start the PostgreSQL service; check the password in `DATABASE_URL` |
| Test prints `[WARN] backend\.env was not found` | File missing or saved as `.env.txt` | Run `dir /a C:\CDTRS-main\backend\.env*`; rename to exactly `.env` |
| Configuration check shows `MISSING` | Value empty, still commented out with `#`, or written in an old root `.env` | Fill it in `backend\.env` |
| IMAP or SMTP "connection" fails, `Test-NetConnection` is `False` | Mail server unreachable (LAN, VPN, firewall) | Fix the network first |
| Connection fails although the port is open; errors about SSL, TLS or "wrong version number" | Security mode does not match the port (for example `ssl` on a STARTTLS port) | Use the mode and port the mail administrator gives you (4.2) |
| Error mentioning "certificate verify failed" | Self-signed or internal certificate | `INTRANET_ALLOW_SELFSIGNED=true` (4.3) |
| IMAP login fails | Wrong `DS_MAIL_USER` / `DS_MAIL_PASS`, or the CDTRS account used by mistake | Check the DS credentials; some servers require the full email address as user name |
| SMTP send fails at login or the sender is refused | Wrong `CDTRS_MAIL_*`, or the server does not allow that sender address | Check the CDTRS credentials; use a `CDTRS_SENDER_EMAIL` the CDTRS account may send as |
| Test finds no unread emails | Message already read (earlier test run, mail client, or the running backend) | Mark it unread again (5.6) |
| Emails become read but never appear in the live CDTRS Inbox | Another backend (test server, second PC) with mail switched on synced them into its own database | Start every test backend with `--no-mail` (5.1); mark the emails unread again |
| Test email sent but not received | Spam/junk filter, recipient typo, server relay rules | Check junk folder and the mail server log |
| Sync Now says "not configured" | `MAIL_CHANNEL` not `intranet` (or `off` / started with `--no-mail`), a required value missing, or no restart | Fix `backend\.env` and restart the backend without `--no-mail` |
| Sync Now says "Mailbox sync is a DS action." | Logged in without the DS context | Log in as the DS user and select the DS context |
| No notification emails although SMTP works | Account has no email address, `MAIL_CHANNEL` not `intranet`, or `mail.notifications_enabled` off | Fill in the users' email field; check `backend\.env` and restart (see 4.1, 5.12) |
| Processing an intake message gives "already registered as document" (409) | That email was already turned into a document | Open the existing document instead |
| Opening a synced attachment gives 403 | Not in the DS or Admin context | Switch to the DS context |
| `python` is not recognised | Python 3.12 not on PATH | Use `py -3.12` or the full path to `python.exe` |

When something fails, first find the layer: network, mail server login, CDTRS configuration, database, or desktop app. Do not change Python code to work around a network or password problem.

---

## 7. Final checklist

LAN:

- [ ] `backend\.env`: `HOST=0.0.0.0`, `PORT=8000`
- [ ] Firewall rule "CDTRS backend" added (Administrator Command Prompt)
- [ ] Server IP noted and fixed
- [ ] `http://<server-ip>:8000/health` works from a client browser
- [ ] Each client: Python 3.12, `frontend\requirements.txt` installed, `frontend\.env` with `CDTRS_API_URL` (old root `.env` removed)
- [ ] Each client can log in with `start_frontend.bat`

Mail:

- [ ] Mail values filled in `backend\.env` (not in a root `.env`), `MAIL_CHANNEL=intranet`
- [ ] `OVERRIDE_TEST_RECIPIENT_EMAIL` set during testing
- [ ] Any second or test backend started with `--no-mail`
- [ ] `test_intranet_mail.py`: configuration PASS, IMAP connection + login + INBOX PASS
- [ ] Simple email and attachment email read correctly
- [ ] `--send` test email received with the right sender
- [ ] `test_mail_service.py` shows `IntranetMailProvider`
- [ ] Sync Now creates the intake record; attachment saved under `backend\uploads`
- [ ] Second sync of the same email skips it as a duplicate
- [ ] User accounts have their office email address filled in
- [ ] Workflow run completed; notification emails received at the test address
- [ ] `OVERRIDE_TEST_RECIPIENT_EMAIL` emptied and backend restarted before going live
