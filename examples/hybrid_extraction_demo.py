#!/usr/bin/env python
"""
Demo: Hybrid OCR/HTR + VLM extraction on historical documents.

This script shows how to use the hybrid extraction pipeline to accurately
transcribe dense tabular documents like census records and death registers.

Usage:
    python examples/hybrid_extraction_demo.py path/to/image.jpg
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_basic_hybrid_extraction(image_path: Path) -> None:
    """Run hybrid extraction on a single image."""
    from treesleuth.hybrid_extraction import run_hybrid_extraction_pipeline

    logger.info(f"Running hybrid extraction on: {image_path}")

    result = run_hybrid_extraction_pipeline(
        image_path,
        target_schema={
            "Name": str,
            "Age": str,
            "Occupation": str,
            "Birthplace": str,
        },
        vlm_model="qwen2.5vl",
        htr_model="microsoft/trocr-large-handwritten",
        device="cuda",
    )

    print("\n" + "=" * 80)
    print("HYBRID EXTRACTION RESULTS")
    print("=" * 80)

    print(f"\n📄 Document: {result.page_image_path.name}")
    print(f"📊 Total rows detected: {result.metadata['total_rows']}")

    print("\n" + "-" * 80)
    print("RAW HTR OUTPUT (Baseline Text)")
    print("-" * 80)
    print(result.raw_full_page_text)

    print("\n" + "-" * 80)
    print("STRUCTURED & REFINED ROWS")
    print("-" * 80)

    for idx, row_data in enumerate(result.structured_rows, 1):
        if row_data:
            print(f"\nRow {idx}:")
            print(f"  Raw HTR: {row_data.get('raw_htr_input', '[MISSING]')}")
            print(f"  Structured: {json.dumps(row_data.get('structured_fields', {}), indent=4)}")
            flags = row_data.get("flags", {})
            if flags.get("issues"):
                print(f"  ⚠️  Issues: {flags['issues']}")
            if flags.get("ditto_expanded"):
                print(f"  ✓ Ditto marks expanded")
            print(f"  Confidence: {flags.get('confidence', 'N/A')}")


def demo_row_segmentation(image_path: Path) -> None:
    """Visualize row segmentation."""
    from PIL import Image, ImageDraw

    from treesleuth.hybrid_extraction import detect_rows_by_horizontal_lines, segment_rows

    logger.info(f"Testing row segmentation on: {image_path}")

    image = Image.open(image_path).convert("RGB")
    row_bounds = detect_rows_by_horizontal_lines(image)

    print(f"\n🔍 Row Detection Results for {image_path.name}")
    print(f"   Detected {len(row_bounds)} rows")
    for idx, (y_top, y_bottom) in enumerate(row_bounds[:5], 1):  # Show first 5
        height = y_bottom - y_top
        print(f"   Row {idx}: y={y_top}-{y_bottom} (height={height}px)")

    # Optional: Save visualization
    vis_image = image.copy()
    draw = ImageDraw.Draw(vis_image)
    for y_top, y_bottom in row_bounds:
        draw.rectangle([(0, y_top), (image.width, y_bottom)], outline="red", width=2)

    vis_path = image_path.parent / f"{image_path.stem}_rows_detected.png"
    vis_image.save(vis_path)
    logger.info(f"✓ Saved visualization: {vis_path}")


def demo_htr_only(image_path: Path) -> None:
    """Run just the HTR stage (no row segmentation, no VLM)."""
    from PIL import Image

    from treesleuth.hybrid_extraction import (
        detect_rows_by_horizontal_lines,
        extract_htr_text,
        segment_rows,
    )

    logger.info(f"Running HTR-only on: {image_path}")

    image = Image.open(image_path).convert("RGB")
    row_bounds = detect_rows_by_horizontal_lines(image)
    segments = segment_rows(image, row_bounds)

    print(f"\n📝 HTR-Only Output (Raw Text Recognition)")
    print(f"   Image: {image_path.name}")
    print(f"   Rows: {len(segments)}")
    print()

    for segment in segments[:5]:  # Show first 5 rows
        text = extract_htr_text(segment)
        print(f"Row {segment.row_index:2d}: {text}")


def demo_compare_methods(image_path: Path) -> None:
    """Compare pure-VLM vs hybrid extraction."""
    import time

    from treesleuth.config import get_settings
    from treesleuth.extraction import VlmExtractor
    from treesleuth.hybrid_vlm_extractor import create_hybrid_extractor

    logger.info(f"Comparing extraction methods on: {image_path}")

    settings = get_settings()

    print("\n⚖️  COMPARISON: Pure VLM vs Hybrid Extraction")
    print("=" * 80)

    # Method 1: Pure VLM
    print("\n1️⃣  Pure VLM Method (Original)")
    print("-" * 80)
    pure_vlm = VlmExtractor(settings, model="qwen2.5vl")
    start = time.time()
    try:
        pure_text = pure_vlm.extract_text(image_path)
        pure_time = time.time() - start
        print(f"✓ Completed in {pure_time:.2f}s")
        print(f"  Text length: {len(pure_text)} chars")
        print(f"  Preview: {pure_text[:200]}...")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
        pure_text = None
        pure_time = None

    # Method 2: Hybrid
    print("\n2️⃣  Hybrid Extraction Method (New)")
    print("-" * 80)
    hybrid = create_hybrid_extractor(
        settings,
        vlm_model="qwen2.5vl",
        target_schema={"Name": str, "Age": str, "Occupation": str},
    )
    start = time.time()
    try:
        hybrid_text = hybrid.extract_text(image_path)
        hybrid_time = time.time() - start
        print(f"✓ Completed in {hybrid_time:.2f}s")
        print(f"  Text length: {len(hybrid_text)} chars")
        print(f"  Preview: {hybrid_text[:200]}...")
    except Exception as exc:
        print(f"✗ Failed: {exc}")
        hybrid_text = None
        hybrid_time = None

    # Summary
    if pure_time and hybrid_time:
        print("\n📊 Summary")
        print("-" * 80)
        speedup = pure_time / hybrid_time
        print(f"Pure VLM:  {pure_time:.2f}s")
        print(f"Hybrid:    {hybrid_time:.2f}s")
        print(f"Speedup:   {speedup:.1f}x faster" if speedup > 1 else f"Note: Hybrid slower (more processing)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExamples:")
        print("  python examples/hybrid_extraction_demo.py ./data/census.jpg")
        print("  python examples/hybrid_extraction_demo.py ./data/register.jpg")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"❌ File not found: {image_path}")
        sys.exit(1)

    print("🚀 Hybrid Extraction Demo\n")

    # Run all demos
    try:
        demo_row_segmentation(image_path)
        demo_htr_only(image_path)
        demo_basic_hybrid_extraction(image_path)
        demo_compare_methods(image_path)
    except Exception as exc:
        logger.exception("Demo failed")
        sys.exit(1)

    print("\n✅ Demo complete!")
