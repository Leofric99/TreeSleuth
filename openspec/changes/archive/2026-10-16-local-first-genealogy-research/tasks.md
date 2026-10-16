# Tasks

## 1. Application foundation

- [x] 1.1 Create the Python 3.11+ project structure, `requirements.txt`, and FastAPI application entry point with the selected runtime dependencies; verify dependency resolution and that the application imports on Windows, macOS, and Linux CI.
- [x] 1.2 Add typed configuration, request/response models, and selected-root path validation using `pathlib`; verify unit tests reject missing, non-directory, unreadable, and out-of-root locations.
- [x] 1.3 Document environment setup, local Ollama installation/model preparation, launch instructions, supported platforms, CPU fallback, and optional CUDA-enabled PyTorch setup in the README; verify each documented command matches the application entry point.

## 2. File discovery and source extraction

- [x] 2.1 Implement recursive `Path.rglob` discovery for GEDCOM, PDF, image, TXT, and Markdown files with case-insensitive suffix handling and exclusion of cache/output folders; verify tests find nested mixed files without returning generated artifacts or following directory symlinks outside the selected root.
- [x] 2.2 Implement GEDCOM parsing behind a normalized adapter for individuals, families, events, dates, locations, and record identifiers; verify representative parser fixtures preserve relationships and a malformed tree does not discard valid trees.
- [x] 2.3 Implement Docling extraction for PDF and image inputs and direct text reads for TXT/Markdown, automatically selecting supported CUDA/MPS acceleration when available and otherwise using CPU with accelerator-failure fallback; verify mocked extraction tests cover supported formats, automatic accelerator selection, CPU fallback, empty results, and per-file errors.
- [x] 2.4 Implement a local `.tree_cache` keyed by source content and extraction identity with atomic writes and explicit cache failures; verify repeated unchanged inputs hit the cache and edited inputs or changed extraction settings re-run extraction.
- [x] 2.5 Document supported source formats, cache behavior, and per-file error reporting; verify README guidance matches the discovery and extraction tests.

## 3. Person resolution and genealogical analysis

- [x] 3.1 Implement GEDCOM-backed person/document matching with evidence and confidence metadata and explicit ambiguity states; verify fixtures match an unambiguous person and leave indistinguishable candidates unresolved.
- [x] 3.2 Implement provisional person clustering when no usable GEDCOM baseline exists; verify tests group matching names with overlapping dates while labeling inferred identities as provisional.
- [x] 3.3 Implement local Ollama client operations for structured conflict audit and chronological biography generation with timeouts and response validation; verify mocked model tests cover supported results, malformed output, unavailable models, and incomplete generations.
- [x] 3.4 Implement provenance-bearing conflict findings and source-attributed biography results saved beneath the selected root's output directory with collision-safe per-person names; verify tests retain source/baseline references and do not overwrite colliding display names.
- [x] 3.5 Document how to interpret potential conflicts, uncertain associations, provisional clusters, and generated biographies; verify examples distinguish sourced facts from model inference.

## 4. Pipeline orchestration and API

- [x] 4.1 Implement an asynchronous pipeline coordinator with bounded blocking-work execution, per-file/per-person statuses, and an in-memory bounded run/event registry; verify unit tests confirm stage ordering, resource limits, and explicit terminal outcomes.
- [x] 4.2 Add `GET /api/system-check` and `POST /api/analyze-directory` with typed responses and explicit service/path failures; verify API tests cover reachable/unreachable Ollama and workload previews that do not invoke OCR.
- [x] 4.3 Add `POST /api/run-pipeline` run creation and a per-run `GET` SSE event endpoint; verify API tests receive ordered progress and terminal events and confirm disconnecting a client does not mark active work complete.
- [x] 4.4 Configure loopback binding by default, restrictive cross-origin behavior, and result access limited to generated application outputs; verify API tests reject arbitrary file access and a default startup configuration is local-only.
- [x] 4.5 Document API request/response shapes, run lifecycle, event names, and error states; verify documented examples match the API tests.
- [x] 4.6 Emit a recurring per-document elapsed-time progress event while blocking OCR remains active; verify tests confirm the event identifies the document and does not prevent extraction from completing.

## 5. Local dashboard

- [x] 5.1 Build the static HTML, Tailwind-CDN styling, and native JavaScript interface for path selection, model selection, directory preview, and pipeline start; verify the UI loads without a frontend build step and handles API errors visibly.
- [x] 5.2 Implement the people/process board and live event feed using the run event stream; verify browser-level checks update person status and show file/person progress and failures.
- [x] 5.3 Implement biography and conflict review with source evidence and separate conflict highlighting; verify browser-level checks render completed results and incomplete/failed states without success-shaped fallbacks.
- [x] 5.4 Document dashboard usage and the local-only networking boundary; verify the launch instructions open the dashboard and no research content is sent to the styling CDN.

## 6. Cross-platform integration

- [x] 6.1 Add an end-to-end fixture run covering nested inputs, GEDCOM indexing, cached extraction, mocked local-model analysis, progress streaming, and output review; verify the full flow completes and expected source links and conflicts are visible.
- [x] 6.2 Run the focused unit, API, and browser test suites on Windows, macOS, and Linux with CPU-only settings; verify all supported-platform jobs pass without platform-specific path assumptions.
- [x] 6.3 Validate GPU-backed OCR on an available NVIDIA host with a CUDA-enabled PyTorch build, confirm Docling selects the GPU, and verify the previously slow high-resolution image yields extracted text.
