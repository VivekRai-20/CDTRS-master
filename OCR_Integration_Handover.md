# OCR integration: status and handover

How the offline OCR engine (`OCR_new/`) is wired into CDTRS, what it does today,
and where to change things. All the planned integration tasks (A–E) are finished.

---

## 1. How it works

```
Desktop app                     Backend                                  OCR_new (in the backend process)
───────────                     ───────                                  ────────────────────────────────
Intake page ── file ──►  POST /intelligence/analyze  ─┐
  (preview before                                     ├─► ocr_adapter.py ─► DocumentProcessor.process()
   registering)                                       │                      PaddleOCR 2.8.1 (lines)
DS registers ─────────►  POST /intake/manual-upload   │                      printed / handwritten per line
Mailbox sync ─────────►  DS processes intake message ─┘                      TrOCR re-reads handwriting
                                  │                                          entities, fields, Director remarks
                                  ▼
            DocumentOCR (text, confidence)
            DocumentExtractedField (unverified), e.g. DIRECTOR_HANDWRITTEN_REMARK,
                                                      PRIOR_DIRECTOR_REVIEW_DETECTED
            RoutingSuggestion.ranked_departments  [{department, department_id, score}, …]
```

- **One engine, on the server.** The desktop app does not load PaddleOCR or torch.
  `frontend/services/ocr_adapter.py` sends the file to the backend
  (`/api/v1/intelligence/analyze`, or `/analyze-text` for text). The backend loads the
  engine once (`backend/ocr_adapter.py`) and warms it up in a background thread when
  it starts.
- **The server stays responsive.** OCR runs in worker threads, and the intake page
  shows a busy dialog instead of freezing.
- **Windows DLL order.** On Windows, torch must be loaded before PaddlePaddle, and
  pyarrow/pandas before PaddleOCR. Otherwise the backend crashes silently, and the app
  reports *"WebSocket error: The remote host closed the connection"*. This is handled
  in `backend/ocr_adapter.py`, `backend/main.py` and `OCR_new/utils/native_libs.py`.
  Keep those imports at the top.

## 2. What is done

| Task | Status | Where |
|---|---|---|
| **A** Ranked department suggestions in the routing dialog | Done | `RoutingDialog` in `frontend/components/routing_dialogs.py` shows the top 5 as clickable chips |
| **B** DS verification of Director remarks found by OCR | Done | `frontend/components/document_viewer.py` (DS only): editable remark, confirmation checkbox, **Verify & Save**. It is deliberately not on the intake page, which must never bypass Director review |
| **C** Workflow gate trusts only verified values | Done | `backend/workflow.py` `_ocr_prior_director_review_detected` uses `verified_value` only. Re-running OCR keeps DS-verified values |
| **D** Department descriptions and keywords for routing | Done | see below |
| **E** Frontend intake uses OCR_new (server-side) | Done | `OCR_old/` removed |

### Task D: department descriptions and routing keywords

- `departments.description` and `departments.keywords` (`backend/models.py`) are added
  to existing databases automatically on start (`database.ensure_schema_columns`).
- The Admin edits them in **Admin → Department Configuration**: a *Description* box
  and *Routing keywords* (comma separated), shown in the table and searchable. They
  can also be imported with `backend/import_from_csv.py`. The demo departments in
  `backend/data/seed_data.json` come with both.
- `backend/intelligence.py` builds each department's profile from its name,
  description and keywords, and uses it for semantic similarity.
- Configured keywords found in the document raise the score: 1 hit → 0.55, 2 → 0.75,
  3 or more → 0.9. Keywords of 3 characters or less (for example `HR`, `IT`) count
  only as whole words in capitals, so "it" in a sentence does not match.

## 3. What the OCR engine does now

| Area | Behaviour |
|---|---|
| Printed text | PaddleOCR 2.8.1, CPU: PP-OCRv3 text detection, PP-OCRv4 recognition. Models are in `OCR_new/models/paddleocr/` (tracked in git) |
| Memory | Pages are padded to 3 square sizes, and lines are read one at a time with widths rounded to fixed steps. One A4 page needed more than 6 GB before; the peak is now about 3 GB (`paddleocr:` settings in `config.yaml`) |
| Printed vs handwritten | `ocr/text_type_detector.py`: 20 line-shape features and a built-in logistic model. Lines with fewer than 3 glyphs are UNKNOWN. A classifier trained on your own lines replaces the built-in model when present |
| Handwriting | TrOCR (`trocr-small-handwritten`) re-reads HANDWRITTEN lines, and UNKNOWN lines where PaddleOCR is less than 90% sure. Its reading replaces PaddleOCR's only if it is at least 50% confident and at least as confident as PaddleOCR. About 25 s per handwritten page on 2 CPU cores |
| Director instructions | `backend/ocr_adapter.py` looks at the handwritten lines and scores them for instruction words ("put up", "discuss", "for action", "see me", …). It ignores address lines such as "To, The Director". It returns the best line together with the handwritten lines next to it, as `DIRECTOR_HANDWRITTEN_REMARK` / `PRIOR_DIRECTOR_REVIEW_DETECTED`. The result stays unverified until the DS confirms it. A printed letter no longer triggers a false instruction |
| Entities | spaCy `en_core_web_sm` 3.8.0 with a whitelist of useful labels and a plausibility filter. Dates are no longer invented from the current day |
| Fields | `backend/ocr_adapter.py` maps OCR_new fields to CDTRS fields and does not duplicate entity labels that are already mapped |

## 4. One-time setup on a new server

```
cd /d C:\CDTRS-main\OCR_new
python setup_models.py --check
python fineTune\download_base_model.py
```

The first command checks that the PaddleOCR models are present. The second downloads
the handwriting model (about 250 MB; internet is needed only this once).

Then restart the backend. Without the handwriting model, everything works, but
handwriting is read by PaddleOCR only.

## 5. Improving accuracy on your documents

Follow **[OCR_new/fineTune/README.md](OCR_new/fineTune/README.md)**:

1. Put scans or PDFs of your handwriting in `fineTune\datasets\raw\`.
2. Run `prepare_dataset.py` to cut them into lines.
3. Label the lines with `label_tool.py`.
4. Run `train.py --task handwriting`.
5. Run `evaluate.py`.
6. Restart the backend.

A new model is activated only if it reads the held-back test lines better than the
current one. `set_active_model.py` rolls back.

## 6. Where to look when something is wrong

| Symptom | Look at |
|---|---|
| Backend window closes during the first OCR / WebSocket closed | DLL import order (section 1); the `[STARTUP]` lines in the backend window |
| OCR very slow the first time | Warm-up still running (20–60 s after start) |
| Wrong department suggested | The department's description and keywords in Admin → Department Configuration |
| Handwriting not re-read | `models\handwriting\active.txt`, `handwriting.enabled` in `OCR_new\config\config.yaml`, and `OCR_new\output\ocr_system.log` |
| Printed lines treated as handwritten | Train the text-type classifier (`train.py --task text_type`) |
| Memory errors | The `paddleocr:` memory settings in `config.yaml`; do not raise `text_det_limit_side_len` |

Tests: `cd OCR_new` and `python -m unittest discover -s testing -t . -v`. See also
[OCR_new/README.md](OCR_new/README.md).
