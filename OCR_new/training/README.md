# Training — Placeholder

This directory is reserved for future fine-tuning of PaddleOCR on custom handwriting datasets.

## When to use this

PaddleOCR's default recognition model performs well on printed text but may underperform on:
- Handwritten text
- Domain-specific printed fonts (very old documents, cursive, stylised)
- Low-quality scans

Fine-tuning the **recognition model** on a labelled dataset of your specific document type is the recommended path to improving accuracy.

## Directory structure (future)

```
training/
├── README.md                    ← this file
├── datasets/
│   ├── raw/                     ← original labelled images + text pairs
│   └── processed/               ← converted to PaddleOCR training format
├── configs/
│   └── rec_custom.yml           ← PaddleOCR training config (copy from PaddleOCR repo)
├── checkpoints/                 ← Saved model checkpoints
├── export/                      ← Exported inference models (det/ rec/ cls/)
├── prepare_dataset.py           ← Script to convert labels to PaddleOCR format
└── train.py                     ← Fine-tuning launch script
```

## PaddleOCR training documentation

- Text recognition training: https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_en/recognition_en.md
- Dataset format (Label file): each line = `image_path\tlabel_text`

## Integration with this system

After fine-tuning and exporting a recognition model:

1. Copy the exported model to:
   ```
   models/paddleocr/rec/
   ```
   (replacing or alongside the default model)

2. No code changes are required — the OCR engine reads model dirs from config.yaml.

3. Verify with:
   ```bash
   python main.py --mode ocr --input input/handwritten_sample.jpg
   ```

## Future: Handwritten vs Printed Classification

A region classifier can be added between the preprocessing and OCR steps to:
1. Detect whether a region is handwritten or printed
2. Route each region to the appropriate OCR engine

The bounding boxes and region crops preserved in the OCR output are already
structured to support this without pipeline changes.
