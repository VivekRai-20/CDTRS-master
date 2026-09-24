# models/ner/

Place a spaCy NER model here for named entity recognition.

## Option 1: spaCy model

Download a spaCy model wheel offline and install to a subdirectory:

    models/ner/en_core_web_sm-3.7.1/

## Option 2: Regex-only (no model needed)

Leave this directory empty. The NER engine will automatically use
its built-in regex patterns for EMAIL, PHONE, DATE, MONEY,
REFERENCE_NUMBER, and DOCUMENT_ID extraction.

## Configuration (config.yaml)

    ner:
      enabled: true
      model_path: "models/ner"
      backend: "spacy"    # or "regex" to force regex-only
