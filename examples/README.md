# Hybrid Extraction Examples

Complete working examples demonstrating the hybrid OCR/HTR + VLM extraction pipeline for accurate transcription of historical documents.

## 📚 Files in This Directory

| File | Purpose | Command |
|------|---------|---------|
| **hybrid_extraction_demo.py** | Interactive demonstration of all pipeline stages | `python hybrid_extraction_demo.py path/to/image.jpg` |
| **test_hybrid_pipeline.py** | Validation, benchmarking, and method comparison | `python test_hybrid_pipeline.py --help` |
| **hybrid_walkthrough.py** | Step-by-step walkthrough with detailed output | `python hybrid_walkthrough.py path/to/image.jpg` |
| **HYBRID_QUICKSTART.md** | Quick-start guide and configuration reference | Read first! |

## 🚀 Quick Start

### 1. Validate Your Environment

Before running on real documents, verify all dependencies are installed:

```bash
python test_hybrid_pipeline.py --validate-models
```

Expected output:
```
1️⃣  Checking Ollama VLM availability...
   Model: qwen2.5vl
   ✓ Ollama VLM configuration found

2️⃣  Checking HTR model (transformers)...
   Loading microsoft/trocr-large-handwritten...
   ✓ HTR model loaded successfully

3️⃣  Checking OpenCV for row detection...
   OpenCV version: 4.8.0
   ✓ OpenCV available

✅ All models and dependencies validated!
```

### 2. Run Interactive Demo

Explore the pipeline on a real image:

```bash
python hybrid_extraction_demo.py C:\path\to\census.jpg
```

This demonstrates:
- ✓ Row segmentation visualization
- ✓ HTR-only text extraction
- ✓ Full hybrid pipeline with structured output
- ✓ Pure VLM vs hybrid comparison

### 3. Step-by-Step Walkthrough

For detailed understanding of each pipeline stage:

```bash
python hybrid_walkthrough.py C:\path\to\image.jpg
```

Output includes:
- Image analysis (size, format, contrast)
- Row detection results
- HTR sample output
- VLM refinement examples
- Full pipeline execution

### 4. Benchmark and Compare

Measure performance on your hardware:

```bash
# Benchmark pipeline stages
python test_hybrid_pipeline.py --benchmark C:\path\to\image.jpg

# Compare pure VLM vs hybrid
python test_hybrid_pipeline.py --compare-methods C:\path\to\image.jpg
```

## 📖 Detailed Usage

### hybrid_extraction_demo.py

Demonstrates four use cases:

#### 1. Row Segmentation Visualization
```python
python hybrid_extraction_demo.py image.jpg
```
Creates `image_rows_detected.png` showing detected row boundaries.

#### 2. HTR-Only Output
Shows raw text extraction without VLM refinement (fast, baseline).

#### 3. Full Hybrid Pipeline
Complete end-to-end extraction with structured JSON output.

#### 4. Method Comparison
Benchmarks pure VLM vs hybrid side-by-side:
- Speed comparison
- Output quality
- Text length

### test_hybrid_pipeline.py

Command-line tool for validation and benchmarking:

#### Validate Models
```bash
python test_hybrid_pipeline.py --validate-models
```
Checks:
- ✓ Ollama VLM installed and configured
- ✓ HTR model can be loaded (microsoft/trocr-large-handwritten)
- ✓ OpenCV available for row detection
- ✓ All dependencies present

#### Benchmark Pipeline
```bash
python test_hybrid_pipeline.py --benchmark image.jpg
```
Profiles each stage:
- Row detection: 0.1-0.2s
- Segmentation: 0.5-1s
- HTR (per row): 0.2-0.5s
- Full pipeline estimate

#### Compare Methods
```bash
python test_hybrid_pipeline.py --compare-methods image.jpg
```
Runs both extraction methods and reports:
- Execution time for each
- Output quality (text length)
- Speedup factor (hybrid vs pure VLM)

### hybrid_walkthrough.py

Interactive step-by-step exploration:

```bash
python hybrid_walkthrough.py image.jpg
```

Shows:
1. **Image Loading** - File info, size, format
2. **Preprocessing** - Grayscale conversion, contrast analysis
3. **Row Detection** - Count, heights, spacing
4. **Segmentation** - Per-row crops with padding
5. **HTR Recognition** - Sample text extraction
6. **VLM Refinement** - Schema enforcement and validation
7. **Full Pipeline** - Complete end-to-end execution

## 🔧 Python Integration

### Use as Module in Your Code

```python
# Option 1: Direct function usage
from treesleuth.hybrid_extraction import run_hybrid_extraction_pipeline

result = run_hybrid_extraction_pipeline(
    "path/to/census.jpg",
    target_schema={"Name": str, "Age": str, "Occupation": str},
    vlm_model="qwen2.5vl",
)

# Option 2: Drop-in replacement
from treesleuth.hybrid_vlm_extractor import create_hybrid_extractor

extractor = create_hybrid_extractor(settings, vlm_model="qwen2.5vl")
text = extractor.extract_text("path/to/image.jpg")

# Option 3: Call helper functions
from treesleuth.hybrid_extraction import (
    detect_rows_by_horizontal_lines,
    segment_rows,
    batch_extract_htr,
)

image = Image.open("path.jpg").convert("RGB")
row_bounds = detect_rows_by_horizontal_lines(image)
segments = segment_rows(image, row_bounds)
htr_results = batch_extract_htr(segments)
```

