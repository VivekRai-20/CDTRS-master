# OCR Integration Status Report & Handover Guide

This document outlines the current state of the new offline OCR integration within the CDTRS (Central Document Tracking & Routing System), explaining how the pipeline functions across the backend and frontend, and providing a step-by-step guide on what remains to be implemented to achieve full integration.

---

## 1. System Overview (How It Works)

**CDTRS** is a system for tracking and routing documents across organizational departments and employees. 

**The New OCR Engine (`OCR_new/`)**:
The system includes a 100% offline OCR and Document Intelligence Engine. It doesn't just extract raw text; it performs layout analysis, text-type detection (handwritten vs. printed), semantic matching, and field extraction (like identifying if the Director has already written a remark on the physical document).

**The Pipeline**:
1. **Intake**: A document (PDF/Image) is uploaded via the Frontend (`document_intake.py`).
2. **Backend OCR Trigger**: The backend intercepts this upload and triggers `trigger_ocr_processing()` inside `backend/intelligence.py`.
3. **Adapter**: `backend/ocr_adapter.py` acts as a bridge, invoking the `OCR_new` Python module.
4. **Data Storage**:
   - The raw text and confidence scores are saved to the `DocumentOCR` database table.
   - Specific fields (e.g., `DIRECTOR_HANDWRITTEN_REMARK`, `PRIOR_DIRECTOR_REVIEW_DETECTED`) are saved to the `DocumentExtractedField` table.
5. **Routing Suggestion**: The backend runs a semantic matching algorithm to compare the OCR text against department profiles. It generates a `RoutingSuggestion` record, which now includes a `ranked_departments` JSON list (e.g., `[{department: "Engineering", score: 0.85}, ...]`).

---

## 2. What Works Currently (Completed)

**Backend Integration is Complete:**
- `update_intelligence.py` has successfully patched the backend routing logic.
- The `OCR_new` pipeline is fully wired up via `ocr_adapter.py` and successfully runs locally without internet.
- Semantic matching executes correctly, populating the `ranked_departments` JSON payload in the API response.
- Specific extracted fields (like Director remarks) are successfully captured into the database as "unverified" extractions.

**Frontend Integration (Partial):**
- The document upload successfully hits the backend and triggers the OCR process.
- The UI can read the basic `routing_suggestion` and auto-populate a single dropdown choice if a high-confidence match is found.

---

## 3. What is Remaining (To-Do for Next Developer)

The backend is doing all the heavy lifting and returning rich intelligent data, but the **Frontend UI is currently ignoring the advanced data**. The remaining tasks focus on exposing this data to the user and allowing them to verify it.

### Task A: Frontend Display of Ranked Departments (DONE)
**Status**: Completed. `ranked_departments` (each with `department`, `department_id`, `score`, best first) is returned by `/documents/{id}` and `/documents/{id}/routing-suggestion`. `RoutingDialog` shows the top 5 as clickable chips that set the Department row.

**The Goal**: Instead of just defaulting a dropdown to a single department, show the user the top 3-5 departments the AI thinks this document belongs to, along with their confidence scores.

**Files to Modify**: 
- `frontend/components/routing_dialogs.py` (specifically `RoutingDialog`)

**Instructions**:
1. Parse `document.routing_suggestion.ranked_departments` (which will be a JSON list).
2. Update the UI to render a list of cards or a small table showing the suggested department names and scores (e.g., "Engineering - 85% match").
3. Make these visual elements clickable so that clicking one immediately selects it as the routing destination in the dialog.

### Task B: Director Remark UI Verification (DONE)
**Status**: Completed in `frontend/components/document_viewer.py` (DS only): an "OCR: Director Instruction Found on the Document" panel with an editable remark, a confirmation checkbox and **Verify & Save**, which writes `verified_value` for `DIRECTOR_HANDWRITTEN_REMARK` and `PRIOR_DIRECTOR_REVIEW_DETECTED`. It is deliberately not on the intake page, which must never bypass the Director review. Desktop intake now sends its OCR_new fields (including handwritten-Director detections) to the backend, where they are stored unverified.

