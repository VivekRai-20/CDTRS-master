CDTRS Intranet Mail — Complete Testing Guide

From zero to full test

This guide is for testing the intranet/local IMAP + SMTP mail integration in CDTRS from beginning to end.

Your project structure

C:\Projects\CDTRS-main\
│
├── .env                         ← ROOT .env
│
├── backend\
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── mail\
│   │   ├── service.py
│   │   ├── intranet_provider.py
│   │   ├── outlook_provider.py
│   │   └── base.py
│   │
│   └── tests\
│       └── test_intranet_mail.py
│
└── ...

1. First understand what is being tested

The intranet mail integration has two separate directions:

Incoming mail — IMAP

DS Office Mailbox
        ↓
      IMAP
        ↓
CDTRS IntranetMailProvider
        ↓
CDTRS reads incoming emails
        ↓
attachments/body/subject/sender are parsed

Outgoing mail — SMTP

CDTRS
  ↓
SMTP
  ↓
CDTRS/application mailbox or configured sender
  ↓
recipient receives email

The test file checks these independently.

2. Do we need LAN?

Yes — for the real intranet-mail test

If your intranet mail server is configured as something like:

INTRANET_IMAP_HOST=192.168.1.100
INTRANET_SMTP_HOST=192.168.1.100

then the computer running CDTRS must be able to reach that server.

That normally means:

Your laptop/PC
     │
     │ LAN / same office network
     ↓
192.168.1.100
     │
     ├── IMAP
     └── SMTP

Therefore:

Test

LAN required?

Check Python/imports

No

Check .env loading

No

Check configuration values

No

Check provider object creation

No

Real IMAP connection

Yes

Real IMAP login

Yes

Read real DS mailbox

Yes

Real SMTP connection

Yes

Send a real intranet email

Yes

Test CDTRS + real intranet mail end-to-end

Yes

If you are testing tomorrow from home and the mail server is only reachable on the office LAN, the real IMAP/SMTP connection will not work unless you have an approved route such as the organization's VPN.

Do not assume that 192.168.1.100 will be reachable from outside the office LAN.

3. Does the database need documents?

No — not for the standalone intranet mail test

This is important.

The test file:

backend\tests\test_intranet_mail.py

is designed to test the mail provider directly.

It does not need CDTRS documents in PostgreSQL.

It also does not need to insert documents into the CDTRS database just to test:

IMAP connection

IMAP login

reading the DS inbox

parsing emails

parsing attachments

SMTP connection

sending a test email

So even if your database contains:

0 documents
0 branches
0 work items

the standalone mail test can still work.

Why?

Because the test path is essentially:

.env
 ↓
IntranetMailProvider
 ↓
IMAP/SMTP server

not:

PostgreSQL documents
 ↓
workflow
 ↓
mail

4. Important distinction: standalone test vs full CDTRS test

There are two levels of testing.

Level 1 — Mail provider test

Run:

python backend\tests\test_intranet_mail.py

This tests the mail server integration itself.

Database documents are not required.

Level 2 — Full CDTRS workflow test

This tests things such as:

Incoming email
    ↓
CDTRS sync
    ↓
IncomingMessage
    ↓
Document/intake workflow
    ↓
DS
    ↓
Director
    ↓
HOD / Employee / TSO
    ↓
notifications/emails

For this level, the database and CDTRS application matter.

If you want to test document-specific workflow behavior, you will eventually need suitable database records/documents.

So:

Empty DB is completely fine for tomorrow's standalone intranet mail connectivity test.

5. Before starting tomorrow

Make sure you have:

CDTRS project

Python environment activated

root .env

latest backend/mail/intranet_provider.py

latest backend/mail/service.py

backend/tests/test_intranet_mail.py

access to the intranet mail server

DS mailbox username/password for IMAP

CDTRS/application mailbox username/password for SMTP

SMTP recipient address for the optional send test

6. Verify the test file is in the correct place

