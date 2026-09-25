# OCR_new: Offline OCR and Document Intelligence Engine

OCR_new reads scanned letters, forms, PDFs and photos, including pages with
handwritten notes, and turns them into structured results: the text of every line
with its position and confidence, whether each line is printed or handwritten, a
document category, named entities (people, dates, amounts, ...), regex fields and
semantic information.

It runs **fully offline**. All models are stored on the PC, and nothing is
downloaded while documents are processed.

The engine has two uses:

- **Inside CDTRS.** The backend calls it through `backend/ocr_adapter.py` and
  `backend/intelligence.py` (section 2).
- **Standalone.** You can use it through the command line (`main.py`), the Python
  API (`DocumentProcessor`) or a local REST API (`api/app.py`) (section 4).

Contents

1. What it does
2. How CDTRS uses it
3. Installation and models
4. Running it standalone
5. Configuration reference (`config/config.yaml`)
6. Printed/handwritten detection and handwriting recognition
7. Improving accuracy (fine-tuning)
8. Tests
9. Folder structure
10. Troubleshooting

---

## 1. What it does

### 1.1 Pipeline

`DocumentProcessor.process()` in `document_intelligence.py` runs these steps in this
order. Square brackets show the modes that run a step. CDTRS always uses `full`.

```
input file (PDF, image, multi-page TIFF, DOCX, TXT)
  |
  v
1. Load              document/            detect the file type; render PDF pages at 300 DPI;
  |                                       read image frames; read DOCX text and embedded images
  v
2. Preprocess        preprocessing/       optional clean-up of each page (every step is off by default)
  |
  v
3. PaddleOCR         ocr/paddle_engine.py find the text lines -> turn upside-down lines round
  |                                       -> read each line; drop lines below drop_score;
  |                                       sort top-to-bottom, left-to-right
  v
4. Layout            layout/              page regions (HEADER, TITLE, PARAGRAPH, ...)        [full]
  |                                       from the page image; does not change the OCR text
  v
5. Printed or        ocr/text_type_detector.py
   handwritten                            PRINTED / HANDWRITTEN / UNKNOWN for every line      [full]
  |
  v
6. TrOCR re-read     ocr/handwriting_engine.py
  |                                       handwritten (and unsure) lines are read again; the
  |                                       TrOCR reading replaces PaddleOCR's when it is more
  |                                       confident                                           [full]
  v
7. Classification    classification/      keyword rules, or your trained classifier   [classify, full]
  |
  v
8. Extraction        nlp/, extraction/    spaCy entities + regex entities + regex fields
  |                                       from extraction/patterns.yaml                [extract, full]
  v
9. Semantic          semantic/            sentence embedding, TF-IDF keywords, semantic category,
  |                                       similarity to reference texts            [understand, full]
  v
DocumentResult  ->  (optional) output/<file name>/result.json, ocr.txt, ...
```

Steps 1 to 3 always run. In step 7, a trained classifier
(`models/classifiers/document/`) replaces the keyword-rule result when it is at least
`classification.min_model_confidence` (0.6) sure and at least as sure as the rules.
If the category is still UNKNOWN (or step 7 did not run), step 9 uses its semantic
category instead.

### 1.2 Supported input

| Type | Extensions | How it is read |
|---|---|---|
| PDF | `.pdf` | Every page is rendered to an image (`pdf.dpi`, 300) and OCR'd, including digital PDFs; a PDF's text layer is not used. Renderers in order: pypdfium2, then PyMuPDF (also used when a page renders blank), then pdf2image/Poppler |
| Images | `.png .jpg .jpeg .tif .tiff .bmp .webp` | Each TIFF frame is one page |
| Word | `.docx` | Paragraph text is taken as it is (confidence 1.0, `"source": "native_text"`). Embedded images are OCR'd as extra pages numbered 1001, 1002, ... |
| Text | `.txt` | Each line becomes a region (`"source": "plain_text"`) |

A file without a known extension is recognised by its first bytes (PDF, ZIP/DOCX,
JPEG, PNG, TIFF) or its MIME type.

### 1.3 Main components and versions

| Job | Component |
|---|---|
| Text detection and reading | PaddleOCR 2.8.1 on paddlepaddle 2.6.2 (CPU). Models: en_PP-OCRv3_det, en_PP-OCRv4_rec, ch_ppocr_mobile_v2.0_cls |
| Printed/handwritten | 20 line-shape features, built-in logistic model, or a classifier you trained |
| Handwriting reading | Microsoft TrOCR `trocr-small-handwritten` through transformers 5.15.0 and torch 2.13.0 (CPU) |
| Entities | spaCy 3.8.14 with `en_core_web_sm` 3.8.0, plus regex patterns |
| Embeddings | sentence-transformers 5.6.1 with `all-MiniLM-L6-v2` (384 numbers per text) |
| Keywords, trained classifiers | scikit-learn 1.9.0 (TF-IDF, Logistic Regression, Random Forest) |
| Page orientation | OpenCV heuristic (`preprocessing.auto_rotate`, off by default); upside-down lines are handled by PaddleOCR's line classifier |

---

## 2. How CDTRS uses it

