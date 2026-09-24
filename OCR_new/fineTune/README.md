# fineTune

This directory is the **offline fine-tuning workspace** for the OCR & Document Intelligence Engine.

Fine-tuning is intentionally separated from inference — this directory only handles training and exporting improved models. The main system uses models from `../models/`.

---

## Workflow

```
1. Collect Data       → fineTune/datasets/
2. Annotate Locally   → fineTune/annotations/
3. Validate Dataset
4. Preprocess         → fineTune/preprocessing/
5. Fine-Tune          → python fineTune/training/train.py
6. Evaluate           → python fineTune/evaluation/evaluate.py
7. Export Best Model  → fineTune/export/
8. Install to models/ → copy fineTune/export/<model> → models/<model>/vN/
```

All steps run **100% offline** after initial model setup.

---

## Directory Structure

```
fineTune/
├── datasets/
│   ├── handwriting/     – handwriting recognition training images + labels
│   ├── printed/         – printed OCR samples
│   ├── mixed/           – mixed printed+handwritten samples
│   ├── text_type/       – text-type detection dataset
│   └── classification/  – document classification dataset
│
├── annotations/         – annotation files (JSON, XML, or YOLO format)
├── preprocessing/       – dataset preprocessing scripts
├── configs/             – training configuration YAML files
├── training/            – training scripts
│   └── train.py
├── evaluation/          – evaluation scripts
│   └── evaluate.py
├── checkpoints/         – training checkpoints (saved during training)
└── export/              – exported models ready for deployment
```

---

## Dataset Format

### Handwriting / Printed OCR

Place image files and corresponding transcription text files:

```
datasets/handwriting/
├── sample_001.png
├── sample_001.txt   ← contains the ground-truth text
├── sample_002.jpg
└── sample_002.txt
```

### Text-Type Detection

```
datasets/text_type/
├── printed/
│   └── *.png
└── handwritten/
    └── *.png
```

### Document Classification

```
datasets/classification/
├── INVOICE/
│   └── *.pdf (or *.txt)
├── LEAVE_APPLICATION/
│   └── *.pdf
└── TECHNICAL_REPORT/
    └── *.pdf
```

---

## Training

```bash
python fineTune/training/train.py --config fineTune/configs/handwriting.yaml
```

## Evaluation

```bash
python fineTune/evaluation/evaluate.py --model fineTune/checkpoints/best/ --dataset fineTune/datasets/handwriting/
```

## Deploying a Fine-Tuned Model

After evaluation, copy the best model to the main `models/` directory:

```bash
# Example: deploying a new handwriting model version
cp -r fineTune/export/handwriting_v2 models/handwriting/v2
echo "v2" > models/handwriting/active.txt
```

---

## Important

- **Never upload training data to a server.**
- Fine-tuning must run completely locally.
- The test dataset must not be used during training.
- Keep a record of model versions and evaluation metrics in `model_meta.json`.