**The Goal**: OCR data is inherently advisory (prone to errors). The Director Secretary (DS) must manually verify the AI's findings before the system completely trusts them.

**Files to Modify**: 
- `frontend/pages/document_intake.py` 
- `frontend/components/document_viewer.py`

**Instructions**:
1. During the document intake or initial viewing process, if `document.extracted_fields` contains `DIRECTOR_HANDWRITTEN_REMARK` or `PRIOR_DIRECTOR_REVIEW_DETECTED`, render a distinct "AI Extraction Verification" panel.
2. Display the raw extracted remark text in an editable `QTextEdit` widget. Allow the user to fix any OCR typos.
3. Display a checkbox for `PRIOR_DIRECTOR_REVIEW_DETECTED`.
4. Add a "Verify & Save" button that sends a payload to the backend to update the `verified_value` and `verified_by` columns for those `DocumentExtractedField` records.

### Task C: Enforce Workflow Gate Constraints (DONE)
**Status**: `_ocr_prior_director_review_detected` only trusts `verified_value`. Re-running OCR keeps DS-verified values.

**The Goal**: The workflow routing system must strictly rely on the *verified* value, not the raw AI extraction, to skip mandatory Director review steps.

**Files to Modify**: 
- `backend/workflow.py` (specifically `_ocr_prior_director_review_detected` and `_assert_director_review_before_work_routing`)

**Instructions**:
1. Update `_ocr_prior_director_review_detected` to query `models.DocumentExtractedField`.
2. Ensure it returns `True` **only if** the `verified_value` explicitly confirms it (e.g., `verified_value.lower() == 'true'`). It must ignore `extracted_value` if it hasn't been verified by a human yet.

### Task D: Enrich Department Metadata for Accurate Semantic Routing
**The Goal**: The OCR semantic matching currently compares document text against a highly limited string: `"Department name: X (code: Y)"`. Because the database lacks descriptive profiles for departments, the AI struggles to route documents based on context (e.g., routing a "bridge structural integrity report" to "Engineering"). 

**Files to Modify**:
- `backend/models.py` (specifically `Department` class)
- `backend/intelligence.py` (specifically the `generate_routing_suggestion` function logic patched by `update_intelligence.py`)

**Instructions**:
1. Add `description = Column(Text, nullable=True)` and `keywords = Column(Text, nullable=True)` to the `Department` database model.
2. Update the semantic matching loop to build a richer reference text: `desc = f"Department: {d.name}. Description: {d.description}. Keywords: {d.keywords}"`.
3. Update the frontend UI in `department_configuration.py` to allow admins to define these descriptions and keywords. This will immediately make the OCR semantic routing significantly more accurate.
### Task E: Upgrade Frontend Intake to Use the New OCR Pipeline (DONE)
**Status**: Completed. The frontend intake OCR now runs on `OCR_new`, and the old `OCR_old/` folder has been removed.

**What was done** (Option B, local):
- Added `frontend/services/ocr_adapter.py`, a thin bridge over `OCR_new`'s `DocumentProcessor` (the frontend counterpart of `backend/ocr_adapter.py`). It puts `OCR_new/` on `sys.path` right after the frontend directory (so the frontend's own `api`/`config`/`models` packages keep precedence), shares one processor instance, and maps `DocumentResult` onto the keys `ocr_service.py` already reads (`raw_text`, `confidence`, `is_handwritten`, `pages_processed`, `fields`, `department_suggestion`).
- `frontend/services/ocr_service.py` now imports the engine from that adapter instead of `OCR/ocr.py` + `OCR/rules.py`. The service's own logic (fallbacks, priority/date normalisation, Director remark detection, returned keys) is unchanged.
- Field extraction patterns now come from `OCR_new/extraction/patterns.yaml`; the suggested department on the intake form comes from the `department` / `departments` fields OCR_new extracts. Semantic department ranking remains in the backend (`backend/intelligence.py`), also on `OCR_new`.
