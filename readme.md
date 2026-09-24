
Yesterday 10:02 PM

Pasted text(20260909-163203).txt
Document
all apis are working corectly


Pasted code(20260909-163848).py
Python


Pasted code(20260909-164001).py
Python


Pasted code(20260909-164528).py
Python
from PySide6.QtCore import Signal 
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QComboBox 
 
from models.enums import RoleEnum 
from services.auth_service import auth_service 
from core.context.context_manager import context_manager 
from core.navigation.navigation_registry import NavigationRegistry 
 
 
class Sidebar(QFrame): 
    """Primary navigation driven by the user's active operational context.""" 
 
    page_requested = Signal(str) 
    logout_requested = Signal() 
    context_switch_requested = Signal(int) 
 
    department_context_changed = Signal(str) 
    role_context_changed = Signal(str) 
 
    def __init__(self, role: str = "", username: str = ""): 
        super().__init__() 
        self.username = username 
        self._context_switching = False 
 
        # Login's authenticated role is the initial source of truth. 
        self.role = context_manager.active_context_type( 
            fallback_role=role 
        ) 
 
        self.setObjectName("sidebar") 
        self.setMinimumWidth(200) 
        self.setMaximumWidth(280) 
 
        self.layout = QVBoxLayout() 
        self.layout.setContentsMargins(15, 20, 15, 20) 
        self.layout.setSpacing(6) 
 
        title = QLabel("CDTRS") 
        title.setObjectName("sidebarTitle") 
        self.layout.addWidget(title) 
 
        self.user_label = QLabel() 
        self.user_label.setObjectName("sidebarUser") 
        self.user_label.setWordWrap(True) 
        self.layout.addWidget(self.user_label) 
        self.layout.addSpacing(6) 
 
        self.context_selector = None 
        self._build_context_selector() 
 
        self.buttons = {} 
        self._build_menu() 
 
        self.layout.addStretch() 
 
        self.logout_button = QPushButton("Logout") 
        self.logout_button.setObjectName("logoutButton") 
        self.logout_button.clicked.connect(self.logout_requested.emit) 
        self.layout.addWidget(self.logout_button) 
 
        self.setLayout(self.layout) 
        self._refresh_context_display() 
 
    def _build_context_selector(self): 
        contexts = context_manager.contexts() 
        if len(contexts) <= 1: 
            return 
 
        label = QLabel("🔐 Active Context:") 
        label.setStyleSheet( 
            "font-size: 11px; font-weight: bold; color: #94A3B8;" 
        ) 
        self.layout.addWidget(label) 
 
        self.context_selector = QComboBox() 
        self.context_selector.setStyleSheet(""" 
            QComboBox { 
                background: #1E293B; 
                color: #38BDF8; 
                font-weight: bold; 
                padding: 5px 8px; 
                border-radius: 4px; 
            } 
            QComboBox::drop-down { border: none; } 
        """) 
 
        for ctx in contexts: 
            text = getattr(ctx, "context_type", "") or "" 
            department = getattr(ctx, "department_name", "") or "" 
            if department: 
                text += f" • {department}" 
            self.context_selector.addItem(text, getattr(ctx, "id", None)) 
 
        active_id = context_manager.active_membership_id() 
        if active_id is not None: 
            index = self.context_selector.findData(active_id) 
            if index >= 0: 
                self.context_selector.setCurrentIndex(index) 
 
        self.context_selector.currentIndexChanged.connect( 
            self._handle_context_changed 
        ) 
        self.layout.addWidget(self.context_selector) 
        self.layout.addSpacing(6) 
 
    def _build_menu(self): 
        for button in self.buttons.values(): 
            self.layout.removeWidget(button) 
            button.deleteLater() 
 
        self.buttons.clear() 
 
        for item in NavigationRegistry.get_items(self.role): 
            button = QPushButton(item) 
            button.setObjectName("sidebarButton") 
            button.clicked.connect( 
                lambda checked=False, key=item: self.page_requested.emit(key) 
            ) 
            self.buttons[item] = button 
            self.layout.insertWidget(self.layout.count() - 2, button) 
 
    def _refresh_context_display(self): 
        context = context_manager.active_context() 
        display_role = self.role 
 
        if context: 
            display_role = getattr(context, "context_type", None) or display_role 
            department = getattr(context, "department_name", "") or "" 
            if department: 
                display_role += f" • {department}" 
 
        self.user_label.setText( 
            f"{self.username}\n{display_role}" if self.username else display_role 
        ) 
 
    def _handle_context_changed(self, index: int): 
        if self._context_switching or index < 0: 
            return 
 
        context_id = self.context_selector.itemData(index) 
        if context_id is None: 
            return 
 
        self._context_switching = True 
        try: 
            self.context_switch_requested.emit(int(context_id)) 
        finally: 
            self._context_switching = False 
 
    def apply_context(self, context): 
        """Apply a context confirmed by ContextManager.""" 
        old_role = self.role 
        new_role = RoleEnum.normalize( 
            getattr(context, "context_type", None) or 
            RoleEnum.EMPLOYEE.value 
        ) 
        self.role = new_role 
        self._build_menu() 
        self._refresh_context_display() 
 
        department = getattr(context, "department_name", "") or "" 
        if department: 
            self.department_context_changed.emit(department) 
        if old_role != new_role: 
            self.role_context_changed.emit(new_role) 
 
    def set_active(self, active_item: str): 
        for item, button in self.buttons.items(): 
            button.setStyleSheet( 
                "background-color: #1E293B; color: #FFFFFF; font-weight: 600;" 
                if item == active_item else "" 
            ) 
 
    def get_menu_items(self, role: str): 
        return NavigationRegistry.get_items(role) 
