## Why

Docling's OCR (its default engines) performs poorly on historical handwriting such as parish registers, census sheets and letters. Vision-Language Models can read cursive and degraded scripts far better. TreeSleuth already depends on a local Ollama service, so a local GPU-accelerated VLM served by Ollama can replace Docling OCR without sending genealogical data off the machine.

## What Changes

- Replace `DoclingExtractor` and the Docling dependency with an Ollama-based VLM extractor for PDF, JPG, JPEG, PNG, TIF and TIFF files. TXT/Markdown remain read directly.
- Render PDF pages (and multi-frame TIFFs) to images locally and send each page to the configured vision model, assembling per-page transcriptions into one text result per document.
- Let the user pick the vision (transcription) model in the dashboard from the installed local Ollama models, separately from the story-generation model, and send it with the pipeline start request.
- Add configurable VLM tuning settings (per-page timeout, page render DPI/max image dimension, transcription prompt) via environment variables with defaults; the model itself is a per-run user choice, not an env var.
- Use Ollama's own GPU acceleration; remove the PyTorch/CUDA/MPS accelerator detection and CPU-retry logic. Ollama falling back to CPU is reported, not hidden.
- Verify the selected vision model is installed before extraction starts, failing the run with an actionable message (e.g. `ollama pull ...`).
- Include the selected VLM model and prompt version in the extraction cache identity so changing them invalidates cached text.
- Update dashboard wording, README and API docs that reference OCR/Docling.
- **BREAKING**: Docling and its PyTorch-based install steps are no longer required; an Ollama vision model is now required for scanned documents. Existing extraction caches are invalidated.

## Capabilities

### New Capabilities
- `vlm-document-transcription`: Configurable local Ollama VLM pipeline that transcribes document page images into text, including model validation, page rendering, and failure reporting.

### Modified Capabilities
- `local-research-dashboard`: Vision model selection and start request.
- `research-ingestion`: Text extraction requirement, cache-key requirement, and the local/cross-platform acceleration scenarios change from Docling OCR to the Ollama VLM pipeline.

## Impact

- Code: `treesleuth/extraction.py`, `treesleuth/config.py`, `treesleuth/pipeline.py` (extractor construction, cache identity, preflight), `treesleuth/models.py` (start request), `treesleuth/main.py`, `static/app.js`/`static/index.html` (vision model dropdown, OCR wording).
- Tests: `tests/test_extraction.py`, `test_pipeline.py`, `test_cache.py`, `test_api.py` and browser tests updated to use a fake VLM client.
- Dependencies: remove `docling`; add a local PDF rasterizer (PyMuPDF) and Pillow for image handling; `ollama` already present.
- Docs: `README.md`, `docs\API.md`.
- Performance: VLM transcription is slower per page than OCR; progress reporting should be per page.
