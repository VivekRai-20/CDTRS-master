# training/ (moved)

Training and fine-tuning now live in **`OCR_new/fineTune/`**. See
[`fineTune/README.md`](../fineTune/README.md) for the step-by-step guide:
prepare your handwriting scans, label them, train, evaluate and activate.

PaddleOCR's own recognition model is not retrained. Its training tools are not
part of the installed `paddleocr` 2.8.1 package. Handwriting is handled by the
TrOCR model in `models/handwriting/`, which `fineTune/` fine-tunes.