- **One shared engine.** `backend/ocr_adapter.py` puts `OCR_new` on `sys.path` and
  creates one `DocumentProcessor`, which reads `OCR_new/config/config.yaml` once. It
  always calls `process(file, mode="full")`. The backend receives the text, the
  average line confidence, the extracted fields, the page count, the file type and
  `is_handwritten`, which is true when more lines are HANDWRITTEN than PRINTED. The
  adapter also looks through the HANDWRITTEN lines for a Director instruction and
  stores it as the fields `director_handwritten_remark` and
  `prior_director_review_detected`.
- **Text without OCR.** `extract_text_fields(text)` runs only the entity and regex
  extraction, for example on e-mail bodies or on text the desktop intake already
  read. `rank_references(text, references)` uses the embedding model for the
  department suggestions in `backend/intelligence.py`.
- **Background OCR.** The backend runs OCR in a worker thread
  (`run_in_threadpool`), so the server keeps answering other requests while a
  document is read. Calls into the engine share a lock, so documents are OCR'd one
  at a time. OCR is advisory: when it fails, the error is recorded on the OCR record
  and the document is still registered.
- **Warm-up.** When the backend starts, the thread `ocr-warm-up`
  (`intelligence.warm_up_ocr_engine` -> `ocr_adapter.warm_up()`) loads PaddleOCR, the
  NER and regex extraction and the embedding model. The first OCR is ready about
  20 to 60 seconds after start. The TrOCR handwriting model is loaded during the
  first document.
- **Missing models.** When the PaddleOCR models are missing, OCR_new stops with
  `SystemExit`. The adapter catches this and reports "Run 'python
  OCR_new/setup_models.py' once to install them".
- **Changes need a restart.** After you edit `config.yaml`, switch the handwriting
  model or train a classifier, restart the backend (`start_backend.bat`).
- **Windows DLL order.** On Windows, torch must be loaded before PaddlePaddle, and
  pyarrow/pandas before PaddleOCR. Without this, the backend crashed without an
  error message and the desktop app reported "WebSocket ... remote host closed the
  connection". The code handles the order: `backend/ocr_adapter.py` imports torch
  first, `backend/main.py` imports pyarrow and pandas first, and
  `document_intelligence.py` calls `utils/native_libs.preload()` (torch, pyarrow,
  pandas; Windows only). In your own scripts, import `document_intelligence` before
  anything that imports `paddleocr`.

---

## 3. Installation and models

### 3.1 Python and packages

