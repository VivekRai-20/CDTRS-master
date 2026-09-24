class Endpoints:
    """Backend API paths, relative to the client base_url (/api/v1).

    The shape mirrors the workflow model: documents carry a lifecycle,
    branches are independent workstreams, and work items are one person's
    work.
    """

    # --- Authentication & work contexts ---
    AUTH_LOGIN = "/auth/login"
    AUTH_ME = "/auth/me"
    AUTH_CHANGE_PASSWORD = "/auth/change-password"
    AUTH_CONTEXTS = "/auth/contexts"
    AUTH_SWITCH_CONTEXT = "/auth/switch-context"

    # --- Reference data ---
    USERS_LIST = "/users"
    DEPARTMENTS_LIST = "/departments"
    DEPARTMENT_EMPLOYEES = staticmethod(lambda dept_id: f"/departments/{dept_id}/employees")
    EMPLOYEES_LIST = "/employees"
    WORKFLOW_VOCABULARY = "/workflow/vocabulary"

    # --- Intake ---
    INTAKE_LIST = "/intake"
    INTAKE_SYNC_OUTLOOK = "/intake/sync-outlook"
    INTAKE_MANUAL_UPLOAD = "/intake/manual-upload"
    INTAKE_PROCESS = staticmethod(lambda intake_id: f"/intake/{intake_id}/process")

    # --- Documents ---
    DOCUMENTS_LIST = "/documents"
    DOCUMENTS_INBOX = "/documents/inbox"
    DOCUMENT_CREATE = "/documents"
    DOCUMENT_DETAIL = staticmethod(lambda doc_id: f"/documents/{doc_id}")
    DOCUMENT_UPDATE = staticmethod(lambda doc_id: f"/documents/{doc_id}")
    DOCUMENT_REGISTER = staticmethod(lambda doc_id: f"/documents/{doc_id}/register")
    DOCUMENT_CLOSE = staticmethod(lambda doc_id: f"/documents/{doc_id}/close")
    DOCUMENT_REOPEN = staticmethod(lambda doc_id: f"/documents/{doc_id}/reopen")
    DOCUMENT_REMIND = staticmethod(lambda doc_id: f"/documents/{doc_id}/remind")
    DOCUMENT_REMARKS = staticmethod(lambda doc_id: f"/documents/{doc_id}/remarks")
    DOCUMENT_HISTORY = staticmethod(lambda doc_id: f"/documents/{doc_id}/history")
    HISTORY_ALL = "/history"

    # --- Branches (routing) ---
    DOCUMENT_BRANCHES = staticmethod(lambda doc_id: f"/documents/{doc_id}/branches")
    BRANCH_ASSIGN = staticmethod(lambda branch_id: f"/branches/{branch_id}/work-items")
    BRANCH_REMARK = staticmethod(lambda branch_id: f"/branches/{branch_id}/remark")
    BRANCH_CLOSE = staticmethod(lambda branch_id: f"/branches/{branch_id}/close")

    # --- Director review ---
    DIRECTOR_REVIEW_START = staticmethod(lambda branch_id: f"/branches/{branch_id}/director-review/start")
    DIRECTOR_REVIEW_SUBMIT = staticmethod(lambda branch_id: f"/branches/{branch_id}/director-review")
    DIRECTOR_REVIEWS = staticmethod(lambda doc_id: f"/documents/{doc_id}/director-reviews")

    # --- Work items (one person's work) ---
    WORK_ITEMS_MINE = "/work-items/mine"
    WORK_ITEMS_DEPARTMENT = "/work-items/department"
    DOCUMENT_WORK_ITEMS = staticmethod(lambda doc_id: f"/documents/{doc_id}/work-items")
    WORK_ITEM_DETAIL = staticmethod(lambda item_id: f"/work-items/{item_id}")
    WORK_ITEM_STAGE = staticmethod(lambda item_id: f"/work-items/{item_id}/stage")
    WORK_ITEM_PROGRESS = staticmethod(lambda item_id: f"/work-items/{item_id}/progress")
    WORK_ITEM_PROGRESS_FILE = staticmethod(lambda item_id: f"/work-items/{item_id}/progress-with-file")
    WORK_ITEM_SUBMIT = staticmethod(lambda item_id: f"/work-items/{item_id}/submit")
    WORK_ITEM_REVIEW = staticmethod(lambda item_id: f"/work-items/{item_id}/review")

    # --- Attachments ---
    ATTACHMENT_LIST = staticmethod(lambda doc_id: f"/documents/{doc_id}/attachments")
    ATTACHMENT_UPLOAD = staticmethod(lambda doc_id: f"/documents/{doc_id}/attachments")
    ATTACHMENT_DOWNLOAD = staticmethod(lambda attach_id: f"/attachments/{attach_id}/download")

    # --- OCR & routing intelligence (assistive) ---
    OCR_GET = staticmethod(lambda doc_id: f"/documents/{doc_id}/ocr")
    OCR_RUN = staticmethod(lambda doc_id: f"/documents/{doc_id}/ocr/run")
    OCR_VERIFY = staticmethod(lambda doc_id: f"/documents/{doc_id}/verify-field")
    ROUTING_SUGGESTION = staticmethod(lambda doc_id: f"/documents/{doc_id}/routing-suggestion")
    ROUTING_ANALYZE = staticmethod(lambda doc_id: f"/documents/{doc_id}/analyze-routing")
    # Intake analysis before a document exists (OCR runs on the server)
    INTELLIGENCE_ANALYZE = "/intelligence/analyze"
    INTELLIGENCE_ANALYZE_TEXT = "/intelligence/analyze-text"

    # --- Notifications & reminders ---
    NOTIFICATIONS_LIST = "/notifications"
    NOTIFICATIONS_UNREAD = "/notifications/unread"
    NOTIFICATION_MARK_READ = staticmethod(lambda notif_id: f"/notifications/{notif_id}/read")
    NOTIFICATIONS_MARK_ALL_READ = "/notifications/read-all"
    REMINDERS_LIST = "/reminders"
    REMINDERS_CHECK = "/reminders/check"
    REMINDER_MARK_READ = staticmethod(lambda rem_id: f"/reminders/{rem_id}/read")

    # --- Dashboard & events ---
    DASHBOARD = "/dashboard"
    EVENTS_RECENT = "/events/recent"

    # --- Administration ---
    ADMIN_USERS = "/admin/users"
    ADMIN_USER_DETAIL = staticmethod(lambda user_id: f"/admin/users/{user_id}")
    ADMIN_USER_RESET_PASSWORD = staticmethod(lambda user_id: f"/admin/users/{user_id}/reset-password")
    ADMIN_USER_TOGGLE = staticmethod(lambda user_id: f"/admin/users/{user_id}/toggle-active")
    ADMIN_USER_CONTEXTS = staticmethod(lambda user_id: f"/admin/users/{user_id}/contexts")
    ADMIN_USER_CONTEXT_DELETE = staticmethod(
        lambda user_id, context_id: f"/admin/users/{user_id}/contexts/{context_id}"
    )
    ADMIN_TSO = "/admin/tso"
    ADMIN_ACTIVATE_TSO = staticmethod(lambda user_id: f"/admin/tso/{user_id}/activate")
    ADMIN_DEPARTMENTS = "/admin/departments"
    ADMIN_DEPARTMENT_DETAIL = staticmethod(lambda dept_id: f"/admin/departments/{dept_id}")
    ADMIN_SETTINGS = "/admin/settings"
    ADMIN_AUDIT_LOGS = "/admin/audit-logs"