The file must be:

C:\Projects\CDTRS-main\backend\tests\test_intranet_mail.py

The .env must be:

C:\Projects\CDTRS-main\.env

Very important

The test file should load:

ROOT_DIR = Path(__file__).resolve().parents[2]
env_path = ROOT_DIR / ".env"

because .env is in the project root, not inside backend.

7. Open PowerShell

Go to the project root:

cd C:\Projects\CDTRS-main

Check that you are in the correct directory:

pwd

You should see something similar to:

Path
----
C:\Projects\CDTRS-main

8. Activate your Python environment

Use the same environment you normally use for CDTRS.

For example, if you use a conda environment:

conda activate <your-environment>

Or if you use a virtual environment:

.\venv\Scripts\activate

Use whichever environment actually contains your CDTRS dependencies.

9. Check Python

Run:

python --version

Then:

python -c "import sys; print(sys.executable)"

This confirms that the expected Python environment is being used.

10. Check that the required packages are importable

The test itself will expose import problems, but you can optionally check:

python -c "import dotenv; print('python-dotenv OK')"

and:

python -c "import backend.mail.intranet_provider"

If your project uses a different import setup, the second command may differ. The actual test file is the authoritative check.

11. Check the ROOT .env

Open:

C:\Projects\CDTRS-main\.env

For intranet testing, the important section should look like this conceptually:

MAIL_CHANNEL=intranet

INTRANET_IMAP_HOST=192.168.1.100
INTRANET_IMAP_PORT=993
INTRANET_IMAP_SECURITY=ssl
INTRANET_IMAP_AUTH=password

DS_MAIL_USER=your_ds_mailbox
DS_MAIL_PASS=your_ds_password

INTRANET_SMTP_HOST=192.168.1.100
INTRANET_SMTP_PORT=587
INTRANET_SMTP_SECURITY=starttls
INTRANET_SMTP_AUTH=password

CDTRS_MAIL_USER=your_cdtrs_mailbox
CDTRS_MAIL_PASS=your_cdtrs_password
CDTRS_SENDER_EMAIL=your_sender_address
CDTRS_SENDER_NAME=CDTRS

INTRANET_ALLOW_SELFSIGNED=true
OVERRIDE_TEST_RECIPIENT_EMAIL=

Use your organization's actual values.

12. Do not mix the old and new variable names

The newer intranet_provider.py uses separate credentials:

Incoming / DS mailbox

DS_MAIL_USER=
DS_MAIL_PASS=

Outgoing / CDTRS application mailbox

CDTRS_MAIL_USER=
CDTRS_MAIL_PASS=
CDTRS_SENDER_EMAIL=
CDTRS_SENDER_NAME=

Older versions used variables such as:

INTRANET_MAIL_USER
INTRANET_MAIL_PASS
INTRANET_SENDER_EMAIL

Do not assume the old variable names work with the new provider.

Use the variables expected by the actual installed intranet_provider.py.

13. Do not put real passwords in this guide

Keep real credentials only in your local .env.

Do not paste the real passwords into chat, GitHub, screenshots, or source code.

Also make sure .env is in .gitignore.

14. First run — configuration test

From:

C:\Projects\CDTRS-main

run:

python backend\tests\test_intranet_mail.py

Do this before trying to send anything.

The first run should verify the local configuration and provider setup.

15. What you should inspect in the output

The test should show configuration-related information while masking passwords.

You want to confirm:

.env found
IMAP host present
IMAP port present
IMAP security present
DS username present
DS password present
SMTP host present
SMTP port present
SMTP security present
CDTRS username present
CDTRS password present
sender present

Passwords should not be printed in plain text.

16. Next test — IMAP connectivity

The test then attempts to connect to:

INTRANET_IMAP_HOST
INTRANET_IMAP_PORT

For example:

192.168.1.100:993

This is the first step that requires the real mail server/network.

If it succeeds

You should get a successful connection/login result.

