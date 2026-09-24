# Offline OCR & Document Intelligence Engine

A modular, reusable, and **100% offline OCR and Document Intelligence Engine** designed to process real-world documents containing **printed text, digitally generated text, scanned text, handwritten text, and mixed handwritten + printed content**.

The system is designed to function independently as a complete document-processing application while also being reusable as a **standalone Python module, SDK, or local service** inside other applications.

The goal is not only to extract text, but to understand the **content, structure, text type, semantic meaning, document category, and important information** present in a document.

The system also provides a dedicated **offline fine-tuning framework** so that OCR, handwriting recognition, text-type detection, classification, and other components can be improved using locally collected and annotated data.

---

## Quick Start: Independent Usage & Application Integration

### 1. How to Run the OCR Independently (CLI)

The engine can run standalone directly from your terminal with zero external dependencies or internet connection:

#### Check Offline Readiness
```bash
python main.py --mode check-offline
```

#### Run the Complete Pipeline (OCR + Layout + Text-Type + Extraction + Classification)
```bash
python main.py --mode full --input input/document.pdf
```
*Outputs generated in `output/<filename>/`:*
- `result.json` — Consolidated standardized JSON summary
- `ocr.txt` — Plain extracted text
- `ocr.json` — Per-region text, bounding boxes, and confidence
- `layout.json` — Layout regions and logical reading order
- `text_types.json` — Handwritten vs. printed classification
- `entities.json` — Named entities (Dates, Names, Phone numbers, etc.)
- `extracted.json` — Structured key-value fields
- `classification.json` — Document category and confidence
- `semantic.json` — Semantic categories and top keywords

#### Run Specific Modular Modes
```bash
# OCR text & bounding boxes only:
python main.py --mode ocr --input input/document.pdf

# Semantic analysis & keyword extraction:
python main.py --mode understand --input input/document.pdf

# Document classification only:
python main.py --mode classify --input input/document.pdf

# Entity and structured field extraction:
python main.py --mode extract --input input/document.pdf
```

---

### 2. How to Use the OCR in Different Applications

The engine is completely application-agnostic and can be integrated into external Python code, backend servers, or microservices:

#### Option A: High-Level Python SDK (`document_intelligence`)
Use the clean, object-oriented SDK inside your Python application:

```python
from document_intelligence import DocumentProcessor

# Initialize the offline processor
processor = DocumentProcessor()

# Process any supported document (PDF, PNG, JPG, TIFF, DOCX)
result = processor.process("input/document.pdf")

# Access structured document intelligence
print("Document Type   :", result.document_type)
print("Extracted Text  :", result.text)
print("Named Entities  :", result.entities)
print("Extracted Fields:", result.extracted_fields)
print("Classification  :", result.classification)
print("Regions Found   :", len(result.regions))

# Export to standardized dictionary or save all result files
data_dict = result.to_dict()
result.save(output_dir="output/")
```

#### Option B: Low-Level OCR Engine Integration (`ocr`)
If your application only requires OCR text and bounding boxes without high-level intelligence:

```python
from ocr.paddle_engine import PaddleEngine
from ocr.ocr_pipeline import OCRPipeline

# Initialize OCR engine
engine = PaddleEngine()
engine.initialize({})

# Process document
pipeline = OCRPipeline(engine, config={})
ocr_result = pipeline.process("input/document.pdf")

for region in ocr_result["regions"]:
    print(f"[{region['confidence']:.2f}] (Page {region['page']}) {region['text']} -> {region['bbox']}")
```

#### Option C: Local Microservice REST API (For Non-Python Applications)
For Node.js, Go, Java, C#, or web applications, run the local FastAPI service on `localhost`:

```bash
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Send local HTTP requests from any programming language:
- **Full Pipeline**: `POST http://127.0.0.1:8000/process` with body `{"file_path": "input/document.pdf"}`
- **OCR Only**: `POST http://127.0.0.1:8000/ocr` with body `{"file_path": "input/document.pdf"}`
- **Classification**: `POST http://127.0.0.1:8000/classify` with body `{"text": "your document text"}`
- **Health Check**: `GET http://127.0.0.1:8000/health`

---

# 1. Purpose

Traditional OCR systems primarily answer:

> "What characters are present in this document?"

This project aims to answer a broader question:

> "What is present in this document, where is it present, what type of text is it, what does the content mean, and what information can be extracted from it?"

For example, a document may contain:

```text
------------------------------------------------
            PROJECT REPORT

Project Name: ABC System

The system was developed to automate
document processing.

Remarks:
Please make the required corrections
and submit the document again.

              [Handwritten Signature]
------------------------------------------------
```

The system should be able to identify:

```text
Document
│
├── Printed Text
│   ├── Project Report
│   ├── Project Name
│   └── Main Content
│
├── Handwritten Text
│   ├── Remarks
│   └── Signature
│
├── Document Structure
│   ├── Header
│   ├── Body
│   └── Remarks Section
│
├── Semantic Meaning
│   └── Project-related report
│
└── Extracted Information
    ├── Project Name
    └── Remarks
```

This information can then be consumed by any external application.

---

# 2. Design Goals

The system is built around the following goals:

### 2.1 Completely Offline

All inference, document processing, semantic analysis, classification, and fine-tuning must happen locally.

After the required models and dependencies are installed:

```text
Internet
   X
   │
   X
OCR Engine
```

The system must not require:

* Cloud OCR APIs
* Cloud AI APIs
* Online embeddings
* Online document processing
* Automatic model downloads
* External telemetry
* Internet access during inference
* Uploading documents to external services

---

### 2.2 Independent

The system must work as a standalone application.

It should not depend on another project or business application.

Example:

```bash
python main.py --mode full --input document.pdf
```

The system should process the document and produce a complete structured result.

---

### 2.3 Reusable

The same engine should be usable by completely different applications.

```text
                 OCR ENGINE
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
   Application A  Application B  Application C
```

The OCR engine should not contain application-specific business logic.

---

### 2.4 Intelligent

The system should go beyond raw OCR by providing:

* Layout understanding
* Handwritten/printed detection
* Semantic understanding
* Entity extraction
* Document classification
* Information extraction
* Confidence scoring
* Structured output

---

### 2.5 Fine-Tunable

The system must provide a dedicated mechanism for improving its models using user-provided data.

Fine-tuning must also be possible **completely offline**.

```text
Local Dataset
     │
     ▼
Local Annotation
     │
     ▼
Offline Training
     │
     ▼
Offline Evaluation
     │
     ▼
Fine-Tuned Model
     │
     ▼
Local Deployment
```

---

# 3. Supported Document Types

The system should support common document formats including:

* JPG
* JPEG
* PNG
* TIFF
* Multi-page TIFF
* PDF
* Scanned PDF
* DOCX
* Fax images
* Fax PDFs
* Photographs of documents

The architecture should allow additional formats to be added later.

---

# 4. Core Capabilities

| Capability              | Description                                           |
| ----------------------- | ----------------------------------------------------- |
| Offline OCR             | Complete local OCR processing                         |
| Printed OCR             | Recognition of printed and typed text                 |
| Scanned OCR             | Recognition of scanned documents                      |
| Handwriting OCR         | Recognition of handwritten content                    |
| Mixed-content OCR       | Handles handwritten + printed content together        |
| Text-type detection     | Determines whether a region is handwritten or printed |
| Layout analysis         | Detects and preserves document structure              |
| Reading order           | Attempts to reconstruct logical reading order         |
| Semantic understanding  | Understands meaning beyond exact keywords             |
| Embeddings              | Generates local semantic representations              |
| Semantic similarity     | Compares document/sentence meaning                    |
| NER                     | Extracts entities from documents                      |
| Classification          | Determines document category                          |
| Information extraction  | Converts unstructured content into structured fields  |
| Confidence scoring      | Provides confidence for important processing stages   |
| Batch processing        | Processes multiple documents                          |
| Structured output       | Produces standardized JSON                            |
| Python integration      | Can be imported into other applications               |
| CLI                     | Can be used independently                             |
| Local API               | Can optionally expose a local service                 |
| Offline fine-tuning     | Supports local model improvement                      |
| Model management        | Stores and loads models locally                       |
| Extensible architecture | New models and processing stages can be added         |

---

# 5. High-Level Architecture

