# TreeSleuth

TreeSleuth is a **GEDCOM data auditor** for genealogists. It validates family tree files for logical inconsistencies, timeline errors, and data-entry mistakes—catching the "impossible" situations that reveal typos or misremembered facts.

## What It Checks

TreeSleuth validates GEDCOM family trees by checking for:

- **Anachronisms:** Mothers giving birth before age 12 or after age 50
- **Time Travel:** Children born after a parent died (beyond biological possibility)
- **Lifespan Outliers:** Lifespans exceeding 110 years or death before birth
- **Marriage Timing:** Marriages before birth or after death dates
- **Overlap Errors:** Other logical relationship impossibilities in the family tree

No external APIs, no cloud services—just local, deterministic validation of your genealogy data.

## Requirements

- Python 3.11 or newer
- A local GEDCOM file or directory containing GEDCOM files (`.ged` extension)

That's it. No Ollama, no vision models, no GPU needed.

## Setup

Create and activate a virtual environment, then install the dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

From the repository root with the virtual environment active:

```sh
python -m treesleuth
```

The service binds to loopback by default (`127.0.0.1:8000`). Open `http://127.0.0.1:8000` in your browser.

## API

The application exposes a single validation endpoint:

```
POST /api/validate-gedcom
Content-Type: application/json

{
  "path": "/path/to/family/tree/directory"
}
```

**Response:**

```json
{
  "gedcom_files": 1,
  "total_individuals": 193,
  "total_families": 51,
  "issues_found": 3,
  "errors": 2,
  "warnings": 1,
  "issues": [
    {
      "severity": "error",
      "category": "time_travel",
      "person_id": "I1@file.ged",
      "person_name": "John Doe",
      "message": "Birth year 1950 is 10 years after father's death (1940)",
      "details": {
        "child_name": "John Doe",
        "father_name": "James Doe",
        "child_birth_year": 1950,
        "father_death_year": 1940,
        "years_after_death": 10
      }
    }
  ],
  "parse_errors": []
}
```

## Dashboard

The browser interface provides:

1. **Directory Selection** - Choose a folder containing GEDCOM files
2. **Validation** - Click "Validate" to run checks
3. **Results** - View issues grouped by severity and category
4. **Details** - Click any issue to see the involved individuals and specific problem

All processing happens locally. No files are uploaded or sent anywhere.
