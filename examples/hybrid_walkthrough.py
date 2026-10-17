#!/usr/bin/env python
"""
Step-by-step hybrid extraction walkthrough.

This script walks through each stage of the hybrid extraction pipeline
with detailed logging and visualization.

Run with: python examples/hybrid_walkthrough.py path/to/image.jpg
"""

import json
import logging
import sys
from pathlib import Path

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Silence verbose libraries
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("cv2").setLevel(logging.WARNING)


def print_section(title: str, level: int = 1) -> None:
    """Print a formatted section header."""
    char = "=" if level == 1 else "-" if level == 2 else " "
    width = 80 if level == 1 else 70
    print(f"\n{char * width}")
    print(f"{title:^{width}}")
    print(f"{char * width}\n")


def step_1_load_image(image_path: Path) -> None:
    """Load and display image information."""
    from PIL import Image

    print_section("STEP 1: Load Image", level=1)

    image = Image.open(image_path).convert("RGB")

    print(f"📄 Image File: {image_path.name}")
    print(f"📊 Size: {image.width}×{image.height} pixels")
    print(f"📝 Format: {image.format}")
    print(f"🎨 Mode: {image.mode}")

    # Calculate image info
    pixel_count = image.width * image.height
    size_mb = image_path.stat().st_size / (1024 * 1024)

    print(f"💾 File size: {size_mb:.2f} MB")
    print(f"📐 Pixel count: {pixel_count:,}")

    aspect_ratio = image.width / image.height
    print(f"📏 Aspect ratio: {aspect_ratio:.2f}:1")

    return image


def step_2_preprocessing(image) -> None:
    """Apply image preprocessing."""
    from PIL import Image, ImageOps

    print_section("STEP 2: Image Preprocessing", level=1)

    # Convert to grayscale
    print("🔄 Converting to grayscale...")
    gray = ImageOps.grayscale(image)
    print(f"   ✓ Now grayscale ({gray.mode} mode)")

    # Check contrast
    stat = ImageOps.Stat(gray)
    mean = stat.mean[0]
    stddev = stat.stddev[0]
    print(f"\n📊 Contrast analysis:")
    print(f"   Mean brightness: {mean:.1f}/255")
    print(f"   Std deviation: {stddev:.1f}")

    if stddev < 20:
        print("   ⚠️  Low contrast - may affect OCR quality")
    else:
        print("   ✓ Good contrast for OCR")

    return gray


def step_3_row_detection(image) -> list:
    """Detect rows in the image."""
    print_section("STEP 3: Detect Rows by Horizontal Lines", level=1)

    from treesleuth.hybrid_extraction import detect_rows_by_horizontal_lines

    print("🔍 Scanning for horizontal text lines...")
    row_bounds = detect_rows_by_horizontal_lines(image)

    print(f"\n📊 Detection Results:")
    print(f"   Total rows found: {len(row_bounds)}")

    if row_bounds:
        heights = [y2 - y1 for y1, y2 in row_bounds]
        avg_height = sum(heights) / len(heights)
        min_height = min(heights)
        max_height = max(heights)

        print(f"   Row height range: {min_height}-{max_height}px")
        print(f"   Average height: {avg_height:.1f}px")

        print(f"\n   First 5 rows:")
        for i, (y1, y2) in enumerate(row_bounds[:5], 1):
            height = y2 - y1
            print(f"     Row {i}: y={y1:4d}-{y2:4d} (height={height:3d}px)")

        if len(row_bounds) > 5:
            print(f"   ... and {len(row_bounds) - 5} more rows")

        # Estimate OCR time
        htr_time_per_row = 0.35  # seconds (average)
        estimated_time = len(row_bounds) * htr_time_per_row
        print(f"\n⏱️  Estimated HTR time: {estimated_time:.1f}s ({htr_time_per_row}s/row)")

    return row_bounds


def step_4_segment_rows(image, row_bounds: list):
    """Segment rows from image."""
    print_section("STEP 4: Segment Rows", level=1)

    from treesleuth.hybrid_extraction import segment_rows

    print("✂️  Segmenting rows with 10-15% padding...")
    segments = segment_rows(image, row_bounds)

    print(f"\n📊 Segmentation Results:")
    print(f"   Total segments: {len(segments)}")

    if segments:
        print(f"\n   First 3 segments:")
        for seg in segments[:3]:
            print(f"     Row {seg.row_index}: {seg.image.width}×{seg.image.height}px")
            print(f"       Bounds: y={seg.row_bounds[0]}-{seg.row_bounds[1]}")
            print(f"       Padding: {seg.padding_percent*100:.0f}%")

    return segments