```text
                       DOCUMENT
                          │
                          ▼
                 File Type Detection
                          │
                          ▼
                Document Normalization
                          │
                          ▼
                    Page Extraction
                          │
                          ▼
                  Image Preprocessing
                          │
                          ▼
                    Layout Analysis
                          │
                          ▼
                Text Region Detection
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        Printed Region          Handwritten Region
              │                       │
              ▼                       ▼
        Printed OCR             Handwriting OCR
              │                       │
              └───────────┬───────────┘
                          │
                          ▼
                    Result Merger
                          │
                          ▼
                Text-Type Detection
                          │
                          ▼
                   OCR Result
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
        Semantic         NER        Keywords
       Understanding      │
             │            │
             └────────────┼────────────┘
                          ▼
                  Document Classification
                          │
                          ▼
                  Information Extraction
                          │
                          ▼
                   Confidence Analysis
                          │
                          ▼
                  Structured Result
                          │
                          ▼
                 JSON / Python API
```

---

# 6. Processing Pipeline

## Stage 1 — File Detection

The system identifies the input document using:

* File extension
* MIME type where available
* Magic-byte/file-signature validation

Example:

```text
document.pdf
      ↓
PDF detected
      ↓
PDF processor
```

---

# 7. Document Normalization

Different document formats are converted into a common internal representation.

```text
PDF       ─┐
DOCX      ─┤
PNG       ─┤
JPG       ─┼──► Normalized Document
TIFF      ─┤
FAX       ─┘
```

The normalized representation should preserve:

```text
document
pages
page_number
image
metadata
source_format
```

---

# 8. Image Preprocessing

Real-world scanned documents can contain:

* Noise
* Low contrast
* Rotation
* Skew
* Shadows
* Uneven lighting
* Compression artifacts
* Background patterns

The preprocessing pipeline may include:

* Grayscale conversion
* Denoising
* Contrast enhancement
* CLAHE
* Deskew
* Auto-rotation
* Thresholding
* Adaptive thresholding
* Otsu thresholding
* Border removal
* Perspective correction
* Resolution enhancement

The preprocessing pipeline must remain configurable.

This is especially important for handwriting because aggressive thresholding can sometimes remove important handwriting strokes.

---

# 9. Layout Analysis

The system should understand the spatial structure of a document.

Possible region types include:

```text
HEADER
FOOTER
TITLE
PARAGRAPH
TABLE
FORM
IMAGE
SIGNATURE
HANDWRITTEN_NOTE
STAMP
PAGE_NUMBER
TEXT
UNKNOWN
```

Each detected region should retain information such as:

```json
{
  "region_id": 1,
  "page": 1,
  "bbox": [100, 200, 700, 250],
  "region_type": "paragraph",
  "confidence": 0.94
}
```

---

# 10. Printed and Handwritten Text

A major capability of the system is handling documents containing both printed and handwritten content.

A page may contain:

```text
Printed form
+
Printed paragraphs
+
Handwritten remarks
+
Handwritten corrections
+
Signature
```

Therefore, the entire page should not necessarily be processed using only one recognition model.

The pipeline can use:

```text
                     PAGE
                       │
                       ▼
                Region Detection
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       Printed      Handwritten    Unknown
          │            │            │
          ▼            ▼            ▼
    Printed OCR   Handwriting OCR  Fallback
          │            │            │
          └────────────┼────────────┘
                       ▼
                  Result Merger
```

---

# 11. Text-Type Detection

Each text region should be classified independently where possible.

Possible labels:

```text
PRINTED
HANDWRITTEN
MIXED
UNKNOWN
```

Example:

```json
{
  "text": "Please revise this section.",
  "text_type": "HANDWRITTEN",
  "confidence": 0.91
}
```

This allows downstream applications to know not only **what was written**, but also **how the text appeared in the source document**.

---

# 12. OCR Engine Architecture

OCR engines should implement a common interface.

```text
                    BaseOCREngine
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
      PaddleOCR      Handwriting      Future
                       OCR Engine      Engines
```

Example interface:

```python
class BaseOCREngine:
    def initialize(self, config):
        pass

    def recognize(self, image, page):
        pass
```

The rest of the system should consume standardized OCR results instead of depending directly on a specific OCR implementation.

---

# 13. OCR Result

Every recognized text region should ideally contain:

```text
text
confidence
bounding_box
page
text_type
region_type
reading_order
```

Example:

```json
{
  "text": "Project Completion Report",
  "confidence": 0.97,
  "bbox": [100, 80, 700, 130],
  "page": 1,
  "text_type": "PRINTED",
  "region_type": "TITLE"
}
```

---

# 14. Semantic Understanding

OCR produces text.

Semantic processing attempts to understand the meaning of that text.

For example:

```text
Document A:
"Requesting permission to remain absent for two days."

Document B:
"I will not be attending for the next two days."
```

