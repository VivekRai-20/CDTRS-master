# models/ner/

Named-entity recognition (people, organisations, places, dates, amounts) for
`nlp/ner_engine.py`.

The engine uses the first of these that it finds:

1. A spaCy model folder here, for example `models/ner/my_model/` (a folder with
   `meta.json`, as saved by spaCy's `nlp.to_disk()`).
2. The installed spaCy package named in `config.yaml` → `ner.package`. This is
   `en_core_web_sm` 3.8.0, which is installed from `imp.txt`, so nothing needs to
   be placed here.
3. Built-in regex patterns only: email, phone, date, money, reference numbers.

Only useful labels are kept (PERSON, ORG, GPE, LOC, DATE, MONEY, …), and
implausible matches are filtered out.

Settings are in `config/config.yaml`:

```yaml
ner:
  enabled: true
  model_path: "models/ner"
  package: "en_core_web_sm"
  backend: "spacy"          # "regex" = never use spaCy
```
