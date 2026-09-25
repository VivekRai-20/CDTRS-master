# models/classifiers/

Optional classifiers trained on **your own** labelled data. Without them, the
built-in fallbacks are used, so nothing needs to be here.

## text_type/: printed or handwritten line

```
models/classifiers/text_type/
├── classifier.pkl          Random Forest on line-shape features
├── classifier_<date>.pkl   earlier versions (kept as backups)
└── model_meta.json         test scores, date, number of lines
```

Train it with `python fineTune/training/train.py --task text_type`, using the lines
labelled with `fineTune/label_tool.py`. Without `classifier.pkl`, the built-in model
in `ocr/text_type_detector.py` is used. To go back to it, delete or rename
`classifier.pkl` and restart the backend.

## document/: document category

```
models/classifiers/document/
├── classifier.pkl      Logistic Regression
├── vectorizer.pkl      TF-IDF vocabulary
├── label_encoder.pkl   category names
└── model_meta.json
```

Train it with `python fineTune/training/train.py --task classification`, using
documents in `fineTune/datasets/classification/<CATEGORY>/`. The OCR uses it instead
of the keyword rules when it is at least `classification.min_model_confidence` sure
(set in `config/config.yaml`).

For both classifiers, see **`fineTune/README.md`**. These folders are not tracked by
git.