Exact keyword matching may not identify these as related.

A local semantic model can represent both texts as vectors:

```text
Text A
  │
  ▼
Embedding A ─────┐
                 │
                 ▼
          Semantic Similarity
                 ▲
                 │
Embedding B ─────┘
  ▲
  │
Text B
```

This allows the system to perform:

* Semantic similarity
* Semantic search
* Document matching
* Document classification
* Category matching
* Content grouping
* Similar document retrieval

---

# 15. Sentence Transformers

The semantic layer should support local **Sentence Transformer-compatible embedding models**.

The selected model should be stored locally:

```text
models/
└── embeddings/
    └── model/
```

Example:

```python
embedding = embedding_model.encode(text)
```

The system must load the model from the local filesystem during offline inference.

No online embedding API should be required.

---

# 16. Semantic Classification

Document categories can be represented using semantic embeddings.

Example:

```text
Document
   │
   ▼
Embedding
   │
   ├── Leave Application       0.91
   ├── Technical Report        0.38
   ├── Invoice                 0.21
   └── General Letter          0.62
```

The highest suitable similarity can be used as one signal for classification.

Semantic classification can be combined with traditional machine-learning classification when required.

---

# 17. Named Entity Recognition

The system should support local Named Entity Recognition.

Potential entity types include:

```text
PERSON
ORGANIZATION
LOCATION
DATE
TIME
MONEY
EMAIL
PHONE
PROJECT
DEPARTMENT
DOCUMENT_ID
REFERENCE_NUMBER
```

Example:

```text
"John submitted the ABC project report
to the Engineering Department on 20 September."
```

Possible output:

```json
{
  "entities": [
    {
      "text": "John",
      "label": "PERSON"
    },
    {
      "text": "ABC",
      "label": "PROJECT"
    },
    {
      "text": "Engineering Department",
      "label": "DEPARTMENT"
    },
    {
      "text": "20 September",
      "label": "DATE"
    }
  ]
}
```

---

# 18. Information Extraction

Information extraction combines multiple approaches.

```text
                    OCR Text
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
      Regex           NER         Semantic
                                    Rules
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                Structured Fields
```

The system should support:

### Rule-based extraction

Useful for predictable formats.

### Regex extraction

Useful for:

* Dates
* Email addresses
* Phone numbers
* IDs
* Reference numbers
* Amounts

### NER

Useful for entities whose exact format may vary.

### Semantic extraction

Useful when meaning matters more than exact wording.

---

# 19. Document Classification

The system should support multiple classification strategies.

### Rule-based

```text
IF document contains known patterns
THEN category = X
```

### Keyword-based

```text
invoice
GST
amount
vendor
```

may indicate:

```text
INVOICE
```

### Semantic

```text
Document Embedding
       ↓
Compare with category embeddings
       ↓
Best semantic match
```

### Machine Learning

Locally trained models can also be supported.

Possible algorithms include:

* Logistic Regression
* SVM
* Random Forest
* Gradient Boosting
* Neural Networks
* Transformer-based classifiers

The architecture should allow these approaches to coexist.

---

# 20. Confidence System

Confidence should be maintained throughout the pipeline.

```text
OCR confidence
      +
Text-type confidence
      +
Layout confidence
      +
Entity confidence
      +
Classification confidence
      +
Semantic similarity
```

Example:

```json
{
  "classification": {
    "label": "TECHNICAL_REPORT",
    "confidence": 0.94
  },
  "text_type": {
    "label": "HANDWRITTEN",
    "confidence": 0.88
  }
}
```

Low-confidence results should be explicitly reported.

The system should never silently present uncertain predictions as guaranteed facts.

---

# 21. Standardized Output

The most important integration principle is a standardized result format.

Example:

```json
{
  "document": {
    "filename": "document.pdf",
    "pages": 3,
    "source_type": "PDF"
  },

  "ocr": {
    "text": "...",
    "regions": []
  },

  "layout": {
    "regions": []
  },

  "classification": {
    "label": "TECHNICAL_REPORT",
    "confidence": 0.94
  },

  "entities": [],

  "semantic": {
    "categories": [],
    "similarity": []
  },

  "extracted_fields": {},

  "metadata": {}
}
```

External applications can consume this standardized structure without knowing how the OCR was performed internally.

---

# 22. Independent Application Mode

The system must work as a standalone application.

### OCR only