On the CDTRS PC, Python 3.12 (64-bit) is installed per user at
`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, and all the packages from
`imp.txt` are already installed. **No extra installation is needed.** Use only these
packages. `OCR_new/requirements.txt` pins the same versions as `imp.txt`.

| Package | Version | Used for |
|---|---|---|
| paddlepaddle / paddleocr | 2.6.2 / 2.8.1 | Text detection and reading |
| torch / torchvision | 2.13.0 / 0.28.0 | TrOCR |
| transformers / sentencepiece | 5.15.0 / 0.2.2 | TrOCR model and tokenizer |
| huggingface_hub | 1.27.0 | One-time TrOCR download only |
| sentence-transformers | 5.6.1 | Embeddings |
| spacy / en_core_web_sm | 3.8.14 / 3.8.0 | Named entities (`en_core_web_sm` comes from `imp.txt`; it is not in `requirements.txt`) |
| scikit-learn | 1.9.0 | TF-IDF keywords, trained classifiers |
| opencv-python / Pillow / numpy | 4.10.0.84 / 10.4.0 / 1.26.4 | Images |
| pypdfium2 / PyMuPDF / pdf2image | 4.30.0 / 1.24.9 / 1.17.0 | PDF rendering |
| python-docx | 1.2.0 | DOCX |
| python-dateutil | 2.9.0.post0 | Date normalisation of entities |
| PyYAML | 6.0.2 | Configuration |
| fastapi / uvicorn / pydantic | 0.111.0 / 0.30.1 / 2.8.2 | Local REST API |
| editdistance, PySide6 | 0.8.0, 6.7.2 | Fine-tuning (error rates, label tool) |

To set up another PC, install the same versions (`python -m pip install -r
requirements.txt` from `OCR_new`, which needs internet). Paddle supports Python up to
3.12.

### 3.2 Models

| Model | Folder | Size | In git | What to do |
|---|---|---|---|---|
| PaddleOCR detection / recognition / line orientation | `models\paddleocr\det`, `rec`, `cls` (+ `model_info.json`) | about 16 MB | yes | Nothing. Check them with `python setup_models.py --check` |
| TrOCR handwriting | `models\handwriting\trocr-small-handwritten\` + `models\handwriting\active.txt` | about 250 MB | no | Download it once: `python fineTune\download_base_model.py` |
| spaCy `en_core_web_sm` | installed Python package | - | - | Nothing (from `imp.txt`) |
| Sentence embeddings `all-MiniLM-L6-v2` | `models\embeddings\model\` | about 90 MB | yes | Nothing |
| Your own classifiers (optional) | `models\classifiers\text_type\`, `models\classifiers\document\` | small | no | Made by fine-tuning (section 7) |
| Your own spaCy model (optional) | `models\ner\<folder with meta.json>\` | - | no | Only if you have one |

Run these commands from the `OCR_new` folder (`cd /d C:\CDTRS-main\OCR_new`):

| Command | What it does |
|---|---|
| `python setup_models.py --check` | Shows `[OK]` or `[MISSING]` for DET, REC and CLS |
| `python setup_models.py` | Copies the models again from PaddleOCR's cache (`~\.paddleocr\whl`) |
| `python fineTune\download_base_model.py` | Downloads the TrOCR base model once (needs internet) and makes it active |
| `python fineTune\set_active_model.py` | Lists the handwriting models; `*` marks the active one |
| `python main.py --mode check-offline` | Checks the offline flag, the PaddleOCR models and the patterns file |

- `setup_models.py` without `--check` downloads the PaddleOCR models into
  `~\.paddleocr\whl` first, but only if they are not already there (internet is
  needed only then). It refuses PaddleOCR 3.x.
- `download_base_model.py` has two options: `--model small|base|large` (`small` is
  the default and the recommended model) and `--no-activate`. If the PC has no
  internet, run it on another PC and copy the `models\handwriting\` folder across.
- Without an active handwriting model, handwritten lines keep PaddleOCR's reading.
  Nothing else breaks.
- `check-offline` does not check the handwriting, NER or embedding models.
- If `python` is not recognised, use `py -3.12` instead.

---

## 4. Running it standalone

### 4.1 Command line (`main.py`)

```
cd /d C:\CDTRS-main\OCR_new
python main.py --mode full --input input\test_doc.png
python main.py --mode full --input "C:\scans\letter from HQ.pdf"
```

| Option | Meaning |
|---|---|
| `--mode` (required) | `ocr`, `understand`, `classify`, `extract`, `full`, `patterns` or `check-offline` |
| `--input FILE`, `-i FILE` | The file to process. Required for `ocr`, `understand`, `classify`, `extract` and `full`; optional for `patterns`. A relative path is taken relative to the `OCR_new` folder, not the current folder |
| `--config PATH` | Use another configuration file instead of `config\config.yaml`. A relative `PATH` is taken from the current folder. Relative paths inside the file are still relative to `OCR_new` |

What each mode does:

| Mode | Steps (section 1.1) | Files written to `output\<file name>\` |
|---|---|---|
| `ocr` | 1-3 only, through `OCRPipeline` (no printed/handwritten labels, no TrOCR) | `ocr.txt`, `ocr.json` |
| `understand` | 1-3, 9. The semantic category also becomes the classification | all nine files (see 4.2) |
| `classify` | 1-3, 7 | all nine files |
| `extract` | 1-3, 8 | all nine files |
| `full` | 1-9 | all nine files |
| `patterns` | Only the regex fields of `extraction\patterns.yaml`, on a text file (`--input notes.txt`) or on pasted text (end with an empty line, then Ctrl+Z and Enter) | `extracted.json` (only with `--input`) |
| `check-offline` | Reports `[1] Offline mode flag`, `[2] PaddleOCR model dirs`, `[3] Patterns YAML file`; exit code 1 if something is missing | none |

The console shows a summary: pages, number of regions, elapsed time, and the
fields and entities found. Every run is a new Python process, so the models are
loaded again each time. To process many files, use the Python API with one
`DocumentProcessor`.

### 4.2 Output files

The results go to `OCR_new\output\<input file name without extension>\`. A second
run on a file with the same name overwrites them. The modes `understand`,
`classify`, `extract` and `full` (and `DocumentResult.save()`) write:

| File | Contents |
|---|---|
| `result.json` | Everything: `document` (filename, pages, source_type), `classification`, `regions`, `layout`, `text_types`, `entities`, `extracted_fields`, `semantic`, `full_text`, `text`, `ocr`, `metadata` (mode, elapsed_s, region_count, pages_processed) |
| `ocr.txt` | The full text. Regions on one line are joined with spaces, and lines with line breaks |
| `ocr.json` | `{"text", "full_text", "regions"}` |
| `layout.json` | `{"regions": [...]}` with region_id, page, bbox, region_type, confidence, reading_order (`full` only, otherwise `{}`) |
| `text_types.json` | For each line: page, first 40 characters, text_type, confidence, recognizer (`paddleocr` or `handwriting`) (`full` only, otherwise `[]`) |
| `entities.json` | For each entity: text, label, start, end, confidence, normalized_text |
| `extracted.json` | The `extracted_fields` (see below) |
| `classification.json` | label and confidence, plus `method` (RuleClassifier or ModelClassifier) or, when the semantic step set it, `categories` (every category with its similarity) |
| `semantic.json` | enabled, embedding (384 numbers), keywords (top 10 with score), classification, similarities |

In `ocr` mode, `ocr.json` holds `file`, `doc_type`, `pages`, `elapsed_s`,
`processed_at` and `regions`, and the regions have no text type.

One region (line) in `full` mode:

```json
{
  "text": "Please put up the file",
  "confidence": 0.8123,
  "bbox": [412, 1630, 1210, 1702],
  "page": 1,
  "text_type": "HANDWRITTEN",
  "text_type_confidence": 0.91,
  "handwriting_text": "Please put up the file",
  "handwriting_confidence": 0.8123,
  "paddle_text": "Plese put vp the fle",
  "paddle_confidence": 0.61,
  "recognizer": "handwriting"
}
```

`bbox` is `[x1, y1, x2, y2]` in pixels of the page image (a PDF page rendered at
`pdf.dpi`). The fields `handwriting_*` appear on lines that TrOCR read again.
`paddle_*` and `recognizer` appear only when TrOCR's reading replaced PaddleOCR's.

`extracted_fields` combines two sources:

- **Entity lists:** `persons`, `organizations`, `locations`, `dates`, `times`,
  `amounts`, `emails`, `phone_numbers`, `document_ids`, `reference_numbers`.
  These come from spaCy labels PERSON, ORG, GPE, LOC, DATE, TIME and MONEY, after an
  implausibility filter, and from regex entities EMAIL, PHONE, DATE, MONEY,
  REFERENCE_NUMBER and DOCUMENT_ID.
- **Regex fields from `extraction\patterns.yaml`:** `subject`, `title`, `name`,
  `roll_no`, `date`, `semester`, `department`, `marks`, `teacher`, `aim`,
  `experiment_no`. The first matching pattern wins, and a field whose name is
  already present is not overwritten.

### 4.3 Python API (`DocumentProcessor`)

```python
import sys
sys.path.insert(0, r"C:\CDTRS-main\OCR_new")   # not needed when the script runs in OCR_new