def step_5_htr_recognition(segments: list) -> dict:
    """Extract text using HTR model."""
    print_section("STEP 5: Handwritten Text Recognition (HTR)", level=1)

    from treesleuth.hybrid_extraction import extract_htr_text

    print(f"🤖 Running HTR on {min(5, len(segments))} rows (sample)...")
    print("   Loading microsoft/trocr-large-handwritten...")

    htr_results = {}
    for idx, segment in enumerate(segments[:5]):
        text = extract_htr_text(segment)
        htr_results[segment.row_index] = text
        status = "✓" if text.strip() else "⚠️ (empty)"
        print(f"   Row {segment.row_index}: {status} '{text[:60]}...'")

    print(f"\n✓ HTR completed on {len(htr_results)} sample rows")

    return htr_results


def step_6_vlm_refinement(image, row_bounds: list, htr_results: dict) -> None:
    """Refine HTR output with VLM."""
    print_section("STEP 6: VLM Refinement (Schema Enforcement)", level=1)

    from treesleuth.hybrid_extraction import segment_rows, refine_htr_with_vlm

    target_schema = {
        "Name": str,
        "Age": str,
        "Occupation": str,
    }

    print(f"📋 Target Schema:")
    for field, field_type in target_schema.items():
        print(f"   - {field}: {field_type.__name__}")

    segments = segment_rows(image, row_bounds)

    print(f"\n🔄 Refining HTR output with VLM (sample)...")
    print("   Note: This calls Ollama, will take a few seconds per row...")

    # Process first 2 rows as sample
    for segment in segments[:2]:
        raw_text = htr_results.get(segment.row_index, "")
        if not raw_text.strip():
            continue

        print(f"\n   Row {segment.row_index}:")
        print(f"   Raw HTR: '{raw_text}'")

        try:
            refined = refine_htr_with_vlm(
                raw_text,
                segment.image,
                target_schema,
                vlm_model="qwen2.5vl",
                previous_row_context={},
            )

            print(f"   Refined JSON:")
            for field, value in refined.get("structured_fields", {}).items():
                print(f"     {field}: {value}")

            flags = refined.get("flags", {})
            if flags.get("confidence"):
                print(f"   Confidence: {flags['confidence']:.1%}")
            if flags.get("issues"):
                print(f"   Issues: {flags['issues']}")

        except Exception as exc:
            print(f"   ✗ Refinement failed: {exc}")


def step_7_full_pipeline(image_path: Path) -> None:
    """Run complete hybrid pipeline."""
    print_section("STEP 7: Full Hybrid Pipeline", level=1)

    from treesleuth.hybrid_extraction import run_hybrid_extraction_pipeline

    print("🚀 Running complete hybrid extraction pipeline...")
    print("   This will process ALL rows end-to-end.\n")

    result = run_hybrid_extraction_pipeline(
        image_path,
        target_schema={
            "Name": str,
            "Age": str,
            "Occupation": str,
        },
        vlm_model="qwen2.5vl",
        htr_model="microsoft/trocr-large-handwritten",
        device="cuda",
    )

    print(f"\n✓ Pipeline completed successfully!\n")
    print(f"📊 Results Summary:")
    print(f"   Total rows processed: {result.metadata['total_rows']}")
    print(f"   Rows with valid output: {sum(1 for r in result.structured_rows if r)}")
    print(f"   Full page text: {len(result.raw_full_page_text):,} chars\n")

    print(f"📄 Full Page Raw HTR Output:")
    print(result.raw_full_page_text)

    print(f"\n📋 Structured Rows (JSON format):")
    for idx, row_data in enumerate(result.structured_rows[:3], 1):  # Show first 3
        if row_data:
            print(f"\nRow {idx}:")
            print(json.dumps(row_data, indent=2))

    if len(result.structured_rows) > 3:
        print(f"\n... and {len(result.structured_rows) - 3} more rows")


def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/hybrid_walkthrough.py path/to/image.jpg")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"❌ File not found: {image_path}")
        sys.exit(1)

    print("\n" + "🚀 " * 20)
    print("HYBRID EXTRACTION PIPELINE WALKTHROUGH")
    print("🚀 " * 20)

    # Run each step
    try:
        image = step_1_load_image(image_path)
        gray_image = step_2_preprocessing(image)
        row_bounds = step_3_row_detection(gray_image)

        if not row_bounds:
            print("❌ No rows detected. Image may not be a table document.")
            sys.exit(1)

        segments = step_4_segment_rows(gray_image, row_bounds)
        htr_results = step_5_htr_recognition(segments)
        step_6_vlm_refinement(gray_image, row_bounds, htr_results)
        step_7_full_pipeline(image_path)

        print("\n" + "✅ " * 20)
        print("WALKTHROUGH COMPLETE!")
        print("✅ " * 20 + "\n")

    except Exception as exc:
        logger.exception("Walkthrough failed")
        print(f"\n❌ Error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