Then the test checks the mailbox/INBOX.

17. If IMAP connection fails

Do not immediately change Python code.

First check:

A. Are you on the correct LAN?

Check your network connection.

B. Can the machine reach the mail server?

You can test the host:

Test-Connection 192.168.1.100 -Count 2

If ICMP is blocked, this can fail even though the mail port works, so this is only a basic network check.

C. Test the port

For IMAP SSL:

Test-NetConnection 192.168.1.100 -Port 993

For SMTP STARTTLS:

Test-NetConnection 192.168.1.100 -Port 587

Look for:

TcpTestSucceeded : True

If it says False, the problem is likely network/firewall/server accessibility rather than CDTRS workflow code.

18. Check IMAP credentials

If the port is reachable but login fails, check:

DS_MAIL_USER=
DS_MAIL_PASS=

Make sure they are the credentials for the DS mailbox, not the CDTRS sending mailbox.

19. IMAP security must match the server

For example:

INTRANET_IMAP_SECURITY=ssl

means direct SSL/TLS IMAP.

If your server instead requires STARTTLS or plain IMAP, the value must match the server configuration.

Do not randomly switch this value.

Use the organization's mail-server configuration.

20. Test reading incoming emails

Once IMAP login succeeds, the test can retrieve unread messages.

The flow is:

DS mailbox
    ↓
INBOX
    ↓
unread messages
    ↓
IntranetMailProvider
    ↓
IncomingEmailDTO

The test should inspect things such as:

subject

sender

date/time

body

attachment flag

attachments

21. You do not need CDTRS documents for this

This point is worth repeating.

Suppose PostgreSQL contains:

Documents = 0

The IMAP test can still retrieve:

Email 1
Email 2
Email 3

because those messages exist in the mailbox, not in the CDTRS document table.

The test is checking the mail integration before CDTRS creates/uses document records.

22. Best first incoming-mail test

Before testing complicated attachments, have a simple test email in the DS mailbox:

From: test sender
Subject: CDTRS Intranet Test
Body:
This is a test email for CDTRS intranet mail integration.

Then run:

python backend\tests\test_intranet_mail.py

Confirm that the message is detected and parsed.

23. Test an email with an attachment

Send another test message to the DS mailbox:

Subject: CDTRS Attachment Test

Attach something harmless, for example:

test.pdf

or:

test.txt

Run the test again.

Confirm that the parsed email reports an attachment and that its metadata is available.

24. Important: unread/read behavior

The provider is designed around unread-message synchronization.

Therefore, if a message has already been marked/read, it may not appear in an unread-only test.

If you think:

"I sent an email but the test doesn't see it."

first check whether the message is already marked as read.

25. Test outgoing SMTP

The standalone test does not need to send an email automatically.

This is intentional.

Sending is an external side effect.

First make sure:

IMAP works
configuration works
SMTP configuration is present

Then explicitly run the send test.

26. Run the optional SMTP test

Use:

python backend\tests\test_intranet_mail.py --send --recipient your-test-email@example.com

The test should ask for confirmation before actually sending.

Only confirm if you are ready to send a real test email.

27. What to check in the received email

Check:

Sender

It should correspond to:

CDTRS_SENDER_EMAIL=

Recipient

It should be the test recipient.

Subject

It should identify the test.

Body

It should contain the test message.

Mail server

It should have been sent through:

INTRANET_SMTP_HOST
INTRANET_SMTP_PORT

28. SMTP security troubleshooting

For example, if you have:

INTRANET_SMTP_PORT=587
INTRANET_SMTP_SECURITY=starttls

the server must support the corresponding STARTTLS flow.

If the organization uses SSL directly, the configuration will be different.

Again, use the actual mail-server configuration rather than changing values randomly.

29. Test the CDTRS MailService layer

After the direct provider test works, test the service layer.

The architecture is:

CDTRS
  ↓
MailService
  ↓
selected channel
  ↓
