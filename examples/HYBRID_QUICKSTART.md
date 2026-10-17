# Hybrid Extraction Quick-Start Guide

This guide shows you how to use the new hybrid OCR/HTR + VLM extraction pipeline for accurate transcription of historical documents (census records, death registers, marriage records).

## 🚀 Quick Start

### 1. Installation

The hybrid pipeline requires a few additional Python packages:

```bash
# Install HTR model dependencies
pip install transformers torch pillow opencv-python

# Verify installation
python examples/test_hybrid_pipeline.py --validate-models
```

### 2. Basic Usage

#### Option A: Use the drop-in replacement extractor

```python
from pathlib import Path
from treesleuth.config import get_settings
from treesleuth.hybrid_vlm_extractor import create_hybrid_extractor

settings = get_settings()

# Create hybrid extractor
extractor = create_hybrid_extractor(
    settings,
    vlm_model="qwen2.5vl",  # or your preferred model
    target_schema={
        "Name": str,
        "Age": str,
        "Occupation": str,
        "Birthplace": str,
    }
)

# Extract text from image
image_path = Path("path/to/census.jpg")
text = extractor.extract_text(image_path)
print(text)
```

#### Option B: Use the full hybrid pipeline directly

```python
from pathlib import Path
from treesleuth.hybrid_extraction import run_hybrid_extraction_pipeline

image_path = Path("path/to/census.jpg")

result = run_hybrid_extraction_pipeline(
    image_path,
    target_schema={
        "Name": str,
        "Age": str,
        "Occupation": str,
        "Birthplace": str,
        "Relation": str,
    },
    vlm_model="qwen2.5vl",
    htr_model="microsoft/trocr-large-handwritten",
    device="cuda",  # or "cpu" for systems without NVIDIA GPU
)

# Access structured results
print(f"Total rows: {result.metadata['total_rows']}")

for row in result.structured_rows:
    if row:
        raw_text = row.get("raw_htr_input", "")
        structured = row.get("structured_fields", {})
        flags = row.get("flags", {})
        print(f"HTR: {raw_text}")
        print(f"Structured: {structured}")
        if flags.get("ditto_expanded"):
            print("✓ Ditto marks expanded")
```

## 📊 Benchmarking & Validation

### Validate Models

Before running on real documents, verify your environment:

```bash
python examples/test_hybrid_pipeline.py --validate-models
```

This checks:
- ✓ Ollama VLM configuration
- ✓ HTR model (microsoft/trocr-large-handwritten)
- ✓ OpenCV for row detection
- ✓ All dependencies

### Benchmark a Single Image

Profile the pipeline stages on your hardware:

```bash
python examples/test_hybrid_pipeline.py --benchmark path/to/image.jpg
```

Output shows:
- Row detection time
- Segmentation time
- HTR time per row
- Estimated total time for full document

### Compare Pure VLM vs Hybrid

Benchmark both methods side-by-side:

```bash
python examples/test_hybrid_pipeline.py --compare-methods path/to/image.jpg
```

Expected output:
```
COMPARING EXTRACTION METHODS: image.jpg

1️⃣  Pure VLM Extraction
✓ Success in 350.25s
  Text length: 1,234 chars

2️⃣  Hybrid Extraction
✓ Success in 28.50s
  Text length: 4,521 chars

COMPARISON SUMMARY

⏱️  Performance
   Pure VLM:  350.25s  (1,234 chars)
   Hybrid:     28.50s  (4,521 chars)
   Speedup:    12.3x

✓ Hybrid is 12.3x faster
```

## 🔬 How It Works

### Stage 1: Row Segmentation (OpenCV)

- Detects individual rows in dense tabular documents
- Uses morphological operations to find text lines reliably
- Adds 10-15% vertical padding to preserve handwriting ascenders/descenders
- Deterministic (no hallucination)

### Stage 2: Line-Level HTR (Hugging Face Transformers)

- Extracts raw text from each row using microsoft/trocr-large-handwritten
- Provides grounded baseline text (not hallucinatory)
- Character-level accuracy for both printed and handwritten text
- Fast (0.2-0.5s per row)

### Stage 3: VLM Refinement (Ollama)

- Takes raw HTR text + visual image crop
- Validates and corrects HTR output using visual context
- Enforces structured JSON output
- Expands ditto marks ("") using previous row context
- Prevents hallucination (grounded in HTR baseline)

**Key difference from pure VLM:**
- Pure VLM looks at image alone → hallucinates, repeats patterns
- Hybrid VLM looks at grounded HTR text + image → validates, refines

## 📁 Output Format

The hybrid extractor returns structured JSON for each row:

```json
{
  "raw_htr_input": "Ada Lovelace 25 Mathematics",
  "structured_fields": {
    "Name": "Ada Lovelace",
    "Age": "25",
    "Occupation": "Mathematics"
  },
  "flags": {
    "confidence": 0.95,
    "ditto_expanded": false,
    "issues": null
  }
}
```

## 🎯 Configuration for Document Types

### Census Records

```python
census_schema = {
    "Name": str,
    "Relation": str,
    "Age": str,
    "Occupation": str,
    "Birthplace": str,
    "Condition": str,  # marital status
}

extractor = create_hybrid_extractor(
    settings,
    vlm_model="qwen2.5vl",
    target_schema=census_schema,
)
```

### Death Registers

```python
death_schema = {
    "Name": str,
    "Age": str,
    "Birthplace": str,
    "Cause": str,
    "Date": str,
}

extractor = create_hybrid_extractor(
    settings,
    vlm_model="qwen2.5vl",
    target_schema=death_schema,
)
```

### Marriage Registers

```python
marriage_schema = {
    "Groom": str,
    "Bride": str,
    "Groom Age": str,
    "Bride Age": str,
    "Date": str,
    "Witness1": str,
    "Witness2": str,
}

extractor = create_hybrid_extractor(
    settings,
    vlm_model="qwen2.5vl",
    target_schema=marriage_schema,
)
```

## 🐛 Troubleshooting

### "No module named transformers"

Install the HTR dependencies:
```bash
pip install transformers torch pillow opencv-python
```

### "CUDA out of memory"

The HTR model uses GPU when available. If you hit memory issues:

```python
result = run_hybrid_extraction_pipeline(
    image_path,
    device="cpu",  # Force CPU for HTR stage
    vlm_model="qwen2.5vl",
)
```

### "Rows not being detected"

Adjust row detection parameters:

```python
from treesleuth.hybrid_extraction import detect_rows_by_horizontal_lines

# Existing row_bounds = detect_rows_by_horizontal_lines(image)
# New, more sensitive:
row_bounds = detect_rows_by_horizontal_lines(
    image,
    threshold=150,  # Lower = more sensitive
    min_row_height=15,  # Smaller rows
    padding_percent=0.15,
)
```

### "VLM refinement too slow"

The VLM step with context adds processing time. For speed optimization:

```python
# Skip VLM refinement, use raw HTR only
from treesleuth.hybrid_extraction import batch_extract_htr

segments = segment_rows(image, row_bounds)
htr_results = batch_extract_htr(segments)
```

## 📚 Examples

### Run interactive demo

```bash
python examples/hybrid_extraction_demo.py path/to/image.jpg
```

This runs all 4 demo scenarios:
1. Row segmentation visualization
2. HTR-only output
3. Full hybrid extraction
4. Pure VLM vs hybrid comparison

### Use hybrid extraction in your app

See `HYBRID_EXTRACTION_INTEGRATION.md` for three detailed integration patterns:

1. **Direct Function Usage** - Call `run_hybrid_extraction_pipeline()` directly
2. **Drop-in Replacement** - Use `HybridVlmExtractor` as a replacement for `VlmExtractor`
3. **Conditional Hybrid Mode** - Use hybrid for dense documents, pure VLM for others

## ⏱️ Performance Expectations

On RTX 4070 Super (12GB VRAM):

| Operation | Time |
|-----------|------|
| Row detection | 0.1-0.2s |
| Segmentation | 0.5-1s |
| HTR (per row) | 0.2-0.5s |
| VLM refinement (per row) | 0.3-1s |
| **Total (census page, ~35 rows)** | **25-40s** |
| Pure VLM (same document) | 300-500s |

**Speedup: 8-20x faster than pure VLM**

## 📖 Related Files

- **Core Implementation:** [`treesleuth/hybrid_extraction.py`](../treesleuth/hybrid_extraction.py)
- **Integration Layer:** [`treesleuth/hybrid_vlm_extractor.py`](../treesleuth/hybrid_vlm_extractor.py)
- **Integration Guide:** [`HYBRID_EXTRACTION_INTEGRATION.md`](../HYBRID_EXTRACTION_INTEGRATION.md)
- **Demo Script:** [`examples/hybrid_extraction_demo.py`](./hybrid_extraction_demo.py)
- **Test Script:** [`examples/test_hybrid_pipeline.py`](./test_hybrid_pipeline.py)

---

**Next Steps:**
1. ✓ Validate models: `python examples/test_hybrid_pipeline.py --validate-models`
2. ✓ Try demo: `python examples/hybrid_extraction_demo.py path/to/image.jpg`
3. ✓ Integrate into app following `HYBRID_EXTRACTION_INTEGRATION.md`