fix tehse fies and give tsotaskpage code


Pasted code(20260909-165120).py
Python
this is my main winodw,i dont ahev contexts/tso or any such folder,


Pasted code(20260909-165951).py
Python

Yes — I received the current Sidebar file. I checked it against the context-switch architecture.

There is one important fix I would make: when the user's contexts are loaded after the Sidebar is constructed, apply_context() currently rebuilds the menu but does not first ensure that the multi-context dropdown exists. So a user with Employee • FCTD + HOD • C&IT can still end up without the switcher.

Your current file already has the right overall architecture: context_switch_requested, active_context_changed, and NavigationRegistry are all correct. 


Make this one change in apply_context()
Replace:

        self.role = new_role

        self._build_menu()
        self._refresh_context_display()
with:

        self.role = new_role

        # Context memberships may be loaded after Sidebar construction.
        # Ensure the selector exists for multi-context users.
        self._ensure_context_selector()
        self._sync_context_selector()

        self._build_menu()
        self._refresh_context_display()
That is the only change I would make to this Sidebar right now.

The rest of your implementation is already doing the important things correctly:

selector uses actual membership IDs 


switching emits a request rather than directly changing authentication state 


confirmed context changes rebuild the role/navigation 


navigation uses page_key/label, fixing the earlier NavigationItem issue 


So don't replace the whole Sidebar with another large version. Your uploaded one is already the right base; just make that small apply_context() change.

And yes, HOD Inbox remains part of this fix. The correct chain is now:

Employee • FCTD
      ↓ switch
HOD • C&IT
      ↓
Sidebar changes
      ↓
MainWindow changes context
      ↓
HOD dashboard
HOD Department Tasks
HOD history
      ↓
GET /documents with HOD context
      ↓
C&IT documents only
Your HOD page should therefore not independently decide the active department using auth_service.get_active_department(). The active HOD context should determine the scope.


now i sent the document,no one reviced,i did oen doc to tso,emp,hod,also tahts siwtch dropdown on sidebar also didnt come


Today 8:00 AM
give readmd file of this

Done — I made the Markdown debugging plan with the current symptoms, frozen architecture, diagnosis, and exact next debugging steps.

Download the CDTRS Current Debugging Plan 

You've reached the maximum length for this conversation, but you can keep talking by starting a new chat.


Start new chat

CDTRS_Current_Debugging_Plan.md
Document


Library
/
CDTRS_Current_Debugging_Plan.md


CDTRS — Current Debugging Plan
Current symptoms
After DS sends a document:

DS → Employee: Employee receives it. ✅

DS → HOD: HOD does not receive it. ❌

DS → TSO: TSO does not receive it. ❌

Sidebar context-switch dropdown: does not appear. ❌

These were separate tests, so this is not a multi-branch conflict.

Frozen workflow
DS receives → Director reviews → Director writes natural-language remark → returns to DS → DS performs downstream routing → HOD/Employee/TSO executes → progress/follow-up → DS/Director as required → DS closes

Rules:

Director does not perform downstream routing.

Director does not select departments/employees.

