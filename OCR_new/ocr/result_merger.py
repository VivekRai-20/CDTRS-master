"""
ocr/result_merger.py
---------------------
Merge OCR results from multiple engines (printed OCR + handwriting OCR)
into a single, ordered list of region dicts.

Responsibilities
----------------
* Deduplicate regions with highly overlapping bounding boxes.
* Prefer higher-confidence results when two regions cover the same area.
* Assign a final ``reading_order`` index based on spatial position
  (top-to-bottom, left-to-right within the same horizontal band).

Input
-----
Two lists of OCR region dicts, each conforming to the base engine schema::

    {
        "text":       str,
        "confidence": float,
        "bbox":       [x1, y1, x2, y2],
        "page":       int,
        "text_type":  str   (optional)
    }

Output
------
A merged, reading-order-sorted list with an additional ``reading_order``
field (1-indexed) on each region.
"""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)

# IoU threshold above which two boxes are considered duplicates
_IOU_THRESHOLD: float = 0.4


def merge(
    printed_regions: list[dict[str, Any]],
    handwritten_regions: list[dict[str, Any]],
    iou_threshold: float = _IOU_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Merge *printed_regions* and *handwritten_regions* into one list.

    Parameters
    ----------
    printed_regions : list[dict]
        Regions from the printed OCR engine.
    handwritten_regions : list[dict]
        Regions from the handwriting OCR engine.
    iou_threshold : float
        IoU above which two regions are considered duplicates.
        The region with the higher confidence wins.

    Returns
    -------
    list[dict]
        Merged regions with ``reading_order`` field added.
    """
    combined = list(printed_regions) + list(handwritten_regions)

    if not combined:
        return []

    # Group by page number
    pages: dict[int, list[dict[str, Any]]] = {}
    for r in combined:
        pages.setdefault(r.get("page", 1), []).append(r)

    merged_all: list[dict[str, Any]] = []
    for page_num in sorted(pages.keys()):
        page_regions = _deduplicate(pages[page_num], iou_threshold)
        page_regions = _sort_reading_order(page_regions)
        merged_all.extend(page_regions)

    # Assign global reading_order
    for idx, region in enumerate(merged_all, start=1):
        region["reading_order"] = idx

    log.debug(
        "Merged %d printed + %d handwritten → %d final regions.",
        len(printed_regions), len(handwritten_regions), len(merged_all),
    )
    return merged_all


# ──────────────────────────────────────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────────────────────────────────────

def _deduplicate(
    regions: list[dict[str, Any]], iou_threshold: float
) -> list[dict[str, Any]]:
    """Remove duplicate / heavily-overlapping regions, keeping best confidence."""
    kept: list[dict[str, Any]] = []

    for candidate in regions:
        c_bbox = candidate.get("bbox", [0, 0, 0, 0])
        c_conf = float(candidate.get("confidence", 0.0))

        is_duplicate = False
        for kept_region in kept:
            k_bbox = kept_region.get("bbox", [0, 0, 0, 0])
            iou = _iou(c_bbox, k_bbox)

            if iou >= iou_threshold:
                # Duplicate found — keep whichever has higher confidence
                is_duplicate = True
                k_conf = float(kept_region.get("confidence", 0.0))
                if c_conf > k_conf:
                    kept_region.update(candidate)
                break

        if not is_duplicate:
            kept.append(dict(candidate))

    return kept


def _iou(a: list[int | float], b: list[int | float]) -> float:
    """
    Intersection over Union for two [x1, y1, x2, y2] bounding boxes.
    """
    if len(a) != 4 or len(b) != 4:
        return 0.0

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

    union_area = area_a + area_b - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


# ──────────────────────────────────────────────────────────────────────────────
# Reading-order sorting
# ──────────────────────────────────────────────────────────────────────────────

def _sort_reading_order(
    regions: list[dict[str, Any]],
    line_tolerance_ratio: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Sort *regions* into natural reading order (top-to-bottom, left-to-right).

    Regions whose vertical centres are within ``line_tolerance_ratio * height``
    of each other are treated as being on the same text line and sorted
    left-to-right among themselves.
    """
    if not regions:
        return regions

    def y_mid(r: dict) -> float:
        b = r.get("bbox", [0, 0, 0, 0])
        return (b[1] + b[3]) / 2.0 if len(b) == 4 else 0.0

    def x_left(r: dict) -> float:
        b = r.get("bbox", [0, 0, 0, 0])
        return float(b[0]) if len(b) == 4 else 0.0

    def bbox_height(r: dict) -> float:
        b = r.get("bbox", [0, 0, 0, 0])
        return max(1.0, float(b[3] - b[1])) if len(b) == 4 else 20.0

    # Group into lines
    lines: list[list[dict[str, Any]]] = []
    for region in regions:
        ym = y_mid(region)
        placed = False
        for line in lines:
            ref_ym = y_mid(line[0])
            tol = bbox_height(line[0]) * line_tolerance_ratio
            if abs(ym - ref_ym) <= tol:
                line.append(region)
                placed = True
                break
        if not placed:
            lines.append([region])

    # Sort lines by y-midpoint, within each line sort by x
    lines.sort(key=lambda ln: y_mid(ln[0]))
    for line in lines:
        line.sort(key=x_left)

    return [r for line in lines for r in line]