from document_intelligence import DocumentProcessor   # import this before paddleocr (Windows DLL order)

processor = DocumentProcessor()          # reads OCR_new\config\config.yaml
# DocumentProcessor(config={...}) or DocumentProcessor(config_path="...") also work

result = processor.process(r"C:\scans\letter.pdf", mode="full")   # ocr|understand|classify|extract|full

print(result.document_type)      # classification label, or the file type when there is none
print(result.text)               # same as result.full_text
print(result.pages, result.source_type)
for r in result.regions:
    print(r["page"], r.get("text_type"), r["confidence"], r["text"])
print(result.entities)
print(result.extracted_fields)
print(result.classification)     # {"label": ..., "confidence": ..., ...}

data = result.to_dict()          # same structure as result.json
written = result.save()          # OCR_new\output\letter\...; save(output_dir="D:\\results") for another folder
```

- Models load the first time they are needed and are then reused. Create one
  `DocumentProcessor` and use it for every file.
- `process()` raises `FileNotFoundError` for a missing file. When the PaddleOCR
  models are missing, it raises `SystemExit`, so catch it in a long-running program
  (as the CDTRS adapter does).
- The processor is not thread-safe. Serialise calls, for example with a lock.
- Semantic similarity: `processor.process(path, mode="understand",
  reference_texts=["...", "..."])` fills `result.semantic["similarities"]` with
  `{"reference": <first 80 characters>, "similarity": <cosine>}`.

OCR only, without the rest of the pipeline (run from `OCR_new`):

```python
import yaml
from ocr.paddle_engine import PaddleEngine
from ocr.ocr_pipeline import OCRPipeline

config = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
engine = PaddleEngine()
engine.initialize(config)
out = OCRPipeline(engine, config).process("input/test_doc.png")
# out: file, doc_type, pages, regions, full_text, elapsed_s
```

### 4.4 Local REST API (`api/app.py`)

A small FastAPI service lets programs that are not written in Python use the engine.
Start it from `OCR_new` with uvicorn. **Do not use port 8000 while the CDTRS
backend is running.** The backend uses that port by default (`PORT` in
`backend\.env`). Use another port, for example 8010:

```
cd /d C:\CDTRS-main\OCR_new
python -m uvicorn api.app:app --host 127.0.0.1 --port 8010
```

The API always reads `config\config.yaml`. `/ocr` and `/process` use one shared
`DocumentProcessor`, which is the same pipeline as the command line and CDTRS
(including layout, printed/handwritten detection, TrOCR, the trained classifier and
the patterns.yaml fields). The models load during the first request and are then
reused.

| Endpoint | Body | Returns |
|---|---|---|
| `GET /health` | - | `status` (`READY`, or `DEGRADED` when something is missing), `offline_mode`, `models_available`: `{"paddleocr": true/false, "patterns_file": true/false}` |
| `POST /process` | `{"file_path": "C:\\scans\\a.pdf", "mode": "full", "config_overrides": {...}}` (`mode` and `config_overrides` are optional; `mode` is `ocr`, `understand`, `classify`, `extract` or `full`, default `full`) | The same structure as `result.json` (section 4.2), with `metadata.api_elapsed_s` added |
| `POST /ocr` | `{"file_path": "C:\\scans\\a.pdf"}` | Same as `/process` with mode `ocr` (steps 1-3). A `language` field is accepted but ignored; the language comes from `config.yaml` |
| `POST /classify` | `{"text": "..."}` | Keyword-rule classification of the text: label, confidence, method |
| `POST /extract` | `{"text": "..."}` | `entities` and the entity `extracted_fields` of the text (no patterns.yaml fields) |
| `GET /docs`, `GET /redoc` | - | Interactive API documentation |

- `file_path` is a path on the PC that runs the API. A relative path is resolved
  from the folder where uvicorn was started. Nothing is written to `output\`; the
  result is only returned.
- Status codes: 404 when the file does not exist, 422 for an unknown `mode` or an
  invalid body, and 500 when processing fails (the message is in `detail`).
- `config_overrides` replaces whole top-level sections of the configuration, for
  example `{"handwriting": {"enabled": false}}`. A request with overrides gets its
  own `DocumentProcessor`, so its models are loaded again, which is slow.
- Requests are handled one document at a time (a lock around the shared processor); others wait their turn.
- CORS allows only `http://localhost` and `http://127.0.0.1`.

---

## 5. Configuration reference (`config/config.yaml`)

The engine reads `OCR_new\config\config.yaml` when a `DocumentProcessor`, the CLI
or the API starts. The CLI can use another file with `--config`. Relative paths in
the file are relative to `OCR_new`. After a change, restart the CDTRS backend (or
the local API).

