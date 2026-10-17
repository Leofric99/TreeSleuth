## 1. Configuration and dependencies

- [x] 1.1 Add VLM tuning settings (host, timeout, max image side, PDF DPI, prompt override) with validation to `treesleuth\config.py` and env loading
- [x] 1.2 In `requirements.txt` remove `docling`, add `pymupdf` and `pillow`
- [x] 1.3 Add optional `vision_model` to `PipelineStartRequest` in `treesleuth\models.py` and to the run record; reject start when scanned documents exist and it is missing

## 2. VLM extractor

- [x] 2.1 In `treesleuth\extraction.py` add page rendering (PyMuPDF for PDFs, Pillow for images/multi-frame TIFF, downscale, PNG bytes in memory)
- [x] 2.2 Implement `VlmExtractor` with injectable client/renderer, transcription prompt, per-page calls, page-marked joining, empty-result and per-page error handling, and retained TXT/MD direct read
- [x] 2.3 Add VLM preflight (model installed, Ollama reachable) and one-time GPU residency warning via Ollama `ps`
- [x] 2.4 Remove `DoclingExtractor`, torch accelerator detection, and CPU-retry code

## 3. Pipeline integration

- [x] 3.1 Build a `VlmExtractor` per run from settings and the selected vision model in `treesleuth\pipeline.py`; run preflight before extraction only when non-text documents exist
- [x] 3.2 Derive cache identity from version, model, prompt hash, DPI and max side
- [x] 3.3 Emit per-page progress events and failure messages naming document and page
- [x] 3.4 Update `treesleuth\main.py` wiring if it references the old extractor

## 4. UI and docs

- [x] 4.1 Add a "Vision model (transcription)" dropdown beside the story model in `static\index.html`/`static\app.js` (shared model list, start-button gating based on preview's PDF/image count, sent as `vision_model`); replace OCR wording
- [x] 4.2 Update `README.md` (Ollama VLM setup, `ollama pull`, GPU notes, env vars; remove Docling/PyTorch steps) and `docs\API.md`

## 5. Tests

- [x] 5.1 Rewrite `tests\test_extraction.py` with fake Ollama client/renderer: image, multi-page, empty, timeout, missing model, unreachable, text notes
- [x] 5.2 Update `test_pipeline.py`, `test_cache.py`, `test_api.py`, `test_analysis.py` and browser tests for new extractor/identity/wording
- [x] 5.3 Run the full pytest suite and fix regressions
