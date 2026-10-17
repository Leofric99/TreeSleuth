# Quick Start: VLM Pipeline

## 5-Minute Setup

### 1. Ensure Ollama is Running
```bash
ollama serve  # In one terminal
```

### 2. Pull Required Models
```bash
ollama pull qwen2.5-vl:7b  # Vision model for document transcription
ollama pull mistral         # Text model for contradiction checking
```

### 3. Set Environment Variables (Optional)
```bash
# Default values work for RTX 4070 Super (12GB VRAM)
export TREESLEUTH_VLM_MODEL="qwen2.5-vl:7b"
export TREESLEUTH_TEXT_LLM_MODEL="mistral"
export TREESLEUTH_VLM_CTX_WINDOW=4096  # CRITICAL: keeps GPU loaded
```

## Usage Examples

### Basic: Process Single Document
```python
from pathlib import Path
from treesleuth.vlm_pipeline import process_genealogy_document

result = process_genealogy_document(
    image_path=Path("grandma_letter.jpg"),
    gedcom_fields={
        "individual_name": "Mary Smith",
        "birth_date": "1850-03-15",
        "birth_location": "New York"
    }
)

print("Transcription:", result["transcription"])
print("Issues Found:", result["contradictions"]["issues"])
```

### Advanced: Custom Configuration
```python
from treesleuth.vlm_pipeline import transcribe_with_vlm

# Just transcription (no contradiction checking)
text = transcribe_with_vlm(
    image_path=Path("document.jpg"),
    vlm_model="qwen2.5-vl:7b",
    ctx_window=4096,  # ← CRITICAL for 12GB GPU
    timeout_seconds=600
)
print(text)
```

### Batch Processing
```python
from pathlib import Path
from treesleuth.vlm_pipeline import process_with_settings
from treesleuth.config import get_settings

settings = get_settings()
documents = Path("genealogy_docs").glob("*.jpg")

results = []
for doc in documents:
    result = process_with_settings(
        image_path=doc,
        gedcom_fields={...},
        settings=settings
    )
    results.append(result)
    print(f"{doc.name}: {'✓' if result['success'] else '✗'}")
```

## Expected Performance

| Document Type | Expected Time | VRAM Usage |
|---|---|---|
| Simple letter (1 page) | 8-12s | ~8GB |
| Census record (dense) | 20-35s | ~9GB |
| Large form (multi-page) | 30-50s | ~10GB |
| Very complex (exceptional) | 50-60s (may timeout) | ~11GB |

**Note:** Times vary by document image size, content density, and Ollama load.

## Troubleshooting

### Issue: Processing takes 300+ seconds (was slow before fix)
**Solution:** Verify `num_ctx` is being passed correctly
```python
# Check logs for:
# "options": {"num_ctx": 4096}  ← Must see this
```

### Issue: "CUDA out of memory" error
**Solution:** Reduce context window
```bash
export TREESLEUTH_VLM_CTX_WINDOW=2048  # More aggressive
```

### Issue: Inconsistent quality
**Solution:** Try different model or adjust prompt
```bash
# Faster but lighter model
export TREESLEUTH_VLM_MODEL="llama2-vision"

# Or customize the transcription prompt
```

## Key Concepts

### The Magic Parameter: `num_ctx=4096`
This single parameter is why processing is now fast:
- **Without it:** Ollama allocates 32K context → VRAM overflow → CPU fallback → 300+ seconds
- **With it:** Ollama allocates 4K context → Stays on GPU → 8-35 seconds

### Two-Stage Architecture
1. **Stage 1 (Fast):** Vision model reads handwriting → raw text
2. **Stage 2 (Smart):** Text model checks for contradictions vs family tree

You can use Stage 1 independently if you only need transcription!

### Grayscale Conversion
Automatically applied during preprocessing to:
- Reduce data channels (3 → 1)
- Preserve handwriting contrast
- Speed up GPU inference

## Configuration Options

| Env Variable | Default | Purpose |
|---|---|---|
| `TREESLEUTH_VLM_MODEL` | `qwen2.5-vl:7b` | Vision model for transcription |
| `TREESLEUTH_TEXT_LLM_MODEL` | `mistral` | Text model for contradictions |
| `TREESLEUTH_VLM_CTX_WINDOW` | `4096` | **CRITICAL:** Context size for GPU memory |
| `TREESLEUTH_VLM_TIMEOUT_SECONDS` | `600` | Max seconds per document |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API endpoint |

## Model Recommendations

### For 12GB VRAM (RTX 4070 Super):
- **VLM:** `qwen2.5-vl:7b` (default) - balanced quality/speed
- **Text LLM:** `mistral` - fast reasoning
- **Context:** `4096` tokens (critical)

### For 24GB+ VRAM (RTX 4090, A6000):
- **VLM:** `qwen2.5-vl:7b` or `yi-vl:34b` (larger, better)
- **Context:** `8192` tokens (more permissive)

### For Fastest Processing:
- **VLM:** `llama2-vision` - ~3x faster, slightly lower quality
- **Context:** `2048` tokens (aggressive)

## Example: Full Workflow

```python
#!/usr/bin/env python3
"""Process genealogy documents with VLM pipeline."""

import json
from pathlib import Path
from treesleuth.vlm_pipeline import process_with_settings
from treesleuth.config import get_settings

def process_folder(folder_path: Path, gedcom_file: Path) -> None:
    """Process all JPGs in folder."""
    settings = get_settings()
    
    # Load GEDCOM data
    with open(gedcom_file) as f:
        gedcom_data = json.load(f)
    
    # Process each document
    for image_path in sorted(folder_path.glob("*.jpg")):
        print(f"\nProcessing {image_path.name}...")
        
        individual_data = gedcom_data.get(image_path.stem, {})
        
        result = process_with_settings(
            image_path=image_path,
            gedcom_fields=individual_data,
            settings=settings
        )
        
        # Show results
        if result["success"]:
            print(f"  ✓ Transcribed {len(result['transcription'])} characters")
            
            if result["contradictions"]:
                contradictions = result["contradictions"]
                if contradictions["contradictions_found"]:
                    print(f"  ⚠ Found {len(contradictions['issues'])} issues:")
                    for issue in contradictions["issues"]:
                        print(f"    - {issue['description']}")
                else:
                    print("  ✓ No contradictions found")
        else:
            print(f"  ✗ Failed: {result['errors'][0]}")
        
        # Save results
        output_path = image_path.with_suffix(".json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

if __name__ == "__main__":
    process_folder(
        Path("./genealogy_docs"),
        Path("./gedcom_data.json")
    )
```

## Getting Help

Check these resources:
- **Full documentation:** `docs/VLM_PIPELINE.md`
- **Module docstrings:** `python -c "from treesleuth.vlm_pipeline import process_genealogy_document; help(process_genealogy_document)"`
- **Test examples:** `tests/test_vlm_pipeline.py`
- **Enable debug logging:** `logging.basicConfig(level=logging.DEBUG)`

