# Design

## Context

The repository currently contains only a placeholder README and project configuration; there is no application code or established runtime architecture to extend. See proposal.md for the motivation and the three capability specs for observable behavior.

The system must support Python 3.11+ on Windows, macOS, and Linux, process private research documents locally, and remain useful without accelerator hardware. Docling and Ollama are heavyweight/local-service dependencies, while OCR and model calls can take substantially longer than an HTTP request.

## Goals / Non-Goals

**Goals:**
- Establish clear boundaries between filesystem ingestion, genealogical analysis, pipeline orchestration, API services, and static UI.
- Keep event-loop work responsive during OCR and other blocking operations and give clients an explicit run lifecycle.
- Preserve provenance from source files through entity matches, conflict findings, and generated biography claims.
- Provide repeatable local output and cache behavior that is safe across operating systems.

**Non-Goals:**
- Provide hosted inference, cloud storage, multi-user accounts, or remote access by default.
- Automatically edit source GEDCOM files or modify original research documents.
- Guarantee that model-generated genealogical interpretations are correct; results remain evidence-based suggestions for human review.
- Add a frontend compilation or package-installation workflow.

## Decisions

### Use a layered Python application with typed boundaries

Create separate modules for configuration/path validation, discovery and extraction, GEDCOM normalization, analysis, pipeline runs, and FastAPI routes. Keep Docling, the GEDCOM parser, and Ollama behind small adapters so their data models do not leak into API responses or UI code. Use Pydantic request/response models and explicit per-file/per-person result states to prevent partial work from appearing successful.

**Alternatives considered:** Put the whole pipeline in route handlers (simpler initially, but couples HTTP lifecycle to heavy processing); use a distributed task queue (adds infrastructure and deployment cost inappropriate for a local single-user application).

### Treat selected-root paths as `pathlib.Path` values end-to-end

Accept a path from the local UI, validate that it resolves to a readable directory, and use `pathlib.Path` for traversal, cache/output construction, and safe result paths. Discover nested files with `Path.rglob`, case-fold file suffixes, and exclude the application's own cache and output directories from subsequent discovery. Do not follow directory symlinks outside the selected root. Return paths in an OS-neutral API representation and never construct paths by concatenating separator strings.

**Alternatives considered:** Require a rigid folder layout (does not fit arbitrary research collections); normalize user paths with platform-specific string rules (fragile across supported operating systems).

### Build GEDCOM facts before processing unstructured documents

The discovery pass first identifies all `.ged` files and parses each into a normalized person/family/event index. Use `python-gedcom` behind an adapter, with a compatibility fixture covering representative GEDCOM records; retain source-tree and record identifiers. Continue with successfully parsed trees if another GEDCOM file fails. If no usable baseline exists, pass that state to analysis so its entity resolver creates explicitly provisional clusters rather than implying GEDCOM-grounded identities.

**Alternatives considered:** `gedcompy` (also acceptable, but maintaining a parser adapter keeps later replacement low-cost); parse GEDCOM with ad hoc text rules (would be brittle for relationships, dates, and nested record structures).

### Use Docling for document formats and direct reads for text notes

Route PDF and image inputs through a Docling adapter and read TXT/Markdown as text without OCR. Detect supported CUDA or Apple MPS acceleration at runtime and use it by default when available; otherwise use CPU. If accelerated extraction fails, retry on CPU, and keep accelerator-specific builds optional so GPU support is not a prerequisite for running the application. In particular, NVIDIA acceleration requires a CUDA-enabled PyTorch build; a CPU-only PyTorch installation cannot use a detected NVIDIA GPU. Report extraction failures at file granularity and continue other files.

**Alternatives considered:** Use separate OCR libraries per operating system (creates divergent extraction behavior and dependency burden); require a GPU (excludes ordinary desktops and servers).

### Key extraction cache by content and extraction identity

Store extracted text beneath `.tree_cache` at the selected root. Compute a content digest for each source and include the extractor/configuration identity in the cache key or metadata; only reuse entries when both still match. This avoids stale output after a file is renamed or edited and invalidates results when extraction behavior changes. Use temporary files and atomic replacement for cache writes; a cache failure is reported but does not turn a successful fresh extraction into a false failure.

