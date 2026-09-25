# models/handwriting/

Handwriting recognition models (Microsoft TrOCR) used by `ocr/handwriting_engine.py`
to re-read lines that the printed/handwritten detector marks as handwritten.

```
models/handwriting/
├── trocr-small-handwritten/   base model - python fineTune/download_base_model.py
├── v1/, v2/, ...              your fine-tuned versions - python fineTune/training/train.py --task handwriting
│   └── model_meta.json        base model, number of training lines, test scores
└── active.txt                 name of the folder the OCR uses (one line, e.g. "v2")
```

- Get the base model once (internet needed only here, about 250 MB):
  `python fineTune/download_base_model.py`. On a PC without internet, copy this
  folder from a PC where it was downloaded.
- Fine-tune it on your own labelled handwriting: see **`fineTune/README.md`**.
- List the models or choose one: `python fineTune/set_active_model.py [name|--off]`,
  then restart the CDTRS backend.

With no `active.txt`, or when it names a missing folder, handwriting recognition is
skipped and PaddleOCR's reading is kept. Nothing breaks.

Model folders are not tracked by git. They are too large (see `.gitignore`).

Settings are in `config/config.yaml`, section `handwriting:`:

| Setting | Meaning |
|---|---|
| `enabled` | Turn handwriting recognition on or off |
| `model_path` | This folder |
| `device` | `cpu` (the installed PyTorch is the CPU build) |
| `num_beams`, `max_new_tokens` | Decoding settings |
| `replace_below_confidence` | UNKNOWN-type lines with a lower PaddleOCR confidence are re-read too |
| `min_confidence` | The handwriting reading is used only when it is at least this confident, and at least as confident as PaddleOCR |
| `max_lines_per_page` | Upper limit of re-read lines per page (keeps big pages fast) |