```bash
python main.py --mode ocr --input input/document.pdf
```

### Semantic understanding

```bash
python main.py --mode understand --input input/document.pdf
```

### Classification

```bash
python main.py --mode classify --input input/document.pdf
```

### Extraction

```bash
python main.py --mode extract --input input/document.pdf
```

### Complete pipeline

```bash
python main.py --mode full --input input/document.pdf
```

### Offline readiness

```bash
python main.py --mode check-offline
```

---

# 23. Reusable Module

The same functionality should be available programmatically.

Example:

```python
from document_intelligence import DocumentProcessor

processor = DocumentProcessor()

result = processor.process(
    "document.pdf"
)
```

The application receives a structured result:

```python
print(result.document_type)
print(result.text)
print(result.entities)
print(result.extracted_fields)
```

This allows the engine to be embedded into other Python applications without modifying the OCR core.

---

# 24. Optional Local API

A local API can expose the engine to applications written in other languages.

```text
Application
     │
     │ Local request
     ▼
OCR / Document Intelligence Service
     │
     ▼
Document Processing
     │
     ▼
JSON Result
     │
     ▼
Application
```

The API should run locally and must not require external internet connectivity.

---

# 25. Project Structure

```text
ocr/
│
├── main.py
├── requirements.txt
├── setup_models.py
├── README.md
│
├── config/
│   └── config.yaml
│
├── models/
│   ├── paddleocr/
│   │   ├── det/
│   │   ├── rec/
│   │   └── cls/
│   │
│   ├── handwriting/
│   │
│   ├── embeddings/
│   │
│   ├── ner/
│   │
│   ├── classifiers/
│   │
│   └── layout/
│
├── input/
├── output/
├── temp/
│
├── document/
│   ├── file_detector.py
│   ├── pdf_processor.py
│   ├── docx_processor.py
│   ├── image_processor.py
│   └── document_normalizer.py
│
├── preprocessing/
│   ├── image_preprocessor.py
│   ├── deskew.py
│   ├── denoise.py
│   ├── threshold.py
│   └── orientation.py
│
├── layout/
│   ├── layout_analyzer.py
│   ├── region_detector.py
│   └── reading_order.py
│
├── ocr/
│   ├── base_engine.py
│   ├── paddle_engine.py
│   ├── handwriting_engine.py
│   ├── text_type_detector.py
│   ├── ocr_pipeline.py
│   └── result_merger.py
│
├── semantic/
│   ├── embedding_engine.py
│   ├── semantic_similarity.py
│   ├── document_classifier.py
│   ├── keyword_extractor.py
│   └── semantic_pipeline.py
│
├── nlp/
│   ├── ner_engine.py
│   ├── entity_normalizer.py
│   └── text_cleaner.py
│
├── extraction/
│   ├── pattern_manager.py
│   ├── regex_engine.py
│   ├── entity_extractor.py
│   ├── semantic_extractor.py
│   └── patterns.yaml
│
├── classification/
│   ├── base_classifier.py
│   ├── rule_classifier.py
│   ├── semantic_classifier.py
│   └── model_classifier.py
│
├── output/
│   ├── output_writer.py
│   ├── json_writer.py
│   └── text_writer.py
│
├── api/
│   ├── app.py
│   └── schemas.py
│
├── testing/
│   ├── test_document.py
│   ├── test_preprocessing.py
│   ├── test_ocr.py
│   ├── test_handwriting.py
│   ├── test_text_type.py
│   ├── test_semantic.py
│   ├── test_classification.py
│   └── test_extraction.py
│
├── fineTune/
│   ├── README.md
│   │
│   ├── datasets/
│   │   ├── handwriting/
│   │   ├── printed/
│   │   ├── mixed/
│   │   ├── text_type/
│   │   └── classification/
│   │
│   ├── annotations/
│   │
│   ├── preprocessing/
│   │
│   ├── configs/
│   │
│   ├── training/
│   │
│   ├── evaluation/
│   │
│   ├── checkpoints/
│   │
│   └── export/
│
└── utils/
    ├── logger.py
    ├── offline_checker.py
    └── model_manager.py
```

---

# 26. Offline Fine-Tuning

The `fineTune/` directory is a dedicated workspace for improving the system using locally available data.

Fine-tuning is intentionally separated from inference.