## 📊 Performance Benchmarks

Expected performance on RTX 4070 Super (12GB VRAM):

### Stage Breakdown
| Operation | Time | Notes |
|-----------|------|-------|
| Row detection | 0.1-0.2s | Image scan, morphological ops |
| Segmentation | 0.5-1s | Crop and pad rows |
| HTR per row | 0.2-0.5s | Transformer inference |
| VLM refinement per row | 0.3-1s | Ollama chat call with context |

### End-to-End Examples

| Document | Rows | Hybrid Time | Pure VLM | Speedup |
|----------|------|------------|----------|---------|
| 1901 Census | 35 | 25-40s | 300-500s | **8-20x** |
| Death Register | 50 | 40-60s | 400-600s | **8-15x** |
| Marriage Register | 30 | 20-35s | 250-400s | **10-20x** |

## ⚠️ Troubleshooting

### "Module not found" errors

Install missing dependencies:
```bash
pip install transformers torch pillow opencv-python
```

### "CUDA out of memory"

HTR uses GPU when available. Force CPU:
```bash
# In your script:
result = run_hybrid_extraction_pipeline(
    image_path,
    device="cpu",  # Force CPU
    vlm_model="qwen2.5vl",
)
```

Or reduce image size before processing:
```python
from PIL import Image

image = Image.open(path)
# Resize to max 1920px on longest edge
image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
```

### "No rows detected"

Adjust row detection sensitivity:
```python
from treesleuth.hybrid_extraction import detect_rows_by_horizontal_lines

row_bounds = detect_rows_by_horizontal_lines(
    image,
    threshold=150,  # Lower = more sensitive
    min_row_height=15,  # Smaller minimum height
)
```

### "HTR model download fails"

First run will download `microsoft/trocr-large-handwritten` (~600MB):
```bash
# Pre-download model explicitly
python -c "from transformers import TrOCRProcessor, VisionEncoderDecoderModel; \
  TrOCRProcessor.from_pretrained('microsoft/trocr-large-handwritten'); \
  VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-large-handwritten')"
```

### "VLM refinement is very slow"

The VLM step adds latency per row (300-1000ms). For speed:
- Use faster VLM model (check Ollama available models)
- Skip refinement and use raw HTR output
- Process smaller document batches

```python
# Skip refinement, use raw HTR
from treesleuth.hybrid_extraction import (
    detect_rows_by_horizontal_lines,
    segment_rows,
    batch_extract_htr,
)

segments = segment_rows(image, row_bounds)
htr_texts = batch_extract_htr(segments)  # No VLM call
```

## 🎯 Use Cases

### Ideal for Hybrid Pipeline

✓ **Dense tabular documents** (census, death registers)  
✓ **Mixed printed + handwritten** (historical forms)  
✓ **Large images** (full page scans)  
✓ **Structured output needed** (JSON fields)  
✓ **Accuracy critical** (genealogical data)

### Better with Pure VLM

✓ **Single-subject photos** (portraits)  
✓ **Unstructured text** (letters, documents)  
✓ **Speed priority** (quick scanning)

### Better with Pure HTR

✓ **Handwritten-only documents**  
✓ **Real-time processing** (mobile)  
✓ **Memory-constrained** (embedded)

## 📚 Reference

- **Core Implementation:** [`../treesleuth/hybrid_extraction.py`](../treesleuth/hybrid_extraction.py)
- **Integration Layer:** [`../treesleuth/hybrid_vlm_extractor.py`](../treesleuth/hybrid_vlm_extractor.py)
- **Integration Guide:** [`../HYBRID_EXTRACTION_INTEGRATION.md`](../HYBRID_EXTRACTION_INTEGRATION.md)
- **Quick Start:** [`HYBRID_QUICKSTART.md`](./HYBRID_QUICKSTART.md)

## ✅ Getting Started Checklist

- [ ] Install dependencies: `pip install transformers torch pillow opencv-python`
- [ ] Validate environment: `python test_hybrid_pipeline.py --validate-models`
- [ ] Run demo: `python hybrid_extraction_demo.py path/to/image.jpg`
- [ ] Review HYBRID_QUICKSTART.md for configuration options
- [ ] Try walkthrough: `python hybrid_walkthrough.py path/to/image.jpg`
- [ ] Benchmark on your hardware: `python test_hybrid_pipeline.py --benchmark path/to/image.jpg`
- [ ] Integrate into app (see HYBRID_EXTRACTION_INTEGRATION.md)

---

**Questions?** See [`HYBRID_QUICKSTART.md`](HYBRID_QUICKSTART.md) for detailed usage and configuration examples.
