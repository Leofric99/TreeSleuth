# Proposal

## Why

Genealogical research is often scattered across nested folders and mixed media, making it difficult to connect primary-source records to a family tree, identify contradictions, and turn verified facts into a useful narrative. This change establishes a local-first workbench that brings document discovery, OCR, GEDCOM context, historical auditing, and biography generation into one workflow without sending research material to a hosted AI service.

## What Changes

- Add a cross-platform ingestion pipeline that recursively discovers GEDCOM trees and supported research documents, extracts structured family facts and document text, and caches extraction results for reuse.
- Add person-to-document correlation, chronological and factual contradiction reporting, and per-person chronological biography generation using a locally running Ollama model.
- Add asynchronous FastAPI services and a browser-based dashboard for directory inspection, pipeline execution, progress events, individual processing status, and reviewing generated biographies and conflicts.
- Keep filesystem access and generated artifacts local; use platform-neutral path handling, automatically select supported CUDA or Apple MPS OCR acceleration with CPU fallback, and clearly report slow or unavailable processing.
- Emit elapsed-time progress updates for documents that remain in OCR so large local scans do not appear idle while a blocking extraction is in progress.

## Capabilities

### New Capabilities
- `research-ingestion`: Discover local research files recursively, parse GEDCOM baselines, extract text from documents, and reuse cached extraction results.
- `genealogy-analysis`: Correlate source documents with people, detect conflicts with genealogical facts and timelines, and assemble chronological life stories using local LLM inference.
- `local-research-dashboard`: Inspect a selected directory, configure available local models, run and monitor analysis, and review results through local API and browser interfaces.

### Modified Capabilities
- None.

## Impact

- New Python 3.11+ application structure, including FastAPI services, asynchronous pipeline coordination, GEDCOM parsing, Docling OCR, and Ollama integration.
- New static HTML/CSS/JavaScript dashboard served by the backend; no Node.js build or package installation is required.
- New local `.tree_cache` extraction cache and generated biography/audit output under the selected research root.
- New API contracts for system checks, directory analysis, pipeline execution, and real-time progress delivery.
- Runtime prerequisites include Python dependencies, a locally installed/running Ollama service with a selected model, and optional accelerator-capable PyTorch builds. NVIDIA GPU OCR requires a CUDA-enabled PyTorch build; CPU remains supported when acceleration is unavailable.
