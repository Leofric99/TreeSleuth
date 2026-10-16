# TreeSleuth

TreeSleuth is a local-first genealogy research workbench. It is designed to
index GEDCOM trees, extract text from nested research documents, compare source
claims with family facts, and assemble source-attributed life stories using a
local Ollama model.

## Requirements

- Python 3.11 or newer
- Ollama installed and running locally for model-assisted analysis
- A local Ollama model with enough memory for its selected size; for example,
  `qwen2.5:14b`

The application supports Windows, macOS, and Linux. OCR automatically selects
CUDA or Apple MPS when the installed PyTorch build supports an available
accelerator, and otherwise uses CPU. Accelerator errors retry on CPU. NVIDIA
GPU use requires a CUDA-enabled PyTorch build; installing the default CPU-only
PyTorch package does not enable CUDA. Research files and analysis stay on the
local machine.

## Setup

Create and activate a virtual environment, then install the dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For NVIDIA GPU OCR on Windows, replace the CPU-only PyTorch build installed by
the base dependencies with a CUDA-enabled build compatible with your Python
version and NVIDIA driver. For this project environment (Python 3.14 and a
CUDA 13-capable driver), the tested command is:

```powershell
python -m pip install torch==2.14.1+cu130 --index-url https://download.pytorch.org/whl/cu130
```

Use the [official PyTorch installer selector](https://pytorch.org/get-started/locally/)
if your Python version or driver needs a different CUDA build. TreeSleuth will
automatically use CUDA when PyTorch detects it and fall back to CPU otherwise.

On macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Install Ollama using its official installer for your operating system, start
the local Ollama service, and download a model. For example:

```sh
ollama pull qwen2.5:14b
```

The model selector will use models available from the local Ollama service.
Choose a smaller installed model if available memory is limited.

## Run

From the repository root with the virtual environment active:

```sh
python -m treesleuth
```

The service binds to loopback by default. Do not change the bind address to a
network interface unless you understand the privacy implications of exposing
genealogical research endpoints.

API operations, response shapes, and server-sent event names are documented in
[the API guide](./docs/API.md).

## Dashboard and local network boundary

Open `http://127.0.0.1:8000` after starting the service. Check Ollama, enter a
research-folder path, preview the directory workload, choose an installed
model, and start analysis. The dashboard shows per-person status changes and
the live event stream; completed and failed people can be opened to review
biographies, source citations, conflicts, and errors.

The default server host is `127.0.0.1`, and the app does not enable
cross-origin access or an endpoint for arbitrary filesystem reads. The
Tailwind CDN is used only to download presentation styles; the dashboard sends
research paths and source content to same-origin TreeSleuth API routes, not to
the CDN. Keep the service on loopback unless you intentionally configure and
secure a different network deployment.

## Source files and extraction cache

The directory trawler searches nested folders for `.ged` family trees and
research documents ending in `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`,
`.txt`, `.md`, or `.markdown`. PDF and image records use Docling OCR and
layout-aware text extraction; plain-text and Markdown notes are read directly.
The application excludes its own `.tree_cache` and `output` folders from later
scans.

Extracted text is cached in `.tree_cache` beneath the selected research
directory. Cache entries are reused only when the source content and extractor
identity match. Changed files are extracted again, and cache write/read
problems are reported while fresh extraction continues when possible.

An unreadable, empty, corrupt, or unsupported file is reported as an
individual processing failure; it does not erase successful results from other
files. GEDCOM parsing failures are likewise reported per tree while other
valid family trees remain available for analysis.

OCR can take a while on large PDFs or image files, especially on CPU. The live
event feed reports the document being processed and emits elapsed-time updates
while extraction is still running. A `RapidOCR returned empty result` message
means OCR found no text in a page or image; by itself it does not stop the
pipeline. If the whole document contains no readable text, TreeSleuth reports
that file as a warning and continues with the remaining documents.

## Reviewing analysis

GEDCOM-backed matches include the record identity, name evidence, and timeline
evidence used to associate a source. When more than one person is plausible,
the association is marked ambiguous rather than silently choosing one. If no
GEDCOM baseline is available, document groups are explicitly provisional and
are not presented as verified family identities.

Conflict findings are potential contradictions, not corrections to the family
tree. Review the source claim, the cited GEDCOM fact, and their source IDs
before drawing a conclusion. Incomplete evidence and uncertain identity
matches remain marked uncertain.

Generated biographies are saved under `output` as per-person
`*_LifeStory.txt` files, alongside JSON conflict reports and structured
analysis data with claim citations. A stable person-identity suffix prevents
two people with the same display name from overwriting one another. Model
output is checked for valid structure and known source IDs before it is saved;
malformed responses or unsupported citations are reported as failures rather
than treated as verified facts.

## Diagnostic logs

TreeSleuth writes detailed execution diagnostics to `.treesleuth/logs/treesleuth.log`
in the repository. The log is appended across runs and rotated to bound disk use.
It can include research paths and other sensitive processing context, so keep
the checkout private. Generated log files are excluded from Git.
