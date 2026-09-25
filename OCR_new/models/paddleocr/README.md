# models/paddleocr/

PaddleOCR 2.x inference models (for `paddleocr` 2.8.1 and `paddlepaddle` 2.6.2),
used offline by `ocr/paddle_engine.py`:

| Folder | Model | Job |
|---|---|---|
| `det/` | en_PP-OCRv3_det_infer | finds text lines |
| `rec/` | en_PP-OCRv4_rec_infer | reads them |
| `cls/` | ch_ppocr_mobile_v2.0_cls_infer | turns upside-down lines round |

These models (about 16 MB) are tracked in git, so the OCR works offline right after
cloning. `model_info.json` records where they came from.

To check them, or to copy them again from PaddleOCR's download cache
(`~/.paddleocr/whl/`), run this from `OCR_new/`:

```
python setup_models.py --check
python setup_models.py
```

The folders are set in `config/config.yaml` → `paddleocr.det_model_dir`,
`rec_model_dir` and `cls_model_dir`.