Natural-language Director remarks are not automatically parsed into routing commands.

DS is the downstream routing authority.

DS manually closes the document.

OCR/routing suggestions remain advisory.

Do not reintroduce mandatory CONTINUE/CLOSE decisions.

Current backend
GET /documents is context-aware:

DS → crud.get_ds_inbox()

Director → crud.get_director_inbox(...)

HOD → crud.get_department_inbox(...)

Employee → crud.get_employee_inbox(...)

TSO → active TSO branch lookup using the active TSO context membership.

Therefore, if the correct context membership and routing records exist, HOD/TSO documents should be returned.

Most likely problem
The remaining issue is probably in the frontend context/inbox path, rather than basic routing creation.

HOD / TSO page filtering
HOD and TSO pages should consume:

document_service.get_documents()
and trust the backend's active-context scope.

They should not re-filter using old assumptions such as:

auth_service.get_active_department()

old assigned_employee_id

old owner-only filtering

Employee-stage-only filtering

The Employee path working is evidence that the API/repository stack is not universally broken.

Sidebar context dropdown
The current Sidebar already has context-selector support, but apply_context() needs to ensure the selector exists after contexts are loaded.

Targeted change:

def apply_context(self, context) -> None:
    new_role = RoleEnum.normalize(
        getattr(context, "context_type", None) or self.role
    )

    self.role = new_role

    self._ensure_context_selector()
    self._sync_context_selector()

    self._build_menu()
    self._refresh_context_display()
Do not replace the whole Sidebar.

MainWindow
Use the newer context-driven architecture:

context_manager

NavigationRegistry

lazy page creation

page_requested

context_switch_requested

active_context_changed

Do not silently mix it with the older eager-page MainWindow.

Also verify whether the current MainWindow references contexts.tso.tasks while the actual TSO page lives under pages/. Reconcile this explicitly.

Debugging order
1. Check /auth/contexts
For the affected logged-in user, verify:

HOD membership exists

TSO membership exists

correct context_type

correct membership IDs

HOD has the correct department_id

context_manager actually receives/stores the memberships

2. Check /documents with context headers
For HOD:

GET /documents
X-Work-Context-Id: <HOD membership id>
Expected: HOD-routed document appears.

For TSO:

GET /documents
X-Work-Context-Id: <TSO membership id>
Expected: TSO-routed document appears.

For Employee:

GET /documents
X-Work-Context-Id: <Employee membership id>
Expected: employee document appears.

This separates backend/context problems from frontend display/filtering problems.

3. Check HOD Inbox
It should load:

document_service.get_documents()
and display the returned documents.

The active HOD context must determine scope.

4. Check TSO Tasks
It should load:

document_service.get_documents()
and display returned TSO documents.

Do not apply Employee-style filtering.

5. Check Sidebar
If /auth/contexts returns multiple memberships but the dropdown is absent:

verify context_manager stores them;

verify Sidebar can see them;

apply the small apply_context() fix;

verify _ensure_context_selector() creates the dropdown when there are multiple contexts;

verify _sync_context_selector() selects the active membership.

6. Check Document Intake source
The current file set still contains an older document_intake variant with old direct-routing/bypass wording and _update_action_button_text references.

Before another replacement:

identify the actual file imported by the running app;

remove stale/duplicate variants only where appropriate;

ensure new intake always goes to Director first;

preserve Director → DS return.

Expected final test
DS
 ↓
Create/receive document
 ↓
Director Inbox
 ↓
Director reviews + remarks
 ↓
DS receives returned document
 ↓
DS Route
 ├── Employee
 ├── HOD
 └── TSO
 ↓
Correct context sees document
 ↓
Work / progress
 ↓
Follow-up when required
 ↓
DS final closure
For a multi-context user:

Sidebar
  Context ▼
    Employee
    HOD
Immediate next action
Do not rewrite the project yet.

First establish these three facts:

What /auth/contexts returns for the affected user.

What /documents returns with the correct X-Work-Context-Id.

Whether context_manager contains multiple contexts.

Those three checks will pinpoint the failing layer before another file is changed.


I am working on a PySide6 + FastAPI + PostgreSQL desktop application called CDTRS (Centralised Document Tracking and Routing System).

I will send you the project files folder-by-folder after this message. DO NOT start changing code until I have finished sending the relevant files and explicitly ask you to review/change them.

Your first job is to understand the existing project and its intended workflow. Do not assume that an older file/version is the correct source of truth if I later provide a newer file.

