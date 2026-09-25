"""
fineTune/prepare_dataset.py
---------------------------
STEP 1 - turn your handwriting scans into one image per text line.

Put your files (PNG, JPG, TIFF, BMP, WEBP or PDF - any number, any
sub-folders) into:

    OCR_new/fineTune/datasets/raw/

then run, from the OCR_new folder:

    python fineTune/prepare_dataset.py

For every page, PaddleOCR finds the text lines.  Each line is saved to
datasets/lines/ and gets a row in datasets/labels.csv with PaddleOCR's
reading and the printed/handwritten guess.  You then correct the rows with
the labelling tool (fineTune/label_tool.py) or in Excel.

Running it again only adds files that are new; your labels are kept.

Options
    --lines           the files in raw/ are already single text lines
                      (no detection; a same-named .txt file, if present,
                      holds the correct text)
    --type TYPE       with --lines: HANDWRITTEN (default) or PRINTED
    --min-height N    ignore detected lines shorter than N pixels (default 12)
    --stats           only print how many lines are labelled
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    DOCUMENT_EXTENSIONS, HANDWRITTEN, IMAGE_EXTENSIONS, LABELS_CSV, LINES_DIR, PRINTED, RAW_DIR,
    assign_split, load_ocr_config, read_labels, summary, write_labels,
)


def _safe_name(relative: Path) -> str:
    stem = "_".join(relative.with_suffix("").parts)
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:80]


def _pages(path: Path, config: dict):
    """(page_number, BGR image) for an image or PDF, using OCR_new's loaders."""
    if path.suffix.lower() == ".pdf":
        from document.pdf_processor import load_pdf_pages
        yield from load_pdf_pages(path, config)
    else:
        from document.image_processor import load_image_pages
        yield from load_image_pages(path)


def prepare_documents(files: list[Path], rows: list[dict], min_height: int) -> int:
    import cv2

    from ocr.paddle_engine import PaddleEngine
    from ocr.text_type_detector import TextTypeDetector

    config = load_ocr_config()
    engine = PaddleEngine()
    engine.initialize(config)
    detector = TextTypeDetector(config)
    known_sources = {row["source"] for row in rows}
    added = 0

    for path in files:
        relative = path.relative_to(RAW_DIR)
        source = relative.as_posix()
        if source in known_sources:
            continue
        base = _safe_name(relative)
        print(f"  {source}")
        for page, image in _pages(path, config):
            regions = engine.recognize(image, page=page)
            detector.detect_regions(regions, image)
            h, w = image.shape[:2]
            for index, region in enumerate(regions, 1):
                x1, y1, x2, y2 = [int(v) for v in region["bbox"]]
                if y2 - y1 < min_height or x2 - x1 < min_height:
                    continue
                # Exactly the box the OCR uses, so training sees what the
                # OCR will see when reading documents.
                crop = image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                name = f"{base}_p{page}_{index:03d}.png"
                cv2.imwrite(str(LINES_DIR / name), crop)
                rows.append({
                    "image": name,
                    "source": source,
                    "page": page,
                    "bbox": f"{x1} {y1} {x2} {y2}",
                    "ocr_text": region.get("text", ""),
                    "ocr_confidence": region.get("confidence", ""),
                    "predicted_type": region.get("text_type", ""),
                    "text": "",
                    "type": "",
                    "split": assign_split(name),
                    "labelled_at": "",
                })
                added += 1
            print(f"    page {page}: {len(regions)} line(s)")
        write_labels(rows)  # save after every file
    return added


def _read_line(engine, detector, image) -> tuple[str, str, str]:
    """PaddleOCR's reading of a single-line image (for comparison later)."""
    import cv2

    padded = cv2.copyMakeBorder(image, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    regions = sorted(engine.recognize(padded), key=lambda r: r["bbox"][0])
    if not regions:
        return "", "", ""
    text = " ".join(r["text"] for r in regions)
    confidence = round(sum(r["confidence"] for r in regions) / len(regions), 4)
    kind = detector.detect(image, confidence)["text_type"]
    return text, str(confidence), kind


def prepare_lines(files: list[Path], rows: list[dict], kind: str) -> int:
    import shutil

    import cv2

    from ocr.paddle_engine import PaddleEngine
    from ocr.text_type_detector import TextTypeDetector

    known = {row["source"] for row in rows}
    todo = [p for p in files if p.relative_to(RAW_DIR).as_posix() not in known
            and p.suffix.lower() in IMAGE_EXTENSIONS]
    if not todo:
        return 0
    config = load_ocr_config()
    engine = PaddleEngine()
    engine.initialize(config)
    detector = TextTypeDetector(config)
    added = 0
    for path in todo:
        relative = path.relative_to(RAW_DIR)
        name = f"{_safe_name(relative)}{path.suffix.lower()}"
        shutil.copy2(path, LINES_DIR / name)
        image = cv2.imread(str(path))
        ocr_text, ocr_conf, predicted = _read_line(engine, detector, image) if image is not None else ("", "", "")
        text_file = path.with_suffix(".txt")
        text = text_file.read_text(encoding="utf-8", errors="replace").strip() if text_file.exists() else ""
        h, w = image.shape[:2] if image is not None else (0, 0)
        rows.append({
            "image": name, "source": relative.as_posix(), "page": 1, "bbox": f"0 0 {w} {h}",
            "ocr_text": ocr_text, "ocr_confidence": ocr_conf, "predicted_type": predicted,
            "text": " ".join(text.split()), "type": kind if text else "", "split": assign_split(name),
            "labelled_at": datetime.now().isoformat(timespec="seconds") if text else "",
        })
        added += 1
        if added % 50 == 0:
            print(f"  {added} line(s)")
            write_labels(rows)
    write_labels(rows)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lines", action="store_true", help="files in raw/ are single text lines")
    parser.add_argument("--type", default=HANDWRITTEN, choices=[HANDWRITTEN, PRINTED],
                        type=str.upper, help="with --lines: the type of all lines")
    parser.add_argument("--min-height", type=int, default=12)
    parser.add_argument("--stats", action="store_true", help="only print label counts")
    args = parser.parse_args()

    rows = read_labels()
    if args.stats:
        print(summary(rows))
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LINES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in RAW_DIR.rglob("*") if p.is_file() and p.suffix.lower() in DOCUMENT_EXTENSIONS)
    if not files:
        print(f"No images or PDFs found in {RAW_DIR}\nCopy your handwriting scans there and run this again.")
        return

    print(f"Preparing {len(files)} file(s) from {RAW_DIR}")
    if args.lines:
        added = prepare_lines(files, rows, args.type)
    else:
        added = prepare_documents(files, rows, args.min_height)
    print(f"\nAdded {added} line image(s).  Labels file: {LABELS_CSV}\n")
    print(summary(rows))
    print("\nNext: label them with   python fineTune/label_tool.py")


if __name__ == "__main__":
    main()