### `offline_mode`

| Key | Value | Meaning |
|---|---|---|
| `offline_mode` | `true` | Keep `true`. Only `check-offline` reads it, and reports "NOT ready" when it is false |

### `paths`

| Key | Value | Meaning |
|---|---|---|
| `output_dir` | `output` | Output root for the CLI modes `ocr` and `patterns`. The other modes and `DocumentResult.save()` always write to `OCR_new\output` |
| `temp_dir` | `temp` | Page images of the pdf2image (Poppler) fallback |
| `patterns_file` | `extraction/patterns.yaml` | The regex field definitions |
| `models_dir`, `input_dir` | | Not used by the pipeline |

### `paddleocr`

| Key | Value | Meaning |
|---|---|---|
| `lang` | `en` | Language of the models and character set. Another language needs other models: run `setup_models.py` again (internet) |
| `ocr_version` | `PP-OCRv4` | PaddleOCR 2.x model family (PP-OCR to PP-OCRv4). For `en` this means PP-OCRv3 detection and PP-OCRv4 recognition. `setup_models.py` also uses it |
| `use_gpu` | `false` | The installed paddlepaddle is CPU-only |
| `use_textline_orientation` | `true` | Runs the `cls` model, which turns upside-down (180 degree) lines round |
| `text_det_limit_side_len` | `1920` | Pages are scaled so the longest side is at most this. A lower value uses less memory and is faster, but small text may be missed |
| `text_det_limit_type` | `max` | Applies the limit to the longest side |
| `text_det_thresh` | `0.2` | Pixel threshold for text. Lower keeps fainter strokes |
| `text_det_box_thresh` | `0.4` | Minimum score of a text box. Lower keeps fainter lines, and also more false boxes |
| `text_det_unclip_ratio` | `1.6` | Margin around each box. 1.8 merged neighbouring lines |
| `det_model_dir`, `rec_model_dir`, `cls_model_dir` | `models/paddleocr/det` ... | The local model folders. If a folder has no model files, PaddleOCR's own cache (`~\.paddleocr`) is used |
| `drop_score` | `0.25` | Lines read with a lower confidence are dropped |

**Memory settings.** Paddle keeps working memory for every input shape it has seen
and never frees it. These settings limit the number of shapes. One A4 page used to
need more than 6 GB; now the peak is about 3 GB. Leave them as they are.

| Key | Value | Meaning |
|---|---|---|
| `det_square_pad` | `true` | Pads each page with white (right and bottom) to one of three square sizes: 1/3, 2/3 or all of `text_det_limit_side_len` (640, 1280 or 1920 px). Coordinates do not change |
| `rec_batch_num` | `1` | Reads text lines one at a time |
| `rec_ratio_step` | `8` | Line images are widened to a multiple of 8 x line height (0 turns this off) |
| `rec_max_ratio` | `32` | Lines longer than 32 x height are narrowed to fit |

### `text_type_detection`

| Key | Value | Meaning |
|---|---|---|
| `enabled` | `true` | Printed/handwritten detection (`full` mode). When `false`, TrOCR re-reading is skipped too |
| `model_path` | `models/classifiers/text_type` | When `classifier.pkl` is here (fine-tuning, `--task text_type`), it is used; otherwise the built-in model |

### `handwriting`

| Key | Value | Meaning |
|---|---|---|
| `enabled` | `true` | Re-reading with TrOCR on or off |
| `model_path` | `models/handwriting` | Folder of handwriting models. `active.txt` names the one in use. If this folder itself holds a model, that model is used |
| `device` | `cpu` | torch device. The installed torch is the CPU build |
| `num_beams` | `3` | Beam search width. 1 is faster |
| `max_new_tokens` | `64` | Maximum tokens generated for one line |
| `replace_below_confidence` | `0.9` | UNKNOWN lines with a lower PaddleOCR confidence are re-read too |
| `min_confidence` | `0.5` | TrOCR's reading replaces PaddleOCR's only when it is at least this confident and at least as confident as PaddleOCR |
| `max_lines_per_page` | `80` | At most this many lines are re-read on one page (the first in reading order) |

### `classification`

| Key | Value | Meaning |
|---|---|---|
| `model_path` | `models/classifiers/document` | Optional trained classifier: `classifier.pkl`, `vectorizer.pkl`, `label_encoder.pkl` |
| `min_model_confidence` | `0.6` | The trained classifier's label is used when it is not UNKNOWN, reaches this confidence and is at least as confident as the keyword rules |

Without a trained classifier, the keyword rules in `classification/rule_classifier.py`
are used. They know INVOICE, LEAVE_APPLICATION, TECHNICAL_REPORT, LETTER, CONTRACT
and RESUME. Confidence = matched keywords / (0.3 x keywords of that category), with
a maximum of 1. The semantic step compares the text with eight built-in category
descriptions: TECHNICAL_REPORT, INVOICE, LEAVE_APPLICATION, LETTER, FORM, CONTRACT,
RESUME and GENERAL.

### `ner`

| Key | Value | Meaning |
|---|---|---|
| `enabled` | `true` | `false`: spaCy is not loaded, and only the regex entity patterns run |
| `model_path` | `models/ner` | spaCy model folders (with `meta.json`) here are tried first |
| `package` | `en_core_web_sm` | The installed spaCy package, tried next |
| `backend` | `spacy` | `regex`: never use spaCy |

