"""
layout/reading_order.py
------------------------
Reconstruct the logical reading order of detected layout regions.

Algorithm
---------
1.  Group regions by page.
2.  Within each page, cluster regions into horizontal bands (lines) based
    on their vertical-centre proximity.
3.  Sort bands top-to-bottom; within each band sort regions left-to-right.
4.  Assign a sequential ``reading_order`` index (1-based) across all pages.

This deterministic algorithm works without any model and handles typical
document layouts (single-column, two-column, header/footer).
"""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


def assign_reading_order(
    regions: list[dict[str, Any]],
    line_tolerance_ratio: float = 0.6,
) -> list[dict[str, Any]]:
    """
    Sort *regions* into natural reading order and assign ``reading_order``.

    Parameters
    ----------
    regions : list[dict]
        Region dicts, each with a ``bbox`` [x1, y1, x2, y2] and a ``page``.
    line_tolerance_ratio : float
        Fraction of a region's height used as the y-proximity tolerance
        when grouping into horizontal bands.  Increase for sparser layouts.

    Returns
    -------
    list[dict]
        The same regions with ``reading_order`` (int, 1-based) added.
    """
    if not regions:
        return regions

    # Group by page
    pages: dict[int, list[dict[str, Any]]] = {}
    for r in regions:
        pages.setdefault(int(r.get("page", 1)), []).append(r)

    ordered: list[dict[str, Any]] = []
    global_idx = 1

    for page_num in sorted(pages.keys()):
        page_regions = pages[page_num]
        sorted_page = _sort_page(page_regions, line_tolerance_ratio)
        for r in sorted_page:
            r["reading_order"] = global_idx
            global_idx += 1
        ordered.extend(sorted_page)

    log.debug("Reading order assigned to %d region(s).", len(ordered))
    return ordered


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────

def _y_mid(region: dict[str, Any]) -> float:
    bbox = region.get("bbox", [0, 0, 0, 0])
    return (bbox[1] + bbox[3]) / 2.0 if len(bbox) == 4 else 0.0


def _x_left(region: dict[str, Any]) -> float:
    bbox = region.get("bbox", [0, 0, 0, 0])
    return float(bbox[0]) if len(bbox) == 4 else 0.0


def _bbox_height(region: dict[str, Any]) -> float:
    bbox = region.get("bbox", [0, 0, 0, 0])
    return max(1.0, float(bbox[3] - bbox[1])) if len(bbox) == 4 else 20.0


def _sort_page(
    regions: list[dict[str, Any]],
    line_tolerance_ratio: float,
) -> list[dict[str, Any]]:
    """Sort a single page's regions into reading order."""
    lines: list[list[dict[str, Any]]] = []

    for region in regions:
        ym = _y_mid(region)
        placed = False
        for band in lines:
            ref_ym = _y_mid(band[0])
            tol = _bbox_height(band[0]) * line_tolerance_ratio
            if abs(ym - ref_ym) <= tol:
                band.append(region)
                placed = True
                break
        if not placed:
            lines.append([region])

    # Sort bands top-to-bottom, within each band sort left-to-right
    lines.sort(key=lambda band: _y_mid(band[0]))
    for band in lines:
        band.sort(key=_x_left)

    return [r for band in lines for r in band]