==================================================
1. PROJECT PURPOSE
==================================================

CDTRS is a role-based document tracking and routing system.

Frontend:
- Python
- PySide6 / Qt Widgets
- QSS styling
- Role/context-based desktop UI

Backend:
- FastAPI
- SQLAlchemy
- PostgreSQL
- REST API

The frontend communicates with the real backend through an API repository/service layer.

IMPORTANT:
- MockRepository is permanently OUT OF SCOPE.
- Do not introduce mock repositories or fake backend data.
- The real FastAPI + PostgreSQL backend is the source of operational data.

==================================================
2. MAIN ROLES
==================================================

The system has these operational roles/contexts:

- DS = Director Secretary
- DIRECTOR
- TSO
- HOD
- EMPLOYEE
- ADMIN

A user can have multiple work contexts.

For example:
- The same user may have EMPLOYEE context and HOD context.
- The active context determines:
  - dashboard
  - navigation
  - permissions
  - inbox
  - assignments
  - notifications
  - department/data scope

There is a backend concept called WorkContextMembership.

The frontend has a context manager and sidebar context selector/dropdown.

DO NOT treat a user's database role alone as sufficient when the active context system is involved.

==================================================
3. FROZEN DOCUMENT WORKFLOW
==================================================

This is extremely important.

The intended workflow is:

INCOMING DOCUMENT
        ↓
DS receives/ingests document
        ↓
DS sends document to DIRECTOR
        ↓
DIRECTOR REVIEWS DOCUMENT
        ↓
DIRECTOR writes a natural-language remark/instruction
        ↓
DIRECTOR returns document to DS
        ↓
DS reads Director's instruction
        ↓
DS performs actual operational routing
        ↓
HOD / Employee / TSO work happens
        ↓
Progress / follow-up
        ↓
Possibly another Director review cycle
        ↓
DS finally closes document

The Director is a REVIEWER, not the operational router.

==================================================
4. DIRECTOR RESPONSIBILITY
==================================================

Director ONLY:

- receives document from DS
- reviews document
- writes a natural-language remark/instruction
- returns document to DS

Examples of Director remarks:

"Please close this matter."

"Route this to C&IT and Finance."

"Please get the report prepared and send it back."

"Proceed with necessary action."

The Director does NOT:

- select departments
- select employees
- create teams
- assign HODs
- enable/disable HOD validation
- perform actual downstream routing
- manually close the document

The DS interprets the Director's remark and performs the actual routing/closure.

==================================================
5. IMPORTANT: NO NATURAL-LANGUAGE AUTO-ROUTING
==================================================

DO NOT implement a system where the application parses the Director's natural-language remark and automatically routes the document.

Director remarks are advisory/instructional text.

DS remains the authoritative decision-maker for operational routing.

OCR/routing intelligence may suggest a route, but it is NEVER authoritative.

DS must explicitly review and confirm routing.

==================================================
6. DIRECTOR REVIEW DECISION
==================================================

There must NOT be a mandatory machine-readable:

CONTINUE / CLOSE

decision field required from the Director.

The Director simply reviews and writes a remark/instruction.

Closure is performed manually by DS after reading the Director's instruction.

Director review and DS closure must remain separate workflow/history events.

==================================================
7. REQUIRED DS ROUTING VARIATIONS
==================================================

After Director returns the document to DS, the system must support all of these:

A. DS → Department → HOD → Employee

B. DS → Employee
   HOD validation OFF

C. DS → Employee → HOD → DS
   HOD validation ON

D. DS → Multiple Departments
   Each branch progresses independently.

E. Multiple Employees on one work assignment/team.

F. Cross-department employees in one team/assignment.

G. Multiple assignments/teams when actually required.

H. TSO workflow:
   Director → TSO → DS → Director

   TSO does NOT require HOD validation.

I. Employee progress → DS → Director follow-up.

J. Multiple Director review cycles after execution.

K. Final DS closure.

L. Complete workflow history/audit trail.

==================================================
8. TEAM ASSIGNMENTS
==================================================

The backend now supports team assignments.

A WorkAssignment can have multiple WorkAssignmentMember records.

Important concepts include:

- WorkAssignment
- WorkAssignmentMember
- assigned_to_user_id
- team_name
- members
- routing_id
- requires_hod_validation
- assigned_to_context_membership_id

The first selected employee may be retained as the compatibility/primary assigned_to_user_id, but the actual team can contain multiple members.