### `preprocessing`

| Key | Value | Meaning |
|---|---|---|
| `enabled` | `true` | Main switch for the steps below |
| `grayscale` | `false` | Convert to grey |
| `denoise` | `false` | Non-local-means denoising (slow on large pages) |
| `contrast_enhance` | `false` | CLAHE contrast enhancement |
| `threshold` | `false` | Binarise the page. This can remove faint handwriting strokes |
| `threshold_method` | `adaptive` | `adaptive` or `otsu` |
| `deskew` | `false` | Hough-line skew correction. Keep `false` for handwriting: slanted strokes look like skew |
| `auto_rotate` | `false` | 90/180/270 degree page rotation by a projection heuristic. Keep `false`: it can flip handwritten pages. PaddleOCR's line classifier already turns upside-down lines round |
| `border_removal` | `false` | Crops a 10 px border |
| `upscale_factor` | `1.0` | Values above 1 enlarge the page before OCR |
| `pdf_render_dpi` | `300` | Used only when `pdf.dpi` is missing |

Preprocessing changes only the image that PaddleOCR reads. The printed/handwritten
detector and TrOCR cut the lines out of the **unprocessed** page, using PaddleOCR's
coordinates. Steps that move or resize the page (`upscale_factor`, `auto_rotate`,
`deskew`, `border_removal`) therefore give them the wrong crops.

### `pdf`

| Key | Value | Meaning |
|---|---|---|
| `dpi` | `300` | Render resolution of PDF pages. Lower uses less memory and is faster |
| `page_image_format` | `PNG` | pdf2image fallback only |
| `keep_temp_pages` | `false` | pdf2image fallback only: keep the page images in `temp\` |

### `docx`

| Key | Value | Meaning |
|---|---|---|
| `extract_embedded_images` | `true` | OCR the images embedded in a DOCX. Paragraph text is always read directly |

### `output`

| Key | Value | Meaning |
|---|---|---|
| `json_indent` | `2` | JSON indentation for the CLI modes `ocr` and `patterns` (the other result files always use 2) |
| `save_txt`, `save_json`, `save_region_crops` | | Not used by the current code. Text and JSON are always written, and region crops never are |

### `logging`

| Key | Value | Meaning |
|---|---|---|
| `level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `log_to_file` | `true` | Also write a log file |
| `log_dir`, `log_file` | `output`, `ocr_system.log` | The file is `OCR_new\output\ocr_system.log`, whatever the current folder |
| `max_bytes`, `backup_count` | `5242880`, `3` | Rotates at 5 MB and keeps 3 old files |

Logging is set up once per process. If the program already configured Python's
root logger, OCR_new does not add its own handlers.

### Optional keys (read by the code, not in the file)

| Key | Default | Meaning |
|---|---|---|
| `semantic.enabled` | `true` | `false` skips the semantic step |
| `semantic.embedding_model` | `models/embeddings/model` | Embedding model folder |
| `classification.rules_file` | `config/classification_rules.yaml` (does not exist, so the built-in rules are used) | YAML with `rules:` entries of the form `- label: X` / `keywords: [...]` |
| `classification.categories_file` | none | YAML with `categories:` entries of the form `- label: X` / `description: ...` for the semantic category |
| `pdf.poppler_path` | none | Poppler `bin` folder for the pdf2image fallback |

Like the other paths, relative `rules_file` and `categories_file` paths are relative
to `OCR_new`.

---

## 6. Printed/handwritten detection and handwriting recognition

Both run only in `full` mode (which is what CDTRS uses), after PaddleOCR has read
every line.

### 6.1 Printed or handwritten (`ocr/text_type_detector.py`)

For each PaddleOCR line box, the detector:

1. Cuts the line out of the page and scales it to 64 px high. Long horizontal rules
   (underlines, ruled paper) are removed.
2. Measures 20 shape features (`FEATURE_VERSION = 2`). Examples: how uniform the
   glyph heights are, whether glyphs share one baseline and one top line, stroke
   width and how much it varies, how much of each glyph box is ink, how much the
   slant varies, and PaddleOCR's own confidence (print is usually read more
   confidently).
3. Estimates P(handwritten) with:
   - `models/classifiers/text_type/classifier.pkl` when it exists (a Random Forest
     you trained with `fineTune`). A classifier trained on an older feature version
     is ignored, with a warning;
   - otherwise the built-in logistic regression over 12 of the features. It was
     fitted on about 1,900 lines: printed letters, notices and forms (scanned and
     digital, 60+ fonts) and a handwritten notebook.

| Condition | `text_type` | `text_type_confidence` |
|---|---|---|
| P(handwritten) >= 0.70 | HANDWRITTEN | P |
| P(handwritten) <= 0.35 | PRINTED | 1 - P |
| between the two | UNKNOWN | max(P, 1 - P) |
| fewer than 3 glyphs, or the crop is too small | UNKNOWN | 0.0 |

The detector is cautious on purpose: when it is unsure, it answers UNKNOWN. (The
label MIXED exists in the code but is never returned.)

### 6.2 Reading handwriting with TrOCR (`ocr/handwriting_engine.py`)

1. **Which lines.** Lines marked HANDWRITTEN, and UNKNOWN lines that PaddleOCR read
   with confidence below `replace_below_confidence` (0.9). The crop must be at least
   8 x 8 px. At most `max_lines_per_page` (80) lines per page are re-read.
