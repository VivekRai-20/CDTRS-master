# CDTRS Outlook & Microsoft Graph Integration Guide

## 1. Overview & Architecture

CDTRS (Central Document Tracking & Routing System) incorporates an enterprise-grade mail integration architecture utilizing **Microsoft Graph API (oAuth 2.0 Client Credentials Flow)**.

This architecture enables:
1. **Automated / Manual DS Inbox Sync**: Direct ingestion of official communications from the Director Secretary (DS) Outlook mailbox into the CDTRS Intake queue.
2. **Persistent Server-Side Attachments**: Attachments from incoming emails are automatically saved in the standard `./uploads/<year>/intake_<msg_id>/` storage hierarchy with cryptographic SHA-256 integrity checksums and relative database keys.
3. **Workflow-Driven Action Reminders**: Dynamic recipient resolution based on real-time document state (Assigned Employee -> HOD -> Director -> DS) with direct email notifications.
4. **Pluggable Mail Provider Layer (`BaseMailProvider`)**: Designed to support future Government Mail (NIC Mail / SMTP / IMAP) integrition without rewriting business logic.

---

## 2. Microsoft Azure Portal Setup (Microsoft Entra ID)

To connect a live Microsoft 365 / Outlook mailbox to CDTRS, follow these steps in the Azure Portal:

### Step 1: Register an Application
1. Navigate to **Azure Portal** (https://portal.azure.com) -> **Microsoft Entra ID** -> **App registrations**.
2. Click **New registration**.
3. Name: `CDTRS Mail Integration Service`.
4. Supported account types: **Accounts in this organizational directory only (Single tenant)**.
5. Redirect URI: Leave blank (Client Credentials Flow does not require user redirect).
6. Click **Register**.

### Step 2: Note Down Application IDs
On the App Overview page, copy:
- pplication (client) ID -> maps to `OUTLOOK_CLIENT_ID`
- Directory (tenant) ID -> maps to `OUTLOOK_TENANT_ID`

3# Step 3: Create a Client Secret
1. In the left navigation, click **Certificates & secrets** -> **Client secrets** -> **New client secret**.
2. Description: `CDTRS Client Secret`.
3. Expires: Choose 12 or 24 months.
4. Click **Add** and immediately copy the **Value** (not Secret ID) -> maps to `OUTLOOK_CLIENT_SECRET`.

### Step 4: Grant API Permissions
1. In the left navigation, click **API permissions** -> **Add a permission** -> **Microsoft Graph**.
2. Select **Application permissions** (required for background daemon synchronization without user sign-in).
3. Check the following permissions:
   - `Mail.Read` or `Mail.ReadWrite` (Allows CDTRS to read and mark processed emails in DS mailbox)
   - `Mail.Send` (Allows CDTRS to dispatch official action reminder emails)
   - `User.Read.All` (Optional, for resolving organization email addresses)
4. Click **Add permissions**.
5. Click **Grant admin consent for <Your Organization>** and confirm.

---

## 3. Environment Variable Configuration

Create or update your `.env` file in `backend/.env` with the following variables:

#` configuration
# OUTLOOK_TENANT_ID=your-azure-tenant-id-guid
	#OUTLOOK_CLIENT_ID=your-azure-client-id-guid
#	=UTLLOK_CLIENT_SECRET=your-azure-client-secret-value
#	OUTLOOK_MAILBOX=ds.office@yourdomain.gov.in
#	OUTLOOK_FOLDER=Inbox

> **Graceful Degradation Note:** If these environment variables are omitted or blank, CDTRS will gracefully operate in unconfigured mode (`status: not_configured`). In this state, manual file uploads and internal reminders work completely uninterrupted without throwing runtime crashes or fabricating false emails.