```text
                 MAIN SYSTEM
                      │
                      │ uses
                      ▼
                Trained Models
                      ▲
                      │
                      │ exported from
                      │
                fineTune/
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
     Local Dataset          Local Annotations
          │                       │
          └───────────┬───────────┘
                      ▼
               Offline Training
                      │
                      ▼
                Evaluation
                      │
                      ▼
               Best Checkpoint
                      │
                      ▼
                Model Export
                      │
                      ▼
                   models/
```

---

# 27. Fine-Tuning Targets

The framework should allow different components to be improved independently.

## Handwriting Recognition

Fine-tune handwriting recognition using domain-specific handwriting samples.

---

## Text-Type Detection

Improve classification between:

```text
PRINTED
HANDWRITTEN
MIXED
UNKNOWN
```

---

## OCR Recognition

Improve recognition accuracy for:

* Specific handwriting styles
* Poor-quality scans
* Domain-specific vocabulary
* Specialized documents
* Unusual fonts
* Low-resolution documents

---

## Document Classification

Train the system to recognize custom document categories.

Example:

```text
CATEGORY_A
CATEGORY_B
CATEGORY_C
CATEGORY_D
```

The actual categories must remain configurable and application-independent.

---

## NER

Customize entity extraction for domain-specific entities.

Example:

```text
CUSTOM_ID
PROJECT_CODE
DEPARTMENT
REFERENCE_NUMBER
DOCUMENT_NUMBER
```

---

# 28. Offline Fine-Tuning Workflow

The complete workflow should work without internet access after the initial model installation.

```text
1. Collect Data
       │
       ▼
2. Store Data Locally
       │
       ▼
3. Annotate Data Locally
       │
       ▼
4. Validate Dataset
       │
       ▼
5. Preprocess Dataset
       │
       ▼
6. Fine-Tune Model
       │
       ▼
7. Evaluate Model
       │
       ▼
8. Compare With Existing Model
       │
       ▼
9. Export Best Model
       │
       ▼
10. Install Into Local models/
       │
       ▼
11. Run Offline Inference
```

---

# 29. Important Fine-Tuning Requirement

Fine-tuning must **not require uploading data to a server**.

For example:

```text
fineTune/datasets/
```

can contain locally collected samples.

Training runs locally:

```bash
python fineTune/training/train.py
```

Evaluation runs locally:

```bash
python fineTune/evaluation/evaluate.py
```

The resulting model is exported locally:

```text
fineTune/export/
```

and can then be placed into:

```text
models/
```

for inference.

---

# 30. Incremental Offline Improvement

The system should support improving the model over time.

Example:

```text
Initial Model
     │
     ▼
Process Documents
     │
     ▼
Identify Incorrect/Low-Confidence Results
     │
     ▼
Correct / Annotate Locally
     │
     ▼
Add Data to Dataset
     │
     ▼
Offline Fine-Tuning
     │
     ▼
New Model
     │
     ▼
Evaluate
     │
     ▼
Deploy Locally
```

This allows the system to improve for a specific environment without sending documents outside the local system.

---

# 31. Model Versioning

Fine-tuned models should be versioned.

Example:

```text
models/
└── handwriting/
    ├── v1/
    ├── v2/
    └── v3/
```

Metadata should record:

```text
model_version
base_model
training_dataset
training_date
number_of_samples
evaluation_metrics
configuration
```

This makes it possible to compare models and roll back when necessary.

---

# 32. Dataset Separation

Training data should be separated from validation and test data.

```text
Dataset
│
├── train/
├── validation/
└── test/
```

The test dataset should not be used during training.

This is necessary to obtain meaningful evaluation results.

---

# 33. Evaluation

Different components require different metrics.

### OCR

```text
Character Error Rate (CER)
Word Error Rate (WER)
```

### Handwriting Recognition

```text
CER
WER
```

### Text-Type Detection

```text
Accuracy
Precision
Recall
F1-score
Confusion Matrix
```

### Document Classification

```text
Accuracy
Precision
Recall
F1-score
Confusion Matrix
```

### NER

```text
Entity Precision
Entity Recall
Entity F1-score
```

### Semantic Classification

```text
Accuracy
Macro F1
Similarity threshold evaluation
```

---

# 34. Testing Architecture

Every major component should be independently testable.

```text
                    System
                       │
       ┌───────────────┼───────────────┐
       │               │               │
       ▼               ▼               ▼
      OCR          Semantics       Extraction
       │               │               │
       ▼               ▼               ▼
   OCR Result      Meaning        Structured Data
```

Tests should exist for:

* File detection
* Document processing
* Image preprocessing
* Layout analysis
* OCR
* Handwriting recognition
* Text-type detection
* Semantic processing
* NER
* Classification
* Extraction
* Output generation
* Offline readiness

---

# 35. Configuration

All major settings should be configurable.

Example:

```yaml
offline_mode: true

ocr:
  engine: paddleocr
  language: en
  confidence_threshold: 0.5

handwriting:
  enabled: true
  engine: local
  confidence_threshold: 0.5

text_type_detection:
  enabled: true

layout:
  enabled: true

semantic:
  enabled: true
  embedding_model: "models/embeddings/model"

ner:
  enabled: true
  model_path: "models/ner"

classification:
  enabled: true
  method: semantic

preprocessing:
  enabled: true
  grayscale: true
  denoise: true
  deskew: true
  threshold: true
  auto_rotate: true

pdf:
  dpi: 300
  poppler_path: null

output:
  format: json
```

---

# 36. Model Management

All runtime models must be available locally.

```text
models/
├── paddleocr/
├── handwriting/
├── embeddings/
├── ner/
├── classifiers/
└── layout/
```

The runtime should never silently download a missing model.

If a model is unavailable:

```text
ERROR: Required model is not available locally.

Model:
handwriting_recognition

Expected location:
models/handwriting/

Offline mode is enabled.
Automatic downloads are disabled.
```

---

# 37. Offline Readiness Check

Run:

```bash
python main.py --mode check-offline
```

The system should verify:

```text
========================================
OFFLINE READINESS CHECK
========================================

OCR models                  ✓
Handwriting model           ✓
Embedding model             ✓
NER model                   ✓
Classification model        ✓
Layout model                ✓
Configuration               ✓

Automatic downloads         DISABLED
External API access        DISABLED
Internet dependency         NONE

RESULT:
SYSTEM READY FOR OFFLINE OPERATION
```

---

# 38. Output Structure

For:

```text
input/document.pdf
```

the system may generate:

```text
output/document/
│
├── ocr.txt
├── ocr.json
├── layout.json
├── text_types.json
├── entities.json
├── semantic.json
├── classification.json
├── extracted.json
└── result.json
```

---

# 39. Example Complete Result

```json
{
  "document": {
    "filename": "document.pdf",
    "pages": 2,
    "source_type": "PDF"
  },

  "classification": {
    "label": "TECHNICAL_DOCUMENT",
    "confidence": 0.94
  },

  "regions": [
    {
      "page": 1,
      "bbox": [100, 100, 700, 150],
      "text": "Technical Report",
      "text_type": "PRINTED",
      "confidence": 0.97
    },
    {
      "page": 1,
      "bbox": [120, 600, 720, 670],
      "text": "Please make the required corrections.",
      "text_type": "HANDWRITTEN",
      "confidence": 0.88
    }
  ],

  "entities": [
    {
      "text": "20 September",
      "label": "DATE",
      "confidence": 0.91
    }
  ],

  "extracted_fields": {
    "title": "Technical Report"
  },

  "semantic": {
    "categories": [
      {
        "label": "TECHNICAL_DOCUMENT",
        "similarity": 0.94
      }
    ]
  }
}
```

---

# 40. Application Integration

External applications should consume the output rather than modify the OCR pipeline.

```text
                 DOCUMENT
                     │
                     ▼
          DOCUMENT INTELLIGENCE ENGINE
                     │
                     ▼
              STANDARD RESULT
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
 Application A   Application B   Application C
```

Each application can use the result differently.

For example, one application may use:

```text
document_type
```

while another may use:

```text
entities
```

and another may use:

```text
semantic similarity
```

The OCR engine remains independent.

---

# 41. Separation of Responsibilities

The project deliberately separates **document intelligence** from **application business logic**.

## Document Intelligence Engine

Responsible for:

```text
Document
 ↓
Preprocessing
 ↓
Layout
 ↓
OCR
 ↓
Handwriting Detection
 ↓
Text-Type Detection
 ↓
Semantic Understanding
 ↓
NER
 ↓
Classification
 ↓
Information Extraction
 ↓
Structured Result
```

## External Application

Responsible for:

```text
Structured Result
       ↓
Application-specific rules
       ↓
Workflow
       ↓
Actions
```

The OCR engine should not contain assumptions about how a particular application uses the extracted information.

---

# 42. Extending the System

