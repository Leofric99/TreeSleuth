#!/usr/bin/env python
"""
Test & Benchmark: Hybrid extraction pipeline validation.

Validates HTR and VLM models, benchmarks performance, and generates comparison reports.

Usage:
    python examples/test_hybrid_pipeline.py --validate-models
    python examples/test_hybrid_pipeline.py --benchmark path/to/image.jpg
    python examples/test_hybrid_pipeline.py --compare-methods path/to/image.jpg
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


def validate_models() -> bool:
    """Validate that HTR and VLM models can be loaded."""
    print("\n" + "=" * 80)
    print("VALIDATING HYBRID PIPELINE MODELS")
    print("=" * 80)

    try:
        print("\n1️⃣  Checking Ollama VLM availability...")
        from treesleuth.config import get_settings

        settings = get_settings()
        vlm_model = getattr(settings, "vlm_model", "qwen2.5vl")
        print(f"   Model: {vlm_model}")
        print(f"   ✓ Ollama VLM configuration found")

        print("\n2️⃣  Checking HTR model (transformers)...")
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            print("   Loading microsoft/trocr-large-handwritten...")
            processor = TrOCRProcessor.from_pretrained("microsoft/trocr-large-handwritten")
            model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-large-handwritten")
            print(f"   ✓ HTR model loaded successfully")
            print(f"     Processor: {processor.__class__.__name__}")
            print(f"     Model parameters: {model.num_parameters():,}")
        except ImportError:
            print("   ✗ transformers not installed")
            print("   Fix: pip install transformers torch pillow")
            return False
        except Exception as exc:
            print(f"   ✗ Failed to load HTR model: {exc}")
            return False

        print("\n3️⃣  Checking OpenCV for row detection...")
        try:
            import cv2

            print(f"   OpenCV version: {cv2.__version__}")
            print(f"   ✓ OpenCV available")
        except ImportError:
            print("   ✗ opencv-python not installed")
            print("   Fix: pip install opencv-python")
            return False

        print("\n✅ All models and dependencies validated!")
        return True

    except Exception as exc:
        print(f"\n❌ Validation failed: {exc}")
        logger.exception("Model validation error")
        return False


def benchmark_extraction(image_path: Path) -> None:
    """Benchmark hybrid extraction pipeline stages."""
    print("\n" + "=" * 80)
    print(f"BENCHMARKING HYBRID PIPELINE: {image_path.name}")
    print("=" * 80)

    from PIL import Image

    from treesleuth.hybrid_extraction import (
        detect_rows_by_horizontal_lines,
        extract_htr_text,
        segment_rows,
    )

    image = Image.open(image_path).convert("RGB")
    print(f"\n📊 Image specs:")
    print(f"   Size: {image.width}x{image.height} pixels")
    print(f"   Format: {image.format}")

    # Stage 1: Row Detection
    print(f"\n⏱️  Stage 1: Row Detection")
    start = time.time()
    row_bounds = detect_rows_by_horizontal_lines(image)
    stage1_time = time.time() - start
    print(f"   Detected: {len(row_bounds)} rows")
    print(f"   Time: {stage1_time:.3f}s")

    # Stage 2: Row Segmentation
    print(f"\n⏱️  Stage 2: Row Segmentation")
    start = time.time()
    segments = segment_rows(image, row_bounds)
    stage2_time = time.time() - start
    print(f"   Segmented: {len(segments)} row segments")
    print(f"   Time: {stage2_time:.3f}s")

    # Stage 3: HTR (sample first 10 rows)
    print(f"\n⏱️  Stage 3: HTR Text Recognition (first 10 rows)")
    htr_times = []
    for segment in segments[:10]:
        start = time.time()
        text = extract_htr_text(segment)
        elapsed = time.time() - start
        htr_times.append(elapsed)
    
    avg_htr_time = sum(htr_times) / len(htr_times) if htr_times else 0
    print(f"   Rows processed: {len(htr_times)}")
    print(f"   Avg time per row: {avg_htr_time:.3f}s")
    print(f"   Total time: {sum(htr_times):.3f}s")

    # Summary
    print(f"\n📈 Pipeline Summary")
    print(f"   Row Detection:   {stage1_time:.3f}s")
    print(f"   Segmentation:    {stage2_time:.3f}s")
    print(f"   HTR (10 rows):   {sum(htr_times):.3f}s ({avg_htr_time:.3f}s/row)")
    print(f"   Estimated full:  {stage1_time + stage2_time + (avg_htr_time * len(segments)):.1f}s")
    print(f"   Total rows:      {len(segments)}")

    # Per-row breakdown
    if htr_times:
        print(f"\n📊 HTR Performance Stats")
        print(f"   Min: {min(htr_times):.3f}s")
        print(f"   Max: {max(htr_times):.3f}s")
        print(f"   Avg: {avg_htr_time:.3f}s")


def compare_extraction_methods(image_path: Path) -> Tuple[dict, dict]:
    """Compare pure VLM vs hybrid extraction side-by-side."""
    print("\n" + "=" * 80)
    print(f"COMPARING EXTRACTION METHODS: {image_path.name}")
    print("=" * 80)

    from treesleuth.config import get_settings
    from treesleuth.extraction import VlmExtractor
    from treesleuth.hybrid_vlm_extractor import create_hybrid_extractor

    settings = get_settings()
    vlm_model = getattr(settings, "vlm_model", "qwen2.5vl")

    results = {
        "pure_vlm": {"success": False, "time": 0, "text_length": 0, "error": None},
        "hybrid": {"success": False, "time": 0, "text_length": 0, "error": None},
    }

    # Method 1: Pure VLM
    print("\n1️⃣  Pure VLM Extraction")
    print("-" * 80)
    try:
        extractor = VlmExtractor(settings, model=vlm_model)
        start = time.time()
        text = extractor.extract_text(image_path)
        elapsed = time.time() - start

        results["pure_vlm"]["success"] = True
        results["pure_vlm"]["time"] = elapsed
        results["pure_vlm"]["text_length"] = len(text)

        print(f"✓ Success in {elapsed:.2f}s")
        print(f"  Text length: {len(text):,} chars")
        print(f"  Preview:\n    {text[:150]}...")

    except Exception as exc:
        results["pure_vlm"]["error"] = str(exc)
        print(f"✗ Failed: {exc}")

    # Method 2: Hybrid
    print("\n2️⃣  Hybrid Extraction")
    print("-" * 80)
    try:
        extractor = create_hybrid_extractor(
            settings,
            vlm_model=vlm_model,
            target_schema={"Name": str, "Age": str, "Occupation": str, "Relation": str},
        )
        start = time.time()
        text = extractor.extract_text(image_path)
        elapsed = time.time() - start

        results["hybrid"]["success"] = True
        results["hybrid"]["time"] = elapsed
        results["hybrid"]["text_length"] = len(text)

        print(f"✓ Success in {elapsed:.2f}s")
        print(f"  Text length: {len(text):,} chars")
        print(f"  Preview:\n    {text[:150]}...")

    except Exception as exc:
        results["hybrid"]["error"] = str(exc)
        print(f"✗ Failed: {exc}")

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)

    if results["pure_vlm"]["success"] and results["hybrid"]["success"]:
        pure_time = results["pure_vlm"]["time"]
        hybrid_time = results["hybrid"]["time"]
        speedup = pure_time / hybrid_time if hybrid_time > 0 else 0

        print(f"\n⏱️  Performance")
        print(f"   Pure VLM:  {pure_time:7.2f}s  ({results['pure_vlm']['text_length']:,} chars)")
        print(f"   Hybrid:    {hybrid_time:7.2f}s  ({results['hybrid']['text_length']:,} chars)")
        print(f"   Speedup:   {speedup:7.1f}x")

        if speedup > 1:
            print(f"\n✓ Hybrid is {speedup:.1f}x faster")
        else:
            print(f"\nℹ️  Hybrid slower (expected: more processing stages)")

    else:
        print("\n❌ Could not compare (one or both methods failed)")
        if results["pure_vlm"]["error"]:
            print(f"   Pure VLM error: {results['pure_vlm']['error']}")
        if results["hybrid"]["error"]:
            print(f"   Hybrid error: {results['hybrid']['error']}")

    return results["pure_vlm"], results["hybrid"]


def main():
    parser = argparse.ArgumentParser(
        description="Test and benchmark hybrid extraction pipeline"
    )
    parser.add_argument(
        "--validate-models",
        action="store_true",
        help="Validate model availability",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        metavar="IMAGE",
        help="Benchmark pipeline stages",
    )
    parser.add_argument(
        "--compare-methods",
        type=Path,
        metavar="IMAGE",
        help="Compare pure VLM vs hybrid",
    )

    args = parser.parse_args()

    if args.validate_models:
        success = validate_models()
        sys.exit(0 if success else 1)

    elif args.benchmark:
        if not args.benchmark.exists():
            print(f"❌ File not found: {args.benchmark}")
            sys.exit(1)
        benchmark_extraction(args.benchmark)

    elif args.compare_methods:
        if not args.compare_methods.exists():
            print(f"❌ File not found: {args.compare_methods}")
            sys.exit(1)
        compare_extraction_methods(args.compare_methods)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