2. **Cleaning.** Each crop is converted to grey, ruled lines are painted out, and
   the crop is trimmed to the band of the line itself. PaddleOCR's boxes often
   include parts of the lines above and below, which makes TrOCR invent text.
3. **Reading.** The active TrOCR model reads the lines in batches of 8, with beam
   search (`num_beams` 3, at most `max_new_tokens` 64). Its confidence is the
   average probability per token.
4. **Decision.** TrOCR's text replaces PaddleOCR's only when it is not empty, its
   confidence is at least `min_confidence` (0.5) **and** at least PaddleOCR's
   confidence. Both readings are kept on the region (`handwriting_text`, and
   `paddle_text` when replaced), `recognizer` becomes `handwriting`, and the full
   text is rebuilt. The log shows `Handwriting model re-read N line(s), replaced M.`

The model in use is the folder named in `models\handwriting\active.txt` (at first
`trocr-small-handwritten`). With no active model, the log shows `No handwriting
model is active; handwritten lines keep PaddleOCR's text.`

### 6.3 Performance

| What | Figure |
|---|---|
| Peak memory for one A4 page (with the memory settings) | about 3 GB (more than 6 GB before) |
| TrOCR re-reading | about 25 s per handwritten page on 2 CPU cores |
| Backend warm-up until the first OCR is possible | about 20 to 60 s after start |

For faster handwriting pages, lower `num_beams` (1) or `max_lines_per_page`. For
less memory, lower `text_det_limit_side_len` or `pdf.dpi`.

---

## 7. Improving accuracy (fine-tuning)

The full guide is **`fineTune\README.md`**. It works offline with the installed
packages. In short:

| What you can train | Command | Result |
|---|---|---|
| Handwriting reading (TrOCR), the most useful | `python fineTune\training\train.py --task handwriting` | `models\handwriting\v1`, `v2`, ... It is made active only when it reads the test lines better than the previous model and PaddleOCR |
| Printed/handwritten detector | `python fineTune\training\train.py --task text_type` | `models\classifiers\text_type\classifier.pkl`, installed only when it scores at least as well as the built-in model on the test lines |
| Document categories | `python fineTune\training\train.py --task classification` | `models\classifiers\document\` |

The steps: put scans or PDFs in `fineTune\datasets\raw\` -> `prepare_dataset.py`
(cuts them into line images and `datasets\labels.csv`) -> `label_tool.py`
(type the correct text) -> `training\train.py` -> `evaluation\evaluate.py` -> restart
the backend. `set_active_model.py [name | --off]` lists, switches or rolls back the
handwriting model. The double-click helpers `1_prepare_dataset.bat` to
`6_choose_model.bat` in `fineTune\` run the same steps.

PaddleOCR itself is not retrained: its training tools are not part of the installed
`paddleocr` package. Some problems can be fixed in `config.yaml` without training:

| Problem | Setting to try |
|---|---|
| Faint handwriting is not found | Lower `paddleocr.text_det_thresh` / `text_det_box_thresh` |
| Two lines are merged into one box | Lower `paddleocr.text_det_unclip_ratio` |
| Too many junk lines | Raise `paddleocr.drop_score` |
| Wrong TrOCR readings replace good ones | Raise `handwriting.min_confidence` |
| Handwritten lines are marked PRINTED (so they are not re-read) | Train the printed/handwritten detector |

---

## 8. Tests

The tests use the standard library's `unittest` (130 tests):

```
cd /d C:\CDTRS-main\OCR_new
python -m unittest discover -s testing -t . -v
```

One file only:

```
python -m unittest testing.test_text_type -v
```

| File | Covers |
|---|---|
| `test_document.py` | File type detection, document normalisation |
| `test_preprocessing.py` | Deskew, denoise, threshold, orientation helpers |
| `test_ocr.py` | Offline checker, preprocessor, PaddleOCR engine, OCR pipeline. The PaddleOCR tests are skipped when the models are missing |
| `test_text_type.py` | Printed/handwritten detector and trained classifier loading |
| `test_handwriting.py` | Handwriting engine (no model needed) |
| `test_semantic.py` | Cosine similarity, ranking, TF-IDF keywords (no model needed) |
| `test_classification.py` | Keyword-rule classifier |
| `test_extraction.py` | NER engine, text cleaner, entity normaliser, entity extractor |
| `test_patterns.py` | patterns.yaml loading and regex extraction |
| `test_document_intelligence.py` | `DocumentProcessor` and `DocumentResult` |
| `test_finetune.py` | Fine-tuning helpers (labels, splits, scores, line preparation) |

---

## 9. Folder structure

```
OCR_new/
├── main.py                     command line (section 4.1)
├── document_intelligence.py    DocumentProcessor / DocumentResult (Python API)
├── setup_models.py             check or re-copy the PaddleOCR models
├── requirements.txt            pinned packages (same versions as imp.txt)
├── README.md                   this file
├── config/config.yaml          all settings (section 5)
├── api/                        app.py (local REST API), schemas.py
├── document/                   file_detector, pdf_processor, docx_processor,
│                               image_processor, document_normalizer
├── preprocessing/              image_preprocessor.py (used by the pipeline);
│                               deskew.py, denoise.py, threshold.py, orientation.py (helpers)
├── ocr/                        paddle_engine, text_type_detector, handwriting_engine,
│                               ocr_pipeline, base_engine, result_merger (not used by the pipeline)
├── layout/                     layout_analyzer, region_detector (contour heuristic), reading_order
├── classification/             rule_classifier, model_classifier, base_classifier,
│                               semantic_classifier (not used by the pipeline)
├── nlp/                        ner_engine, entity_normalizer, text_cleaner
├── extraction/                 entity_extractor, regex_engine, pattern_manager, patterns.yaml,
│                               semantic_extractor (not used by the pipeline)
├── semantic/                   embedding_engine, semantic_pipeline, document_classifier,
│                               keyword_extractor, semantic_similarity
├── output/                     json_writer, text_writer, output_writer;
│                               results (<file name>/...) and ocr_system.log
├── utils/                      logger, native_libs (Windows DLL order), offline_checker,
│                               model_manager (not used by the pipeline)
├── models/
│   ├── paddleocr/              det/, rec/, cls/, model_info.json      (in git)
│   ├── handwriting/            trocr-small-handwritten/, v1/ ..., active.txt   (not in git)
│   ├── embeddings/model/       all-MiniLM-L6-v2                         (in git)
│   ├── ner/                    optional spaCy model folders (README only)
│   ├── classifiers/            text_type/, document/ once trained       (not in git)
│   └── layout/                 README only; no layout model is used
├── fineTune/                   fine-tuning (see fineTune/README.md)
│   ├── 1_prepare_dataset.bat ... 6_choose_model.bat
│   ├── download_base_model.py, prepare_dataset.py, label_tool.py, set_active_model.py,
│   │   common.py, tee.py
│   ├── configs/                handwriting.yaml, text_type.yaml, classification.yaml
│   ├── datasets/               raw/, lines/, classification/ (contents not in git)
│   ├── training/train.py
│   └── evaluation/evaluate.py
├── testing/                    unittest tests (section 8)
├── training/                   README.md only: training moved to fineTune/
├── input/                      test_doc.png (sample input)
└── temp/                       pdf2image temp folder; old experiment scripts and sample images
```

Each model folder has a `README.md` with more detail.

---

## 10. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `ERROR: PaddleOCR model files not found locally`, or `[MISSING]` from `setup_models.py --check` | `models\paddleocr\det`, `rec` or `cls` is empty. The models are tracked in git, so restore them from the repository, or run `python setup_models.py` (internet is needed if `~\.paddleocr` has no copy) |
| The first document takes long | Models load when they are first needed. In CDTRS, warm-up takes about 20 to 60 s after the backend starts, and TrOCR loads with the first document. Each CLI run loads everything again; use the Python API for batches |
| Out of memory, the PC becomes very slow, or the backend process disappears during OCR | Keep the memory settings (`det_square_pad: true`, `rec_batch_num: 1`, `rec_ratio_step: 8`, `rec_max_ratio: 32`). Lower `text_det_limit_side_len` (for example 1280) or `pdf.dpi` (for example 200). Do not run the CLI or API on the same small PC while the backend is doing OCR, because each process loads its own models. Paddle memory is released only when the process ends, so restarting the backend frees it |
| Handwriting is still read badly, or `recognizer` is never `handwriting` | Check the log for `No handwriting model is active`. Run `python fineTune\set_active_model.py`, and if no model is listed, `python fineTune\download_base_model.py`. Check that `handwriting.enabled` and `text_type_detection.enabled` are `true` and that the mode is `full`. In `text_types.json`, lines marked PRINTED are not re-read (train the detector). Lines where TrOCR was less confident keep PaddleOCR's text; see `handwriting_text` in `result.json`. Restart the backend after any change |
| `active.txt names 'x', which is not a model folder` | Choose an installed model with `python fineTune\set_active_model.py <name>` |
| `Text-type classifier ... was trained with older features` | Retrain it: `python fineTune\training\train.py --task text_type`. Until then, the built-in model is used |
| Windows: `torch` fails to load (DLL error), or the backend closes without an error and the app says "remote host closed the connection" | DLL load order (section 2). Start the backend with `start_backend.bat`. In your own scripts, import `document_intelligence` before `paddleocr`. Use the 64-bit Python 3.12 |
| Only regex entities are found (log: `NER engine using regex fallback backend` or `NER engine is DISABLED in config`) | `en_core_web_sm` cannot be loaded, or `ner.enabled` is `false` or `ner.backend` is `regex`. Test with `python -c "import spacy; spacy.load('en_core_web_sm')"` |
| `semantic.json` has `"embedding": null` or an error | `models\embeddings\model\` is missing or incomplete. Restore it from git |
| Handwritten pages come out rotated or garbled | Keep `preprocessing.deskew` and `auto_rotate` `false` (section 5) |
| `[ERROR] Input file not found` with a relative path | CLI paths are relative to `OCR_new`. Use a full path in quotes |
| `[ERROR] Configuration file not found` | The `--config` path is wrong. A relative path is taken from the current folder |
| A PDF page gives no text (log: `remains blank after fallbacks`) | The page is empty or could not be rendered. Scan it again, or convert it to an image |
| The local API does not start, or `/health` is `DEGRADED` | Port already in use: pick a free port (not the backend's 8000). `DEGRADED`: see `models_available`; `paddleocr: false` means the PaddleOCR models are missing (first row) |
| Where are the logs? | `OCR_new\output\ocr_system.log` (and the backend console) |