IntranetMailProvider
  ↓
IMAP / SMTP

The important setting is:

MAIL_CHANNEL=intranet

This tells CDTRS to use the intranet provider instead of Outlook.

30. Important background-sync correction

The background mailbox synchronization should use:

mail_service.is_configured()

rather than forcing:

mail_service.is_configured("outlook")

because the selected provider comes from:

MAIL_CHANNEL

This matters when switching from Outlook to intranet mode.

31. Test manual CDTRS mailbox synchronization

Once the direct mail-provider test works, run CDTRS/backend and test the mailbox-sync endpoint/function.

At this stage the flow becomes:

DS mailbox
    ↓
IMAP
    ↓
MailService
    ↓
IntranetMailProvider
    ↓
IncomingMessage
    ↓
CDTRS database

Now the database becomes relevant.

32. What happens if the database starts empty?

That is okay.

An empty database means CDTRS has no previously registered documents.

When synchronization receives a new email, CDTRS can create/persist its incoming-message/intake data according to the current implementation.

So you can start with:

Documents: 0
Incoming messages: 0

and test the synchronization flow.

However, the exact database records created depend on the current MailService.sync_ds_mailbox() implementation.

33. Database test sequence

For the full integration test, use this order:

Step 1

Start PostgreSQL.

Step 2

Make sure:

DATABASE_URL=...

points to your CDTRS database.

Step 3

Start the CDTRS backend.

Step 4

Ensure the backend starts without database errors.

Step 5

Send a fresh test email to the DS mailbox.

Step 6

Trigger mailbox synchronization.

Step 7

Check the backend response/log.

Step 8

Check the database for the newly persisted incoming-message/intake record.

34. Test duplicate handling

This is important because your mail synchronization already has duplicate protection.

Suppose you sync:

CDTRS Intranet Test #1

The first sync should create the new record.

If you run synchronization again without a new message, the same email should not be inserted repeatedly.

The expected behavior is similar to:

synced_count = 0
ignored_duplicates = 1

for an already-known message, depending on the exact mailbox contents.

35. Then test attachment persistence

Send:

Subject: CDTRS Attachment Integration Test

with:

sample.pdf

Run synchronization.

Then verify:

IncomingMessage
      ↓
Attachment
      ↓
stored file

The current service stores incoming attachments under the configured upload directory.

For example:

UPLOAD_DIR=./uploads

36. Then test the full workflow

Only after mail synchronization itself works should you test:

Email
 ↓
Incoming message
 ↓
Document/intake
 ↓
DS
 ↓
Director review
 ↓
HOD / Employee / TSO
 ↓
notifications

This is a different test from the standalone mail-provider test.

37. Director/OCR testing is separate

Do not mix the following tests together initially:

mail connectivity

OCR

department semantic routing

Director handwriting detection

workflow gate

database

UI

First prove the mail layer.

Then prove the CDTRS intake layer.

Then prove OCR.

Then prove workflow.

This makes failures much easier to identify.

38. Recommended complete testing order for tomorrow

Use this exact sequence:

1. Connect to office LAN
        ↓
2. Open C:\Projects\CDTRS-main
        ↓
3. Activate CDTRS Python environment
        ↓
4. Verify root .env
        ↓
5. Verify intranet credentials/config
        ↓
6. Run test_intranet_mail.py
        ↓
7. Verify configuration checks
        ↓
8. Verify IMAP connection
        ↓
9. Verify IMAP login
        ↓
10. Verify INBOX access
        ↓
11. Read a simple test email
        ↓
12. Read a test email with attachment
        ↓
13. Test SMTP connection/send
        ↓
14. Verify received test email
        ↓
15. Set MAIL_CHANNEL=intranet
        ↓
16. Start PostgreSQL
        ↓
17. Start CDTRS backend
        ↓
18. Run CDTRS mailbox synchronization
        ↓
19. Verify IncomingMessage/database persistence
        ↓
