## Context

`treesleuth\extraction.py` defines `DoclingExtractor` (OCR via Docling, torch accelerator detection with CPU retry). `pipeline.py` constructs it by default, runs `extractor.extract_text` in a worker via `ExtractionCache.get_or_extract`, and keys the cache with identity `treesleuth-docling-extraction-v1`. `config.py` already holds Ollama host/timeout settings and `analysis.py` has an Ollama client wrapper (`available_models`, `OllamaServiceError`). Docling OCR misreads historical handwriting.

## Goals / Non-Goals

**Goals:**
- Local, GPU-accelerated (via Ollama) transcription of scans with a configurable VLM.
- Keep the `extract_text(Path) -> str` interface so pipeline and cache logic change minimally.
- Clear failures for missing model / unreachable Ollama.

**Non-Goals:**
- Hosted VLMs or any network egress beyond the local Ollama host.
- Structured/layout extraction (tables, bounding boxes); output is plain transcribed text.
- Bundling or auto-pulling models.
- Changing the analysis (story/audit) model configuration.

## Decisions

1. **`VlmExtractor` replaces `DoclingExtractor`** in `extraction.py`, with an injectable Ollama client (and page renderer) for tests. TXT/MD handling is kept as-is. Alternative: keep Docling for layout plus VLM for OCR; rejected as it retains the heavy torch dependency and the user asked to replace OCR tooling.
2. **Rendering**: PDFs rasterized with PyMuPDF (pure wheel, cross-platform, no poppler); images/TIFF frames loaded with Pillow, converted to RGB, downscaled so the longest side ≤ configured max, and encoded as PNG bytes in memory. Nothing is written to the research folder.
3. **Inference**: `ollama.AsyncClient`/`Client.chat` with `images=[bytes]`, `temperature: 0`, and a prompt instructing faithful transcription (preserve spelling, abbreviations, line breaks; mark illegible as `[illegible]`; no commentary). One call per page; results joined with `\n\n--- Page N ---\n\n` markers.
4. **Configuration**: the vision model is NOT an env var; it is chosen per run in the dashboard, mirroring the story model (`modelSelect` populated from the system check, sent in `PipelineStartRequest`). Add an optional `vision_model: str | None` to `PipelineStartRequest` and `RunRecord`, and a second dropdown `visionModelSelect` in `static\index.html`/`app.js` sharing the model list from `checkOllama`. The start button requires a vision model only when the preview reports PDF/image documents; otherwise it is optional, and the backend enforces the same rule. Env-only tuning settings (new `Settings` fields): `TREESLEUTH_VLM_HOST` (falls back to `OLLAMA_HOST`), `TREESLEUTH_VLM_TIMEOUT_SECONDS` (default 300), `TREESLEUTH_VLM_MAX_IMAGE_SIDE` (default 2048), `TREESLEUTH_VLM_PDF_DPI` (default 200), `TREESLEUTH_VLM_PROMPT` (optional override). Pydantic bounds validate values. No default vision model is assumed.
5. **Preflight**: at the start of `_extract_documents`, if any non-text document exists, verify the selected vision model is in the installed list on the VLM host and fail the run with an actionable message if missing or Ollama unreachable. After the first successful call, query `ps` once and warn if `size_vram < size`.
6. **Cache identity**: replace the static identity with a string derived from a version tag plus the selected model, prompt hash, DPI and max side so any change re-extracts. The extractor is constructed per run with the selected model rather than once at pipeline construction.
7. **Concurrency**: keep the extractor lock so a single GPU is not oversubscribed regardless of `max_workers`.
8. **Progress**: extractor accepts an optional page-progress callback; pipeline emits "Transcribing page X of Y of <source>" events using the existing progress mechanism.
9. **Dependencies**: remove `docling`; add `pymupdf` and `pillow`. README drops PyTorch/CUDA install guidance in favour of Ollama GPU notes and `ollama pull <vlm>`.

## Risks / Trade-offs

- VLM hallucination on illegible text → prompt demands `[illegible]` markers, temperature 0; downstream review step already exists.
- Slow on large PDFs/CPU-only → per-page progress, per-page timeout, CPU warning, cache reuse.
- Model context/VRAM limits on large images → configurable max side.
- Loss of Docling's born-digital PDF text layer → mitigation: none initially (all pages rasterized); noted as possible follow-up to use PyMuPDF text for text-layer PDFs.
- Existing caches invalidated → one-time re-extraction.

## Open Questions

- Which installed model is suitable is the user's choice; the UI does not filter for vision capability, so the preflight/first call should surface a clear error if the chosen model rejects images.