Teams may be:

- multiple employees from the same department
- cross-department employees when routed branches permit them
- HOD-created teams within their department
- DS-created cross-department teams

Do not remove legacy single-employee compatibility unless it is demonstrably unnecessary.

==================================================
9. TSO
==================================================

TSO is a distinct operational context.

The backend has a single active TSO concept.

TSO routing creates a TSO branch and assignment.

TSO work should not go through HOD validation.

The TSO must be able to see documents routed to TSO in the TSO context/inbox/tasks area.

If the TSO context membership does not exist, the backend login/context initialization is intended to create/activate it for the designated TSO.

==================================================
10. CONTEXT SYSTEM
==================================================

The backend supports:

- WorkContextMembership
- active context
- context membership ID
- X-Work-Context-Id request header
- /auth/contexts
- /auth/switch-context

The frontend has a context manager responsible for active context.

The API client sends the active context ID using:

X-Work-Context-Id

This is important.

For HOD/Employee/TSO data retrieval, the frontend should NOT simply rely on old flattened role logic such as:

"current user's role = HOD"

The active context must determine the actual scope.

==================================================
11. CURRENT BACKEND DOCUMENT RETRIEVAL MODEL
==================================================

The backend GET /documents endpoint is intended to be context-aware.

Conceptually:

DS:
    DS inbox

DIRECTOR:
    Director inbox

HOD:
    department inbox based on active HOD context/membership

EMPLOYEE:
    employee inbox based on active employee context/membership

TSO:
    documents associated with the active TSO branch/context

Therefore, if an Employee receives a document but HOD or TSO does not see theirs, DO NOT immediately change routing creation.

First investigate:

1. backend branch/assignment creation
2. context membership IDs
3. API request headers
4. GET /documents behavior
5. frontend repository/service
6. page-level filtering
7. MainWindow/context switching
8. Sidebar/context selector

==================================================
12. CURRENT FRONTEND ARCHITECTURE
==================================================

The project has layers roughly like:

API
- client
- endpoints
- exceptions

Repositories
- APIRepository
- repository provider

Services
- auth_service
- document_service
- routing_service
- assignment_service
- progress_service
- inbox_service
- workflow_service
- notification_service
- websocket_service
- OCR service
- event bus

Models
- DocumentModel
- UserModel
- WorkAssignment
- WorkAssignmentMember
- Department
- DocumentRoute
- Notification
- ProgressUpdate
- WorkflowEvent
- Attachment
- enums

Components
- document viewer
- document table
- document info
- routing dialogs
- history components
- notification components
- state widgets
- etc.

Pages
- DS dashboard
- DS inbox
- document intake
- documents
- Director inbox/review
- HOD inbox
- Employee tasks
- TSO tasks
- history
- admin pages
- etc.

Core
- context manager
- navigation registry

ui
-login
- MainWindow
- Sidebar

==================================================
13. CURRENT DEBUGGING PROBLEM
==================================================

At the moment I am testing the real workflow.

I sent a document from DS to Director.

The major current problem is:

THE DOCUMENT IS NOT APPEARING/BEING RECEIVED WHERE EXPECTED.

I tested routing separately:

1. DS → Employee
   Employee DID receive the document.

2. DS → HOD
   HOD DID NOT receive the document.

3. DS → TSO
   TSO DID NOT receive the document.

These were separate tests, not necessarily three branches of one document.

This pattern is important:

EMPLOYEE retrieval works.
HOD retrieval fails.
TSO retrieval fails.

Therefore do not blindly rewrite the routing backend.

We need to determine whether the problem is:

- Director inbox/review flow
- DS intake
- document creation
- Director return
- routing dialog
- backend branch creation
- HOD inbox retrieval
- TSO task/inbox retrieval
- context membership handling
- API context header
- document_service
- APIRepository
- page-level filtering
- MainWindow
- Sidebar/context selector
- or duplicate/stale frontend files.

==================================================
14. SIDEBAR CONTEXT DROPDOWN PROBLEM
==================================================

The Sidebar should show a context-switch dropdown when a user has multiple context memberships.

Currently, the context switch dropdown is NOT appearing.

There is already a context manager and Sidebar architecture.

The current Sidebar logic includes:

- context_manager
- NavigationRegistry
- active_context_changed
- context_switch_requested
- context selector
- apply_context()
- _ensure_context_selector()
- _sync_context_selector()