The architecture should make it possible to add new components without rewriting the complete pipeline.

### New OCR Engine

Add:

```text
ocr/new_engine.py
```

implementing:

```python
BaseOCREngine
```

---

### New Embedding Model

Place the model under:

```text
models/embeddings/
```

and configure its path.

---

### New Classifier

Implement the classifier interface under:

```text
classification/
```

---

### New NER Model

Place the model under:

```text
models/ner/
```

---

### New Document Format

Add a processor under:

```text
document/
```

---

# 43. Recommended Architecture Philosophy

The system should follow these principles:

### Offline First

Local inference and local training.

### Modular

Each component can be replaced independently.

### Model Agnostic

Do not permanently couple the architecture to a single OCR or NLP model.

### Application Independent

No application-specific business rules inside the core engine.

### Explainable

Provide:

```text
What was detected?
Where was it detected?
What type of text was detected?
What confidence does the model have?
Why was the document classified this way?
```

### Fine-Tunable

Allow local data to improve model performance.

### Reproducible

Track model versions, datasets and evaluation metrics.

### Privacy Focused

Documents remain local during processing and training.

---

# 44. Future Roadmap

Potential future capabilities include:

* Advanced handwriting recognition
* Better handwritten/printed segmentation
* Table detection and extraction
* Form understanding
* Signature detection
* Stamp/seal detection
* Checkbox recognition
* Mathematical expression recognition
* Multi-language OCR
* Multilingual embeddings
* Local vector database
* Semantic document search
* Document similarity search
* Active learning
* Human-in-the-loop correction
* Confidence-based manual verification
* Incremental offline fine-tuning
* Model version management
* GPU acceleration
* Local REST API
* Python SDK
* Desktop GUI
* Batch processing
* Parallel document processing
* Custom domain-specific models

---

# 45. Complete System Concept

The final architecture can be summarized as:

```text
                         RAW DOCUMENT
                              │
                              ▼
                     DOCUMENT PROCESSING
                              │
                              ▼
                       IMAGE PREPROCESSING
                              │
                              ▼
                        LAYOUT ANALYSIS
                              │
                              ▼
                     TEXT REGION DETECTION
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
             PRINTED                   HANDWRITTEN
                 │                         │
                 ▼                         ▼
            PRINTED OCR              HANDWRITING OCR
                 │                         │
                 └────────────┬────────────┘
                              ▼
                         OCR RESULTS
                              │
                              ▼
                    TEXT-TYPE INFORMATION
                              │
                              ▼
                     SEMANTIC PROCESSING
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
          Embeddings          NER        Classification
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                    INFORMATION EXTRACTION
                              │
                              ▼
                     CONFIDENCE ANALYSIS
                              │
                              ▼
                    STANDARDIZED JSON
                              │
               ┌──────────────┼──────────────┐
               │              │              │
               ▼              ▼              ▼
          Application 1   Application 2   Application 3
```

And the improvement cycle is:

```text
                 EXISTING MODEL
                       │
                       ▼
                OFFLINE INFERENCE
                       │
                       ▼
                LOW-CONFIDENCE /
                INCORRECT RESULTS
                       │
                       ▼
                  LOCAL DATA
                       │
                       ▼
                  ANNOTATION
                       │
                       ▼
              OFFLINE FINE-TUNING
                       │
                       ▼
                  EVALUATION
                       │
                       ▼
                BETTER MODEL
                       │
                       ▼
               LOCAL DEPLOYMENT
```

---

# 46. Final Objective

This project is intended to be a **general-purpose Offline OCR and Document Intelligence Engine**, rather than an OCR implementation tied to one particular application.

Its responsibility is to transform:

```text
RAW DOCUMENT
```

into:

```text
UNDERSTOOD DOCUMENT
```

by combining:

```text
OCR
+
Handwriting Recognition
+
Printed/Handwritten Detection
+
Layout Analysis
+
Semantic Embeddings
+
Named Entity Recognition
+
Document Classification
+
Information Extraction
+
Confidence Analysis
```

The system should remain:

```text
        INDEPENDENT
             +
         REUSABLE
             +
          OFFLINE
             +
       FINE-TUNABLE
             +
          MODULAR
             +
      APPLICATION-AGNOSTIC
```

The same engine can therefore be integrated into any application that needs to process and understand documents, without requiring the engine itself to know how the consuming application will use the extracted information.

---

# License

MIT License. See `LICENSE` for details.
