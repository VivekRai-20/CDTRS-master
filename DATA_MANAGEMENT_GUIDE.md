# CDTRS data management: from demo data to real data

This guide is for the administrator of the CDTRS server PC. It explains what data CDTRS keeps, how to replace the demo
data with your own departments and staff, how documents get into the system and where their files are stored, and how to
back everything up.

All commands are run in a Command Prompt on the server PC, in the backend folder:

```bat
cd /d C:\CDTRS-main\backend
```

The scripts read the database address (DATABASE_URL) from `backend\.env`. They only use packages that are installed
with CDTRS (`requirements.txt` / `imp.txt` in the project folder), so nothing extra has to be installed. If `python` is
not recognised, use the full path in quotes (the user name may contain a space):
`"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"`.

## 1. What data CDTRS keeps

| Layer | What it holds | Tables | Created by |
|---|---|---|---|
| Master data | Departments (with description and routing keywords), accounts, work contexts, staff directory, settings | `departments`, `users`, `work_context_memberships`, `employees`, `system_settings` | Seeding, `import_from_csv.py`, Admin pages |
| Documents and files | Incoming mail, documents, their files, OCR results, routing suggestions | `incoming_messages`, `documents`, `attachments`, `document_ocr`, `document_extracted_fields`, `routing_suggestions`, plus the files in `backend\uploads` | DS intake, mail sync, OCR |
| Workflow data | Workstreams, assignments, progress, reviews, remarks, reminders, notifications, history | `document_branches`, `work_teams`, `work_items`, `progress_updates`, `work_item_reviews`, `work_stage_changes`, `director_reviews`, `document_remarks`, `reminders`, `notifications`, `workflow_events` | People using the application |
| Admin audit | Configuration and security changes | `audit_logs` | Admin actions |

Only the master data has to be prepared by you. Everything else is created by using the application.

### Accounts, work contexts and the staff directory

- **Account** (`users`): username, password, full name, primary role (ADMIN, DS, DIRECTOR, TSO, HOD or EMPLOYEE), home
  department, e-mail addresses and an active flag.
- **Work context** (`work_context_memberships`): one "hat" the user can wear, with a type (the same six values) and, for
  HOD and EMPLOYEE, a department. A user can hold several hats, for example EMPLOYEE of Engineering and HOD of Customer
  Experience, and switches between them in the sidebar of the desktop app. The active hat, not the primary role, decides
  what the user sees and may do. The desktop app sends it with every request in the `X-Work-Context-Id` header; without
  the header the server uses the hat that matches the primary role, or else any active hat.