20. Test duplicate handling
        ↓
21. Test incoming attachment persistence
        ↓
22. Test DS intake/UI
        ↓
23. Test workflow routing
        ↓
24. Test notifications
        ↓
25. Test Director/OCR behavior separately

39. What absolutely does NOT require the LAN

You can do these before going to the office:

✓ Check file structure
✓ Check test file
✓ Check root .env loading
✓ Check imports
✓ Check provider construction
✓ Check configuration validation
✓ Check that passwords are masked
✓ Check CDTRS Python environment
✓ Check database configuration
✓ Run tests that do not contact the mail server

40. What DOES require the LAN

For your current intranet configuration:

✓ IMAP server connection
✓ DS mailbox login
✓ Reading real emails
✓ Reading real attachments
✓ SMTP server connection
✓ Sending real email
✓ Full intranet mail integration

If the organization provides VPN access that routes to the mail server, that may substitute for being physically on the LAN, subject to the organization's network configuration.

41. What does NOT require documents in the database

The standalone test works with:

Documents = 0

because it tests the mail provider.

You can therefore test the mail server first without creating dummy CDTRS documents.

42. What eventually requires the database

The database matters when testing:

MailService.sync_ds_mailbox()
IncomingMessage persistence
Attachment persistence
Document creation/intake
DS dashboard
Routing
Director review
HOD assignment
Employee work
TSO work
Notifications
Workflow history

43. If something fails, identify the layer first

Use this table.

Failure

First thing to check

.env not found

Root .env path

Import error

Python environment / project path

IMAP host unreachable

LAN/VPN/firewall

IMAP port closed

Mail server/network

IMAP authentication failed

DS_MAIL_USER/PASS

SSL error

IMAP security/certificate settings

No emails found

Inbox/unread status

Attachment missing

MIME/message parsing

SMTP connection failed

SMTP host/port/network

SMTP authentication failed

CDTRS_MAIL_USER/PASS

SMTP TLS error

SMTP security mode

Email sent but not received

recipient/mail server/filter

CDTRS sync fails

MailService/DB/config

DB insert fails

PostgreSQL/schema/migration

Duplicate appears

sync/deduplication logic

UI doesn't show intake

frontend/API issue

Workflow routing fails

workflow/backend logic

44. Very important safety rule for tomorrow

Do not start by sending a large number of real emails.

Use:

1 simple incoming email
1 incoming email with attachment
1 outgoing SMTP test

Confirm each stage before moving to the next.

This avoids filling the real mailbox or database with unnecessary test records.

45. Final checklist

Before leaving the test session, record:

[ ] Root .env loaded
[ ] MAIL_CHANNEL=intranet
[ ] IMAP host reachable
[ ] IMAP port reachable
[ ] DS mailbox login successful
[ ] INBOX accessible
[ ] Simple email parsed
[ ] Attachment email parsed
[ ] SMTP host reachable
[ ] SMTP authentication successful
[ ] Test email received
[ ] PostgreSQL running
[ ] CDTRS backend running
[ ] Mail synchronization successful
[ ] IncomingMessage persisted
[ ] Attachment persisted
[ ] Duplicate protection verified
[ ] DS UI receives the intake
[ ] Workflow test completed

46. The two answers to remember

Do we need LAN?

For the real intranet mail server: yes, unless you have an approved VPN/network route that can reach the intranet mail server.

Does the database need documents?

No, not for test_intranet_mail.py.

You can start with an empty CDTRS database and test the standalone IMAP/SMTP integration.

For the full CDTRS workflow, the database becomes part of the test once you move from direct mail-provider testing to mailbox synchronization, document intake, routing, and workflow.

Recommended starting point tomorrow

Start with exactly:

cd C:\Projects\CDTRS-main

then activate your CDTRS environment and run:

python backend\tests\test_intranet_mail.py

Do not start by running the full CDTRS workflow.

First make the direct intranet mail test pass. Then move one layer at a time.