# models/classifiers/

Place trained classification models here.

## document/

ML classifier for document category:

    models/classifiers/document/
    ├── classifier.pkl
    ├── vectorizer.pkl
    └── label_encoder.pkl

Train using: python fineTune/training/train.py --config fineTune/configs/classification.yaml

## text_type/

Classifier for PRINTED vs HANDWRITTEN detection:

    models/classifiers/text_type/
    └── classifier.pkl

Train using: python fineTune/training/train.py --config fineTune/configs/text_type.yaml

Both classifiers are optional — rule-based and heuristic fallbacks
are used when no trained model is present.
