"""
main.py
-------
Command-line entry point for the Offline OCR & Extraction System.

Usage examples
--------------
  python main.py --help
  python main.py --mode check-offline
  python main.py --mode ocr      --input input/sample.jpg
  python main.py --mode ocr      --input input/document.pdf
  python main.py --mode patterns --input input/sample.txt
  python main.py --mode patterns                              # interactive
  python main.py --mode full     --input input/document.pdf

For a full description of all options run: python main.py --help
"""

from __future__ import annotations

import argparse
import sys
import os
import json
from pathlib import Path

# ── ensure project root is on sys.path ───────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── load config before importing sub-modules ─────────────────────────────────
import yaml


def _load_config(config_path: Path) -> dict:
    """Load config.yaml and return as dict."""
    if not config_path.exists():
        print(
            f"[ERROR] Configuration file not found: {config_path}\n"
            "       Please ensure config/config.yaml exists.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    config_path = _ROOT / "config" / "config.yaml"
    config = _load_config(config_path)

    # Setup logging as early as possible
    from utils.logger import setup_root_logger, get_logger
    setup_root_logger(config.get("logging", {}))
    log = get_logger("main")

    parser = _build_parser()
    args = parser.parse_args()

    log.info("Mode: %s", args.mode)

    if args.mode == "check-offline":
        _mode_check_offline(config)

    elif args.mode == "ocr":
        _require_input(args)
        _mode_ocr(args.input, config)

    elif args.mode == "understand":
        _require_input(args)
        _mode_understand(args.input, config)

    elif args.mode == "classify":
        _require_input(args)
        _mode_classify(args.input, config)

    elif args.mode == "extract":
        _require_input(args)
        _mode_extract(args.input, config)

    elif args.mode == "patterns":
        _mode_patterns(args.input, config)

    elif args.mode == "full":
        _require_input(args)
        _mode_full(args.input, config)

    else:
        parser.print_help()
        sys.exit(1)


# ============================================================================ #
# Mode: check-offline                                                           #
# ============================================================================ #

def _mode_check_offline(config: dict) -> None:
    """Validate all offline requirements and print a status report."""
    from utils.offline_checker import run_full_check
    run_full_check(config)


# ============================================================================ #
# Mode: ocr                                                                     #
# ============================================================================ #

def _mode_ocr(input_path: str, config: dict) -> None:
    """
    Run OCR only (no regex extraction).

    Pipeline: File → Document processing → Preprocessing → PaddleOCR → Output
    """
    from utils.offline_checker import abort_if_models_missing
    from ocr.paddle_engine import PaddleEngine
    from ocr.ocr_pipeline import OCRPipeline
    from output.output_writer import OutputWriter

    log = _get_log()

    input_file = _resolve_input(input_path)

    # Guard — ensure models are present before initialising PaddleOCR
    abort_if_models_missing(config)

    # Initialise engine
    engine = PaddleEngine()
    engine.initialize(config)

    # Run pipeline
    pipeline = OCRPipeline(engine, config)
    result = pipeline.process(input_file)

    # Write outputs
    writer = OutputWriter(input_file, config)
    written = writer.write_ocr(result)

    # ── Console summary ──────────────────────────────────────────────── #
    print("\n" + "=" * 60)
    print(f"  OCR RESULTS  —  {Path(input_file).name}")
    print("=" * 60)
    print(f"  Document type : {result['doc_type']}")
    print(f"  Pages         : {result['pages']}")
    print(f"  Regions found : {len(result['regions'])}")
    print(f"  Elapsed       : {result['elapsed_s']}s")
    print()
    print("  Per-region breakdown:")
    print(f"  {'PAGE':>4}  {'CONF':>6}  {'BBOX':^24}  TEXT")
    print("  " + "-" * 80)
    for region in result["regions"]:
        bbox_str = str(region["bbox"])
        text_preview = region["text"][:60]
        print(
            f"  {region['page']:>4}  {region['confidence']:>6.3f}"
            f"  {bbox_str:^24}  {text_preview}"
        )
    print()
    print("  Full text:")
    print("  " + "-" * 60)
    for line in result["full_text"].splitlines():
        print(f"  {line}")
    print()
    print("  Output files:")
    for name, path in written.items():
        print(f"    {name:15}  {path}")
    print("=" * 60 + "\n")


# ============================================================================ #
# Mode: patterns                                                                #
# ============================================================================ #

def _mode_patterns(input_path: str | None, config: dict) -> None:
    """
    Run pattern extraction only (no OCR).

    Accepts a .txt file path OR reads from stdin interactively.
    """
    from extraction.pattern_manager import PatternManager
    from extraction.regex_engine import RegexEngine

    log = _get_log()

    paths_cfg = config.get("paths", {})
    patterns_file = _ROOT / paths_cfg.get("patterns_file", "extraction/patterns.yaml")

    pm = PatternManager(patterns_file)
    pm.load()

    engine = RegexEngine(pm)

    # ── Get text ─────────────────────────────────────────────────────── #
    if input_path:
        file = _resolve_input(input_path)
        text = Path(file).read_text(encoding="utf-8", errors="replace")
        log.info("Loaded text from: %s", file)
    else:
        print("\nPattern Testing Mode — paste OCR text below.")
        print("When finished, press ENTER on an empty line, then Ctrl-Z (Windows) or Ctrl-D (Unix).\n")
        lines: list[str] = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        text = "\n".join(lines)

    if not text.strip():
        print("[WARNING] Input text is empty. Nothing to extract.")
        sys.exit(0)

    # ── Run extraction ────────────────────────────────────────────────── #
    results = engine.extract(text)
    table   = engine.format_table(results)

    print("\n" + "=" * 60)
    print("  PATTERN EXTRACTION RESULTS")
    print("=" * 60)
    print()
    print(table)
    print()

    # Also emit JSON for scripting use
    json_out = {f: r.to_dict() for f, r in results.items()}

    print("JSON output:")
    print("-" * 40)
    print(json.dumps(json_out, indent=2, ensure_ascii=False))
    print()

    # Write to output dir if input_path was given
    if input_path:
        from output.output_writer import OutputWriter
        writer  = OutputWriter(input_path, config)
        written = writer.write_extracted(results)
        print("Output file(s):")
        for name, p in written.items():
            print(f"  {name}  ->  {p}")
        print()


# ============================================================================ #
# Mode: full                                                                    #
# ============================================================================ #

# ============================================================================ #
# Mode: understand                                                             #
# ============================================================================ #

def _mode_understand(input_path: str, config: dict) -> None:
    """
    Run semantic understanding pipeline (OCR + embeddings + keywords + similarity).
    """
    from document_intelligence import DocumentProcessor

    log = _get_log()
    input_file = _resolve_input(input_path)

    processor = DocumentProcessor(config=config)
    result = processor.process(input_file, mode="understand")
    written = result.save()

    print("\n" + "=" * 60)
    print(f"  SEMANTIC UNDERSTANDING RESULTS  —  {Path(input_file).name}")
    print("=" * 60)
    print(f"  Document type : {result.document_type}")
    print(f"  Pages         : {result.pages}")
    print(f"  Elapsed       : {result.metadata.get('elapsed_s', 0)}s")
    print()

    semantic = result.semantic
    keywords = semantic.get("keywords", [])
    if keywords:
        print("  Top Keywords:")
        print("  " + "-" * 40)
        for kw in keywords[:10]:
            print(f"    - {kw.get('keyword', ''):20} (score: {kw.get('score', 0):.4f})")
        print()

    cls = result.classification
    if cls and cls.get("label"):
        print(f"  Semantic Category: {cls.get('label')} (confidence: {cls.get('confidence', 0):.2f})")
        print()

    print("  Output files:")
    for name, p in written.items():
        print(f"    {name:20}  {p}")
    print("=" * 60 + "\n")


# ============================================================================ #
# Mode: classify                                                               #
# ============================================================================ #

def _mode_classify(input_path: str, config: dict) -> None:
    """
    Run document classification pipeline (OCR + rule & semantic classification).
    """
    from document_intelligence import DocumentProcessor

    log = _get_log()
    input_file = _resolve_input(input_path)

    processor = DocumentProcessor(config=config)
    result = processor.process(input_file, mode="classify")
    written = result.save()

    cls = result.classification

    print("\n" + "=" * 60)
    print(f"  DOCUMENT CLASSIFICATION  —  {Path(input_file).name}")
    print("=" * 60)
    print(f"  Category   : {cls.get('label', 'UNKNOWN')}")
    print(f"  Confidence : {cls.get('confidence', 0.0):.2f}")
    if cls.get("matched_keywords"):
        print(f"  Keywords   : {', '.join(cls.get('matched_keywords', []))}")
    if cls.get("categories"):
        print("\n  Category Scores:")
        for c in cls.get("categories", []):
            print(f"    - {c.get('label', ''):20} {c.get('similarity', 0):.4f}")
    print()
    print("  Output files:")
    for name, p in written.items():
        print(f"    {name:20}  {p}")
    print("=" * 60 + "\n")


# ============================================================================ #
# Mode: extract                                                                #
# ============================================================================ #

def _mode_extract(input_path: str, config: dict) -> None:
    """
    Run entity and information extraction pipeline (OCR + NER + regex patterns).
    """
    from document_intelligence import DocumentProcessor

    log = _get_log()
    input_file = _resolve_input(input_path)

    processor = DocumentProcessor(config=config)
    result = processor.process(input_file, mode="extract")
    written = result.save()

    print("\n" + "=" * 60)
    print(f"  INFORMATION EXTRACTION  —  {Path(input_file).name}")
    print("=" * 60)
    print(f"  Pages   : {result.pages}")
    print(f"  Elapsed : {result.metadata.get('elapsed_s', 0)}s")
    print()

    if result.extracted_fields:
        print("  Extracted Fields:")
        print(f"  {'FIELD':<20}  {'VALUE'}")
        print("  " + "-" * 60)
        for field, val in result.extracted_fields.items():
            print(f"  {field:<20}  {val}")
        print()

    if result.entities:
        print("  Named Entities:")
        print(f"  {'LABEL':<12}  {'TEXT':<30}  CONF")
        print("  " + "-" * 50)
        for ent in result.entities[:15]:
            print(f"  {ent.get('label', ''):<12}  {ent.get('text', '')[:28]:<30}  {ent.get('confidence', 0):.2f}")
        print()

    print("  Output files:")
    for name, p in written.items():
        print(f"    {name:20}  {p}")
    print("=" * 60 + "\n")


# ============================================================================ #
# Mode: full                                                                    #
# ============================================================================ #

def _mode_full(input_path: str, config: dict) -> None:
    """
    Full pipeline: Normalization → Layout → OCR → Text-Type → Semantic → NER → Classification → Extraction.
    """
    from document_intelligence import DocumentProcessor

    log = _get_log()
    input_file = _resolve_input(input_path)

    processor = DocumentProcessor(config=config)
    result = processor.process(input_file, mode="full")
    written = result.save()

    print("\n" + "=" * 60)
    print(f"  FULL PIPELINE RESULTS  —  {Path(input_file).name}")
    print("=" * 60)
    print(f"  Document format : {result.source_type}")
    print(f"  Classification  : {result.classification.get('label', 'UNKNOWN')} (conf: {result.classification.get('confidence', 0):.2f})")
    print(f"  Pages           : {result.pages}")
    print(f"  Regions found   : {len(result.regions)}")
    print(f"  Elapsed         : {result.metadata.get('elapsed_s', 0)}s")
    print()

    if result.extracted_fields:
        print("  Extracted Fields:")
        print(f"  {'FIELD':<18}  {'VALUE'}")
        print("  " + "-" * 60)
        for field, val in result.extracted_fields.items():
            print(f"  {field:<18}  {val}")
        print()

    if result.entities:
        print("  Named Entities:")
        print(f"  {'LABEL':<12}  {'TEXT':<30}  CONF")
        print("  " + "-" * 50)
        for ent in result.entities[:10]:
            print(f"  {ent.get('label', ''):<12}  {ent.get('text', '')[:28]:<30}  {ent.get('confidence', 0):.2f}")
        print()

    print("  Output files:")
    for name, p in written.items():
        print(f"    {name:20}  {p}")
    print("=" * 60 + "\n")


# ============================================================================ #
# Helpers                                                                       #
# ============================================================================ #

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description=(
            "Offline OCR & Document Intelligence Engine\n"
            "100%% offline — no internet access required at runtime."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode check-offline
  python main.py --mode ocr        --input input/document.pdf
  python main.py --mode understand --input input/document.pdf
  python main.py --mode classify   --input input/document.pdf
  python main.py --mode extract    --input input/document.pdf
  python main.py --mode full       --input input/document.pdf
  python main.py --mode patterns   --input input/sample.txt
""",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["ocr", "understand", "classify", "extract", "full", "patterns", "check-offline"],
        help=(
            "ocr           — Run OCR only (recognition & bounding boxes).\n"
            "understand    — Run semantic understanding & keyword extraction.\n"
            "classify      — Run document classification.\n"
            "extract       — Run entity & field extraction (NER + regex).\n"
            "full          — Run full document intelligence pipeline.\n"
            "patterns      — Run regex pattern extraction only.\n"
            "check-offline — Verify offline readiness (models, config)."
        ),
    )
    parser.add_argument(
        "--input", "-i",
        metavar="FILE",
        default=None,
        help=(
            "Path to the input file.\n"
            "Required for modes: ocr, understand, classify, extract, full.\n"
            "Optional for mode: patterns (defaults to interactive stdin)."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(_ROOT / "config" / "config.yaml"),
        help="Path to config.yaml (default: config/config.yaml).",
    )
    return parser


def _require_input(args: argparse.Namespace) -> None:
    if not args.input:
        print(
            f"[ERROR] --input is required for mode '{args.mode}'.\n"
            "        Example: python main.py --mode ocr --input input/sample.jpg",
            file=sys.stderr,
        )
        sys.exit(1)


def _resolve_input(input_path: str) -> Path:
    """Resolve --input to an absolute path and verify it exists."""
    p = Path(input_path)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.exists():
        print(f"[ERROR] Input file not found: {p}", file=sys.stderr)
        sys.exit(1)
    return p


def _get_log():
    from utils.logger import get_logger
    return get_logger("main")


if __name__ == "__main__":
    main()