**Alternatives considered:** Key only by filename (misses changed content and colliding names); disable caching (repeats expensive OCR on every run).

### Separate asynchronous job creation from SSE event consumption

`POST /api/run-pipeline` validates options and creates a run with a stable run ID; it returns immediately. A separate `GET` event-stream route for that run emits ordered stage, file, person, warning, and terminal events. The browser uses `EventSource` for the stream. The pipeline owns its lifecycle independently of an individual client connection, and a disconnect does not silently mark work successful. Keep run metadata and recent events in an in-memory, bounded registry; durable deliverables are the saved results and extraction cache.

Run blocking extraction work in a bounded worker pool so it cannot block FastAPI's event loop. While a document extraction remains active, publish a file progress event every 15 seconds identifying the document and elapsed time; this is a liveness update, not a completion estimate or cancellation timeout. Use the Ollama async client for inference, with explicit timeouts and error states. Enforce a per-run work limit and expose queue/progress rather than spawning unbounded OCR tasks.

**Alternatives considered:** Keep a POST request open as SSE (not directly consumable through browser `EventSource` and vulnerable to request timeouts); WebSockets (bidirectional communication is unnecessary for progress); execute OCR synchronously in request handlers (blocks API responsiveness).

### Keep source content and service local by default

Bind the server to loopback by default, avoid permissive cross-origin settings, and expose only application-generated results rather than an arbitrary file-read endpoint. Use a local Ollama endpoint and make failures visible. Build safe output names from normalized person identity plus a stable identifier, store biography text and structured conflict data beneath the selected root's `output` directory, and never overwrite a different person's result because their display names collide.

The requested Tailwind CDN can be used for presentation, but it must receive no genealogy content; the app should keep its functional HTML and JavaScript local. A future offline stylesheet may replace the CDN without changing APIs.

**Alternatives considered:** Bind to all network interfaces by default (unintentionally exposes sensitive data); use a hosted LLM or remote asset pipeline (violates the local-processing boundary); use display names alone for filenames (collisions can overwrite records).

### Validate model outputs before saving or displaying them

Use structured prompts that clearly separate GEDCOM facts, extracted source claims, and inferred details. Ask the model for machine-readable audit findings and biography content with source references, validate the response against application schemas, and mark malformed or incomplete responses as failed/incomplete. Do not interpret a missing or invalid model field as an empty successful result.

**Alternatives considered:** Save raw model output as if it were valid analysis (poorly supports review and can hide unsupported claims); rely solely on free-form model prose (makes conflicts and citations hard to render consistently).

## Risks / Trade-offs

- [Docling installation and model assets may be large or differ across operating systems] → Keep CPU as the supported baseline, isolate document processing behind an adapter, document platform setup, and validate supported Python 3.11+ installs in CI where feasible.
- [OCR, entity matching, and generated narratives can be inaccurate] → Preserve source attribution and uncertainty, separate inferred clusters from GEDCOM identities, expose potential rather than definitive conflicts, and make human review explicit.
- [A large research folder can exhaust memory or run for a long time] → Stream files through a bounded worker pool, cache individual extraction results, report progress, and avoid accumulating all document image data in memory.
- [A user-provided directory can contain unreadable or adversarial files] → Validate the selected root, constrain outputs/cache to that root, avoid following directory symlinks outside it, handle failures per file, and do not expose arbitrary file reads through the API.
- [Local Ollama may be absent or model output may be incomplete] → Check service/model availability before a run, use timeouts, surface actionable failures, and retain explicit failed/incomplete statuses.
- [Tailwind CDN requires network access for styling] → Keep content and application logic local and send no research data to the CDN; the UI remains structurally usable if the style resource is unavailable.
- [In-memory job/event state is lost if the server exits] → Treat active run tracking as transient, report interrupted runs on restart, and persist completed user-facing outputs and reusable OCR cache locally.

## Migration Plan

This is a new application in a repository with no existing runtime or user data contract, so no data migration or backward-compatibility transition is required. Initial setup should create the Python dependency manifest, application modules, static dashboard, and focused tests; rollback consists of stopping/removing the application while leaving user source files untouched. Cache and output cleanup must be explicit and limited to the application's named directories.