There appears to be a likely timing/order issue where contexts may be loaded after Sidebar construction.

Do NOT immediately replace the whole Sidebar.

First inspect the exact current Sidebar file I provide.

One known candidate issue is that apply_context() may need to ensure/synchronize the context selector after contexts have been loaded, before rebuilding the menu.

But verify the actual current file before changing anything.

==================================================
15. IMPORTANT SOURCE-OF-TRUTH RULE
==================================================

I may send multiple versions of files.

DO NOT mix old and new versions silently.

For every file I send:

- treat the latest explicitly provided version as the source of truth
- inspect imports
- inspect interfaces
- inspect surrounding architecture
- identify dependencies
- compare with already reviewed files when necessary

If two files appear to belong to different architectures, STOP and tell me.

Do not silently merge incompatible variants.

==================================================
16. CHANGE POLICY
==================================================

I want minimal, controlled changes.

For every folder/file, classify it:

🟢 KEEP
    Compatible. No change needed.

🟡 UPDATE
    Mostly correct but needs a targeted change.

🔴 REPLACE
    Fundamentally incompatible/obsolete and needs a complete replacement.

⚪ DON'T TOUCH
    Unrelated to the current problem.

Do NOT rewrite files just because they could be "cleaner".

Do NOT refactor working code unnecessarily.

Do NOT introduce a new architecture unless the existing architecture is fundamentally broken.

==================================================
17. FOLDER-BY-FOLDER PROCESS
==================================================

I will send files folder-by-folder.

For each folder:

1. Read ALL relevant files I provide.
2. Understand dependencies between them.
3. Identify compatibility problems.
4. Classify every relevant file as:
   🟢 KEEP
   🟡 UPDATE
   🔴 REPLACE
   ⚪ DON'T TOUCH
5. Explain the actual reason.
6. Only then propose changes.
7. When changes are approved, provide COMPLETE replacement files for changed files.
8. Do not give random snippets if a complete file replacement is safer.
9. Syntax-check/test the changed files when possible.
10. Freeze that folder before moving to the next one.

Do not repeatedly revisit already frozen folders unless a later file proves there is a real dependency issue.

==================================================
18. IMPORTANT EXISTING DECISIONS
==================================================

The following decisions are already made and should not be reversed:

- No MockRepository.
- Real FastAPI/PostgreSQL only.
- Director is reviewer, not operational router.
- DS is responsible for actual downstream routing.
- No automatic natural-language routing from Director remarks.
- No mandatory Director CONTINUE/CLOSE machine decision.
- DS performs final closure.
- OCR/routing suggestions are advisory only.
- Team assignments are supported.
- Cross-department teams are supported where valid.
- TSO has no HOD validation.
- Context membership determines operational scope.
- Legacy compatibility should be preserved where practical.
- Do not invent unnecessary new RouteType enum values just for teams.
- Existing route types can represent team routing through assignment/team data.
- Fresh database resets are acceptable during development/testing.

==================================================
19. CURRENT GOAL
==================================================

The immediate goal is NOT to redesign CDTRS.

The goal is to make the existing application actually work end-to-end.

Especially:

DS
 ↓
Director
 ↓
Director Review
 ↓
DS
 ↓
HOD / Employee / TSO
 ↓
work/progress
 ↓
DS
 ↓
Director follow-up/review when required
 ↓
DS closure

And ensure:

- every recipient sees the document in the correct context
- context switching works
- sidebar context dropdown appears for multi-context users
- assignments work
- teams work
- progress works
- HOD validation works
- TSO flow works
- Director follow-up works
- history is correct
- notifications are correct
- no stale/duplicate architecture is being used

==================================================
20. HOW I WANT YOU TO WORK
==================================================

Be careful and diagnostic.

If something fails, trace the actual data flow:

UI
→ Page
→ Service
→ Repository
→ API endpoint
→ CRUD
→ Database

and in the opposite direction:

Database
→ API endpoint
→ Repository
→ Service
→ Page
→ UI

Do not assume that because backend data exists, the frontend will display it.

Do not assume that because a route was created, the recipient inbox is correct.

Check:

- IDs
- context membership IDs
- user IDs
- department IDs
- branch IDs
- assignment IDs
- active/inactive flags
- API headers
- endpoint paths
- response models
- frontend filtering

I will now start sending the actual files.

For now, DO NOT modify anything.

Wait for my files and instructions.