- An account without an active work context cannot log in ("This account has no active work context. Contact an
  administrator.").
- **One TSO rule**: only one active TSO context exists in the whole organisation. Giving the TSO hat to someone (by
  the import or in User Configuration) takes it away from the previous holder; the startup seeding only designates a
  TSO when there is none.
- **Staff directory** (`employees`): HR reference data (employee code, name, designation, department, e-mail, linked
  account); not a login. Routing uses it: the designations of a department's staff are part of the department profile,
  and a staff member named in a document or Director remark is suggested.

## 2. Moving from demo data to real data

### 2.1 The demo data

A new installation is filled from `backend\data\seed_data.json`: 15 departments (PROD, ENG, EXEC, ENT, CX, CR, MBT, PTN,
CONS, TECH, OPS, TALENT, CORP, FIN, SUPPORT), each with a description and routing keywords, and 17 demo accounts:

| Username | Password | Work contexts |
|---|---|---|
| corp | cdtrs@admin | ADMIN |
| director | cdtrs@director | DIRECTOR |
| exec_user | cdtrs@ds | DS (Director's Secretary) |
| tso_user | cdtrs@tso | TSO, EMPLOYEE ENG |
| hod_prod, hod_eng, hod_cit, hod_corp, hod_ptc | cdtrs@hod | HOD of two to four departments each |
| emp_anil, emp_vikram, emp_sneha, emp_rahul, emp_sunil, emp_pooja, emp_kamble, emp_rajesh | cdtrs@emp | EMPLOYEE of their department; six of them are also HOD of another department |

### 2.2 What seeding does at every backend start

Every time the backend starts it creates missing tables and columns and then runs the seeding (`crud.seed_data`) with
`backend\data\seed_data.json`. It only **creates what is missing**; it never changes or deletes existing data:

| Data | What seeding does |
|---|---|
| Departments (matched by name or code, any case) | Missing ones are created. For existing ones only an **empty** description or keyword list is filled in; nothing else is changed. |
| Staff directory (matched by employee code) | Missing records are created; existing ones are not changed. |
| Accounts (matched by username) | Missing ones are created with `default_password`. Existing accounts are never changed: role, name, department, e-mail addresses, password and active status stay as they are. |
| Work contexts | Only accounts created in this run get their hats. Hats an administrator removed are not switched on again. |
| TSO | A TSO from the file is designated only when no active TSO exists, and only if that account is active. |
| Settings | Missing default settings are added. |

Everything is saved in one transaction. The console then shows a line such as
`[CDTRS SEED] 15 departments, 17 accounts, ... work contexts.` If the file is missing, nothing is seeded. A seeding
error is printed as `[STARTUP WARN] ...`, nothing from that run is saved, and the backend still starts.

So changes made in the Admin pages (deactivated accounts, removed hats, the chosen TSO, edited departments) are kept.
But whenever a demo account or department is missing from the database, for example in a new or reset database, the
seeding creates it again, demo password included. Empty `seed_data.json` before going live (2.3).

### 2.3 Keeping the demo data out of a new database

Keep a copy of the demo file, then empty it:

```bat
cd /d C:\CDTRS-main\backend
copy data\seed_data.json data\seed_data_demo.json
notepad data\seed_data.json
```

Replace the whole content with:

```json
{"departments": [], "system_users": [], "employees": []}
```

From then on seeding only adds missing default settings, and `reset_db.py` creates a database **without any accounts**,
so run `import_from_csv.py` straight after it (section 2.6). `seed_data.json` is part of the program files: when you
install a newer CDTRS version, make sure your edited copy is kept. Keep `seed_data_demo.json` as well: the automated
tests need the demo accounts, in a separate test database (section 2.7).

### 2.4 Clearing documents or resetting the database

Stop the backend (close the `start_backend.bat` window) and make a backup first (section 6).

| Command | Deletes | Keeps |
|---|---|---|
| `python clear_documents.py --confirm` | All documents and their workflow data, incoming mail items, attachment records, OCR results, suggestions, reminders, notifications | Departments, accounts, hats, staff directory, settings, admin audit log, and the files in `backend\uploads` |
| `python reset_db.py --confirm` | **Everything** in the `cdtrs` database (drops and re-creates the whole `public` schema), then rebuilds the 23 tables and seeds from `seed_data.json` | Nothing in the database |
| `python reset_db.py --confirm --wipe-uploads` | As above, and also empties `backend\uploads` | Nothing |

- Both scripts refuse to run without `--confirm`. `clear_documents.py` does not delete stored files; move old year
  folders out of `backend\uploads` yourself if you do not want them. New reference numbers start again at
  `CDTRS-<year>-0001`.
- `--wipe-uploads` empties `backend\uploads` (and a project-level `uploads` folder if one exists). If `UPLOAD_DIR` in
  `backend\.env` points somewhere else, empty that folder yourself.

### 2.5 If you keep the database: deactivate demo accounts and departments

Log in with an ADMIN account:

- **Admin > User Configuration**: select the user with **Manage**, then **Activate / Deactivate**. Inactive accounts
  cannot log in and are not offered when routing or assigning work; seeding does not reactivate them. Accounts cannot be
  deleted in the application, because the history refers to them.
- Accounts created there with **+ Add User** get the hat of their role automatically and can log in at once (EMPLOYEE
  and HOD only when a Primary Department is chosen; TSO only if no active TSO exists). Add more hats with
  **+ Add Context**.
- Remove single hats with **Remove** under Work Contexts (refused while the hat still has open work).
- **Admin > Department Configuration**: **Deactivate** demo departments you do not use. Inactive departments are not
  offered for routing and are never suggested.
- Give the TSO hat to the real TSO (**+ Add Context**, type TSO); this takes it from `tso_user`.

### 2.6 Recommended go-live sequence

1. Prepare `departments.csv` and `accounts.csv` and run the check (section 3). Every department used in `accounts.csv`
   must be in `departments.csv`, because the database will be empty after the reset.
2. Stop the backend and run `python backup_database.py`.
3. Empty `seed_data.json` (section 2.3).
4. `python reset_db.py --confirm --wipe-uploads`
5. `python import_from_csv.py`
6. Start the backend, log in with your new ADMIN account and check **User Configuration** and **Department
   Configuration**.
7. Ask everyone to change their first password (section 6.4) and schedule the daily backup (section 6.2).

### 2.7 A separate test database with the demo data

The automated tests log in with the demo accounts, so run them against their own database and test server, never the
real ones. Replace `<password>` with the PostgreSQL password:

```bat
cd /d C:\CDTRS-main\backend
"C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h localhost -U postgres cdtrs_test
copy /y data\seed_data.json data\seed_data_real.json
copy /y data\seed_data_demo.json data\seed_data.json
set DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5432/cdtrs_test
set UPLOAD_DIR=./uploads_test
python reset_db.py --confirm
copy /y data\seed_data_real.json data\seed_data.json
python run_server.py --port 8123 --host 127.0.0.1 --no-mail
```

- `set` only applies to that Command Prompt window and takes precedence over `backend\.env`.
- `--no-mail` switches mail off (MAIL_CHANNEL=off), so the test server never syncs the real DS mailbox or sends
  e-mails. `MAIL_CHANNEL=off` in a `.env` file does the same.
- Never add `--wipe-uploads` here: it always empties `backend\uploads`, the real documents, whatever UPLOAD_DIR says.
- Copying `seed_data_real.json` back keeps the real server from creating demo accounts.

## 3. Importing real departments and accounts

`backend\import_from_csv.py` loads departments and accounts from two spreadsheets. It uses the same code as the seeding
(`crud.apply_seed_payload`), but in update mode: existing departments and accounts are updated from the files (3.5).
The import is all-or-nothing: if anything fails while saving, it prints "Import failed - nothing was saved" with the
reason, and the database is unchanged.

### 3.1 Files and folders

| Folder | Content |
|---|---|
| `backend\data\import_templates\` | `departments.csv` and `accounts.csv` (header row only), `departments_example.csv` and `accounts_example.csv` (filled-in examples) |
| `backend\data\import\` | Your filled-in files (default folder; not stored in git, so staff lists stay on the server) |

```bat
cd /d C:\CDTRS-main\backend
mkdir data\import
copy data\import_templates\departments.csv data\import\
copy data\import_templates\accounts.csv data\import\
```

Fill them in with Excel and save with **Save As > CSV UTF-8 (Comma delimited)**. `departments.xlsx` and `accounts.xlsx`
with the same columns also work: the active sheet is read, and if both a .csv and an .xlsx exist the .csv is used.
Column names are not case-sensitive ("Full Name" is read as `full_name`) and empty rows are skipped. Format
employee-code columns as Text in Excel so leading zeros are kept.

### 3.2 departments.csv

| Column | Meaning |
|---|---|
| `name` | Required. A row whose name or code matches an existing department (any case) updates that department; its name is not changed. |
| `code` | Short unique code, e.g. `FIN`; stored in capitals. |
| `description` | What the department handles, in one or two sentences (section 4). |
| `keywords` | Routing keywords, separated by commas (section 4). |

```csv
name,code,description,keywords
Finance & Accounts,FIN,"Budget, bills, payments, audit objections and financial sanctions.","budget, bill, payment, invoice, audit, sanction, expenditure, GFR"
Human Resources,HR,"Recruitment, leave, service records, training and staff welfare.","recruitment, leave, service book, promotion, training, pension, APAR"
Stores & Purchase,SP,"Procurement, tenders, supply orders and stock.","purchase, tender, quotation, supply order, GeM, stock, indent"
```

For a department that already exists, the import replaces the description and keywords when the file gives them
(empty cells leave them unchanged) and sets the code only if the department has none. Rename departments in
**Department Configuration**.

### 3.3 accounts.csv

| Column | Meaning |
|---|---|
| `username` | Required. The key: a row with an existing username updates that account. |
| `full_name` | Display name (default: the username). |
| `role` | Primary role: `ADMIN`, `DS`, `DIRECTOR`, `TSO`, `HOD` or `EMPLOYEE` (default `EMPLOYEE`). |
| `department` | Home department, by code or name. Required for HOD and EMPLOYEE. |
| `designation` | Post, e.g. Accounts Officer (default `Staff`). |
| `employee_code` | Staff number. EMPLOYEE rows with a code also get a staff-directory record. |
| `email`, `outlook_email`, `gov_email` | Addresses for notifications. `email` must be unique. |
| `password` | First password for **new** accounts (default `cdtrs@123`). Existing passwords are never changed. |
| `contexts` | Optional list of hats (3.4). |

Roles: ADMIN manages users, departments and settings; DS (Director's Secretary) registers and routes documents; DIRECTOR
reviews and remarks; TSO receives work directly from the DS; HOD runs a department's work; EMPLOYEE works on
assignments.

```csv
username,full_name,role,department,designation,employee_code,email,outlook_email,gov_email,password,contexts
admin,System Administrator,ADMIN,,System Administrator,,admin@example.gov.in,,,ChangeMe@1,
ds_office,Director's Secretary,DS,,Director's Secretary,,ds@example.gov.in,,,ChangeMe@1,
tso,Technical Staff Officer,TSO,,TSO,EMP-0001,tso@example.gov.in,,,ChangeMe@1,TSO; EMPLOYEE:FIN
hod_fin,Meera Iyer,HOD,FIN,Head of Finance,EMP-0002,meera.iyer@example.gov.in,,,ChangeMe@1,HOD:FIN; HOD:SP
emp_ravi,Ravi Verma,EMPLOYEE,FIN,Accounts Officer,EMP-0003,ravi.verma@example.gov.in,,,ChangeMe@1,
```

Department codes and names may be written in any case (`fin` finds FIN).

### 3.4 The contexts column

Syntax: `TYPE` or `TYPE:DEPARTMENT`, several separated by `;` (a comma also works). TYPE is one of the six roles;
DEPARTMENT is a code or name.

| contexts | role, department | Resulting hats |
|---|---|---|
| (empty) | EMPLOYEE, FIN | EMPLOYEE of FIN |
| (empty) | HOD, FIN | HOD of FIN |
| (empty) | DS, DIRECTOR, ADMIN or TSO | that hat, without a department |
| `HOD:FIN; HOD:SP` | HOD, FIN | HOD of FIN and HOD of SP |
| `EMPLOYEE:ENG; HOD:QA` | EMPLOYEE, ENG | EMPLOYEE of ENG and HOD of QA |
| `EMPLOYEE; HOD:CX` | EMPLOYEE, ENG | EMPLOYEE of ENG (own department) and HOD of CX |
| `TSO; EMPLOYEE:FIN` | TSO | TSO and EMPLOYEE of FIN |

- A filled-in `contexts` value replaces the default, so include the main hat as well.
- Only one TSO exists: the first row that gives a TSO hat makes that (active) account THE TSO, taking the hat from
  the current holder; further TSO entries are ignored.
- Listed hats are created, or switched on again if they had been removed. Hats that are not listed are never removed;
  remove them in **User Configuration**.

### 3.5 Check, import and re-run

```bat
cd /d C:\CDTRS-main\backend
python import_from_csv.py --check
python import_from_csv.py
```

Another folder: `python import_from_csv.py D:\staff_lists --check`

The script prints how many departments and accounts it read, then one line per problem marked `ERROR` or `NOTE`. Any
ERROR stops it with "Nothing was imported."; fix the file and run it again. A NOTE (an EMPLOYEE without `employee_code`
is added as an account only, without a staff-directory record) does not stop it. `--check` changes no data, but it needs
the database, because the files may refer to departments that already exist there.

Besides empty or unknown values, the check reports: a code or username used twice in a file, a department code that
already belongs to another existing department, an e-mail used twice in the file or already belonging to a different
account, and an `employee_code` used twice.

Running the import again is safe: nothing is duplicated. Existing accounts get the full name, role, designation,
employee code, home department and the e-mail addresses given in the file; staff-directory records are updated the
same way. Passwords and the active/inactive status of existing accounts never change. If you import into a database
that still holds the demo accounts, a username such as `director` updates the demo account and it keeps its demo
password: reset it (section 6.4).

The backend can keep running during an import. The files in `data\import` contain first passwords: delete them or store
them safely afterwards.

### 3.6 Older tool: import_employees.py

`python import_employees.py <file.xlsx|file.csv> [--seed-db]` rewrites the `employees` list inside `data\seed_data.json`
from a staff roster (unknown departments are added to the file with the first four letters of the name as code; default
password `cdtrs@emp`); `--seed-db` then runs the seeding. It cannot set roles or hats, and the seeding creates its
entries again whenever they are missing (section 2.2). Use `import_from_csv.py` instead.

## 4. Department routing data

When a document is read (OCR), CDTRS suggests the department it probably belongs to. The suggestion only assists: the DS
decides, and the routing dialog shows the five best-matching departments.

### 4.1 Where to enter it

In **Admin > Department Configuration** the table shows name, code, routing keywords and status (the description
appears as a tooltip), and the search box also searches descriptions and keywords. **Edit** opens a dialog with Name,
Code, Description and Routing keywords. An import of `departments.csv` (section 3.2) also sets them, replacing the
current text when the file gives a value.

Keywords may be separated by commas, semicolons or new lines; they are stored as one comma-separated line with
duplicates (ignoring case) removed. Changes apply to documents read from then on; an existing document's suggestion is
only recalculated when the document is analysed again (for example after a Director remark).

### 4.2 How the suggestion is calculated

For each active department a keyword score is taken as the highest of these signals:

| Signal | Score |
|---|---|
| The full department name appears in the text | 1.0 |
| OCR found a "Department:" line naming it | 0.95 |
| Configured routing keywords found: 1 / 2 / 3 or more | 0.55 / 0.75 / 0.9 |
| All words of the name appear, in any order | 0.85 |
| The department code as a separate word, same capitals | 0.8 (0.5 for a two-letter code) |
| A staff member of the department is named in the text | 0.6 |
| Built-in topic words (picked from words in the name, code and description such as finance, procurement, legal, research): 1 / 2 / 3 / 4 or more | 0.2 / 0.45 / 0.65 / 0.8 |

This is combined with the semantic similarity between the document and the department profile (name, code, description,
keywords, topic words, staff designations) from the local embedding model:
`score = 1 - (1 - keyword) x (1 - similarity)`. A department is suggested only when the score is at least 0.3 and
either the keyword score is at least 0.2 or the similarity at least 0.4. A Director remark that names a department or
staff member overrides this calculation, and so does a department the DS chose on the intake form.

### 4.3 How keywords are matched

- Case and punctuation are ignored: `e-office` matches "E-Office".
- A phrase of several words must appear as exactly that sequence (`supply order` does not match "supply orders").
- A single word of six letters or more also matches words that start with the same six letters (`payment` matches
  "payments", `procurement` matches "procured").
- A single word of four or five letters matches only itself (`bill` does not match "bills").
- A single word of three characters or less (HR, IT, GST, RTI, tax) only counts when it stands in the document as a
  separate word in CAPITALS, however you typed it: `tax` matches only "TAX", `GeM` only "GEM".

### 4.4 Tips for good routing data

- Write the description as one or two plain sentences listing the subjects the department handles.
- Use 5 to 15 keywords that are typical for that department only; avoid words found in almost every letter (letter,
  request, office, government) and do not give the same keyword to two departments.
- Use phrases for common words (`service book`, `supply order`), add both forms of short words (`bill, bills`) and
  include the abbreviations your documents really use (GFR, APAR).
- Register a few real sample documents, look at the ranking in the routing dialog and adjust the keywords of departments
  that are missed or wrongly suggested.

## 5. Getting documents in

### 5.1 Manual upload in the desktop app

1. Log in with a DS account (DS hat active) and open **Document Intake**.
2. Click **Manual Intake / Upload File** and choose the file. The server reads it (OCR) and fills in the fields and the
   suggested department.
3. Check and correct the fields, then click **Register Document**.
4. The routing dialog opens. The first routing goes to the **Director alone**: the server refuses (400) the Director
   together with HODs, employees or the TSO in one step, and refuses routing to HODs, employees or the TSO until a
   Director review exists. The exception is a letter that already carries a Director review: once the DS has verified
   the OCR field `PRIOR_DIRECTOR_REVIEW_DETECTED` as detected, it can go straight to one or more HODs, employees or the
   TSO.

The server accepts `.pdf .docx .doc .xlsx .xls .png .jpg .jpeg .tif .tiff .bmp .webp .txt .csv .zip`; OCR reads
`.pdf .png .jpg .jpeg .tif .tiff .bmp .webp .docx .txt`. The size limit is `MAX_FILE_SIZE` in `backend\.env`
(20971520 bytes = 20 MB by default).

### 5.2 Mail sync

With mail configured in `backend\.env` (`MAIL_CHANNEL=outlook` or `intranet`; see OUTLOOK_INTEGRATION_GUIDE.md and
Intranet_testing.md) the backend checks the DS mailbox for unread messages every 30 seconds, and **Sync Now** on the DS
**Inbox** page checks at once. Each message becomes an intake item (`incoming_messages`); its message ID is stored, so
the same e-mail is never imported twice, and it is marked as read in the mailbox. Attachments are saved in
`backend\uploads\<year>\intake_<message id>\`. The DS opens the item, checks it in Document Intake and registers it; the
attachments then belong to the new document. Registering the same item a second time is refused (409 "This message
was already registered as document ...").

### 5.3 REST endpoint for scanners and other systems

`POST /api/v1/intake/manual-upload` (multipart form) creates a document from a file. The caller must be logged in with a
DS hat.

| Field | Required | Meaning |
|---|---|---|
| `file` | yes | The document file |
| `title` | yes | Title |
| `received_date` | yes | Date received, e.g. `2026-09-25` or `25/09/2026` (unreadable: today) |
| `priority` | no | `CRITICAL`, `HIGH`, `MEDIUM` (default) or `LOW`; URGENT, IMMEDIATE, NORMAL and ROUTINE are also accepted |
| `mode` | no | Source channel, default `MANUAL_UPLOAD` |
| `subject`, `description`, `deadline` | no | Free text; due date |
| `source`, `sender_name`, `sender_reference` | no | Sending organisation (default `Manual Intake`), sender, sender's own reference number |
| `ocr_text`, `confidence`, `ocr_fields` | no | Text and fields already read (`ocr_fields` as a JSON object); with `ocr_text` the server does not run OCR again |
| `suggested_department_id`, `suggested_employee_id` | no | Department or user chosen in advance |

There is no reference-number field: the server assigns `CDTRS-<year>-NNNN`. Without `ocr_text` the server runs OCR on
the file before it answers, which can take a minute for a scanned document. The answer is HTTP 201 with the document as
JSON (`doc_id`, `reference_no`, `lifecycle` RECEIVED, attachments, history). Register it with
`POST /api/v1/documents/<doc_id>/register` (the desktop app does both steps). Errors: 401 invalid token, 403 not in
the DS hat, 409 duplicate, 413 file too large, 415 file type not accepted.

Example with the `curl` built into Windows (replace the values in angle brackets):

```bat
curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"username\": \"<ds user>\", \"password\": \"<password>\"}"
```

The answer contains `access_token` and the user's `contexts`; note the `id` of the DS context.

```bat
curl -X POST http://127.0.0.1:8000/api/v1/intake/manual-upload ^
  -H "Authorization: Bearer <access_token>" ^
  -H "X-Work-Context-Id: <DS context id>" ^
  -F "title=Annual budget allocation 2026-27" ^
  -F "received_date=2026-09-25" ^
  -F "priority=HIGH" ^
  -F "sender_reference=FIN/2026/114" ^
  -F "file=@C:\scans\budget_letter.pdf"
```

### 5.4 Duplicate detection

- Every stored file gets a SHA-256 checksum (`attachments.checksum`).
- **Registering**: if the file equals the original file of an existing document, the server answers 409 "This file is
  already registered as document CDTRS-... ("..."). Open that document instead of registering it again." The desktop app
  shows this message.
- **Adding an attachment** (`POST /api/v1/documents/<doc_id>/attachments`): if the same file is already attached to
  that document, the answer is 409 "This file is already attached to this document as ...". `attachment_type` must be
  ORIGINAL, EMAIL_ATTACHMENT, SUPPORTING_DOCUMENT (default) or PROGRESS_ATTACHMENT, in any case (otherwise 422); only
  the DS may add an ORIGINAL (403), and a `progress_update_id` must belong to the same document (422).
- Mail attachments are not checked when they arrive (the e-mail itself is recognised by its message ID); once registered
  they count as originals for later uploads. Files attached to progress updates are not checked. After
  `clear_documents.py` the old records are gone, so the same files can be registered again.

### 5.5 File storage

Files are stored under `UPLOAD_DIR` (default `./uploads`, relative to the backend folder):

```text
C:\CDTRS-main\backend\uploads\
  <year>\<doc_id>\               files of one document: original, supporting documents, progress attachments
  <year>\intake_<message id>\    attachments of a synchronised e-mail (they stay here after registration)
  _analysis\                     temporary copies while the DS intake reads a file (deleted right away)
```

- `<year>` is the year of the upload, so a file added later to an older document goes into a newer folder.
- A file never overwrites another: a second file with the same name is saved as `name_1.ext`, then `name_2.ext`, and so
  on.
- The relative path is stored in `attachments.storage_key`. Do not rename or move files, or downloads fail with "Stored
  file is missing from disk."
- The application never deletes stored files. Back them up together with the database (section 6).

## 6. Backups, restore and passwords

### 6.1 Backup

```bat
cd /d C:\CDTRS-main\backend
python backup_database.py
```

or double-click `scripts\backup_database.bat`. It writes `cdtrs_db_YYYYmmdd_HHMM.dump` (the whole database,
pg_dump custom format) and `cdtrs_uploads_YYYYmmdd_HHMM.zip` (the contents of `backend\uploads`) to
`C:\CDTRS-main\backups\`.

| Option | Meaning |
|---|---|
| `--dest D:\cdtrs_backups` | Other backup folder |
| `--keep 30` | Backups of each kind to keep (default 14; older ones are deleted) |
| `--no-uploads` | Database only |

The database password is taken from DATABASE_URL in `backend\.env`, and `pg_dump` is found in PATH or in
`C:\Program Files\PostgreSQL\<version>\bin`. Copy the backups to another disk or PC regularly.

### 6.2 Daily backup with Task Scheduler

1. Open **Task Scheduler**, choose **Create Basic Task** and give it a name, e.g. CDTRS backup.
2. Trigger **Daily**, at a time when the PC is on.
3. Action **Start a program**: `C:\CDTRS-main\scripts\backup_database.bat`; options such as
   `--dest D:\cdtrs_backups --keep 30` go in **Add arguments**.
4. On the last page tick **Open the Properties dialog**, and on the **Settings** tab tick **Stop the task if it runs
   longer than** 1 hour. When a backup fails, the batch file ends with `pause` and waits for a key press, so without
   this the task would keep running. Alternatively, skip the batch file: program = the full path of `python.exe`
   (e.g. `C:\Users\<name>\AppData\Local\Programs\Python\Python312\python.exe`), arguments
   `backup_database.py --keep 30`, **Start in** `C:\CDTRS-main\backend`.
5. Let the task run under the Windows account that has Python installed (Python is installed per user). Check the
   backups folder now and then: a failed run creates no new `.dump` file.

### 6.3 Restore

A restore replaces the current data.

1. Stop the backend.
2. Restore the database (enter the postgres password when asked):

   ```bat
   "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --clean --if-exists -h localhost -U postgres -d cdtrs C:\CDTRS-main\backups\cdtrs_db_YYYYmmdd_HHMM.dump
   ```

   If the database `cdtrs` does not exist, create it first:
   `"C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h localhost -U postgres cdtrs`
3. Move the current `backend\uploads` folder aside and extract the matching zip into a new one:

   ```bat
   powershell -Command "Expand-Archive -Path C:\CDTRS-main\backups\cdtrs_uploads_YYYYmmdd_HHMM.zip -DestinationPath C:\CDTRS-main\backend\uploads"
   ```
4. Start the backend. Seeding runs at start as usual (section 2.2).

### 6.4 Passwords

| Who | How |
|---|---|
| Any user | Login window, **Change Password**: username, current password, new password twice |
| Administrator | **Admin > User Configuration**, select the user, **Reset Password** |
| On the server (e.g. forgotten admin password) | `python reset_password.py <username> <new_password>`, or `python reset_password.py` to be asked for both; the new password is shown in the window |
| Other programs | `POST /api/v1/auth/change-password` with `{"current_password": "...", "new_password": "..."}` |

Passwords are stored as bcrypt hashes and cannot be read back. `reset_password.py` does not reactivate an inactive
account.

## 7. Database table reference

The 23 tables defined in `backend\models.py`. Enter and change data through the application and the scripts in this
guide; the history tables are append-only by design.

| Table | Purpose |
|---|---|
| `departments` | Departments with code, description and routing keywords |
| `employees` | Staff directory (HR reference data, not a login) |
| `users` | Login accounts |
| `work_context_memberships` | Hats: which user may act in which role and department |
| `incoming_messages` | E-mails and other intake items for the DS |
| `documents` | One row per document: metadata and overall lifecycle |
| `document_branches` | Independent workstreams on a document (Director, department, employee or TSO) |
| `work_teams` | Optional named groups of work items inside a branch |
| `work_items` | One person's work on one branch: stage, deadline, round |
| `progress_updates` | Free-text progress written by the worker |
| `work_item_reviews` | HOD or DS accepting or returning one person's work |
| `work_stage_changes` | Every stage change of a work item |
| `attachments` | Stored files of a document, a progress update or an intake item |
| `director_reviews` | Each Director review with its remark |
| `document_remarks` | Remarks on a document, branch or work item |
| `document_ocr` | OCR text, engine, confidence and status per document |
| `document_extracted_fields` | Fields read by OCR and the values the DS verified |
| `routing_suggestions` | Suggested department or staff member, confidence, reason and ranking |
| `reminders` | Deadline and action reminders |
| `workflow_events` | Complete chronological history of each document |
| `audit_logs` | Administrative and security actions |
| `notifications` | In-app notifications, per user and hat |
| `system_settings` | Key/value settings |

### Key columns

- **departments**: `id`, `name` (unique, max 100), `code` (unique, max 20), `description`, `keywords` (one
  comma-separated line), `is_active`, `created_at`.
- **users**: `id`, `username` (unique, max 50), `password_hash` (bcrypt), `full_name`, `role` (ADMIN, DS, DIRECTOR, TSO,
  HOD, EMPLOYEE), `employee_code`, `designation`, `email` (unique), `outlook_email`, `gov_email`,
  `preferred_mail_channel` (default `outlook`), `department_id` (home department), `is_active`, `created_at`,
  `updated_at`.
- **employees**: `id`, `employee_code` (unique), `full_name`, `department_id` and `designation` (required), `email`,
  `outlook_email`, `gov_email`, `user_id` (linked account), `is_active`.
- **work_context_memberships**: `id`, `user_id`, `context_type` (EMPLOYEE, HOD, DIRECTOR, DS, TSO, ADMIN),
  `department_id` (HOD and EMPLOYEE), `is_active`, `created_at`, `updated_at`; unique per (`user_id`, `context_type`,
  `department_id`).
- **documents**: `doc_id`, `reference_no` (unique, `CDTRS-<year>-NNNN`), `title`, `subject`, `description`,
  `received_date`, `deadline`, `source`, `sender_name`, `sender_reference`, `mode` (text, e.g. MANUAL_UPLOAD),
  `priority` (CRITICAL, HIGH, MEDIUM, LOW), `lifecycle` (RECEIVED, REGISTERED, IN_REVIEW, IN_WORK, WITH_DS, CLOSED),
  `created_by`, `source_message_id`, `ocr_status`, `version`, `created_at`, `updated_at`, `registered_at`, `closed_at`,
  `closed_by_user_id`, `closure_remark`.
- **attachments**: `id`, `document_id`, `progress_update_id`, `uploaded_by_user_id`,
  `uploaded_by_context_membership_id`, `file_name`, `storage_key` (path under UPLOAD_DIR), `file_type`, `file_size`,
  `checksum` (SHA-256), `attachment_type` (ORIGINAL, EMAIL_ATTACHMENT, SUPPORTING_DOCUMENT, PROGRESS_ATTACHMENT),
  `source_message_id`, `created_at`.
- **document_branches** (main columns): `id`, `document_id`, `branch_type` (DIRECTOR, DEPARTMENT, EMPLOYEE, TSO),
  `stage`, `department_id`, `target_user_id`, `target_context_membership_id`, `opened_by_user_id`, `instructions`,
  `requires_hod_validation`, `deadline`, `round_no`, `is_active`, `opened_at`, `closed_at`, `version`.
- **work_items** (main columns): `id`, `document_id`, `branch_id`, `team_id`, `assigned_to_user_id`,
  `assigned_to_context_membership_id`, `assigned_by_user_id`, `instructions`, `deadline`, `stage` (ASSIGNED, UNDER_WORK,
  WAITING, SUBMITTED, UNDER_REVIEW, RETURNED, COMPLETED, CANCELLED), `requires_validation`, `round_no`,
  `continues_item_id`, `is_active`, `assigned_at`, `submitted_at`, `completed_at`, `version`. Progress is free text in
  `progress_updates`; there is no percentage.
