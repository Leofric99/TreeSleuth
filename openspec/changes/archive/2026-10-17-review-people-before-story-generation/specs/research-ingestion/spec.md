# Spec Delta

## MODIFIED Requirements

### Requirement: Reuse valid extraction cache entries
The system SHALL cache extracted document text in the application's repository-local `.cache` directory and reuse it only when the source content, selected research root, and extraction-relevant settings match the cached entry.

#### Scenario: An unchanged document is analyzed again
- **WHEN** a document is processed with a matching valid cache entry for its research root and extraction settings
- **THEN** the system reuses its extracted text without repeating document extraction

#### Scenario: A document or extraction configuration changes
- **WHEN** source content, selected research root, or an extraction-relevant setting differs from the cache entry
- **THEN** the system re-extracts the document and replaces or isolates the stale cached result

#### Scenario: The cache is unavailable
- **WHEN** the cache cannot be read or written
- **THEN** the system reports the cache issue and continues extraction without claiming that the result was cached

#### Scenario: Cache data is stored
- **WHEN** the system writes an extracted-text cache entry
- **THEN** it stores the entry under the repository-local `.cache` directory, whose contents are excluded from version control, without creating files in the selected research folder

### Requirement: Keep ingestion local and cross-platform
The system SHALL process selected source files locally and store application-generated cache and analysis results beneath the repository-local `.cache` directory, without writing to the selected research folder except for that TreeSleuth-owned cache when it lies inside the selected folder, or uploading genealogical source content to a hosted service, and SHALL support native Windows, macOS, and Linux filesystem paths.

#### Scenario: A supported OCR accelerator is available
- **WHEN** Docling runs on a host with an available CUDA or Apple MPS accelerator supported by the installed PyTorch build
- **THEN** the system uses that accelerator by default and retries extraction on CPU if accelerated processing fails

#### Scenario: Hardware acceleration is unavailable
- **WHEN** OCR acceleration is not supported or available on the host
- **THEN** the system can process documents using CPU execution and reports unrecoverable processing limitations explicitly

#### Scenario: A scan completes
- **WHEN** the system returns ingestion results
- **THEN** source paths and generated cache locations are represented in a form usable on the host operating system

#### Scenario: Research folder is not modified by ingestion
- **WHEN** the system scans, reads, or analyzes a selected research folder
- **THEN** it creates, modifies, or deletes no selected-folder content other than the TreeSleuth-owned `.cache` directory and its contents

#### Scenario: Repository cache is inside the selected folder
- **WHEN** the selected research folder contains TreeSleuth's repository-local `.cache` directory
- **THEN** the system treats that directory as application state, excludes it from source discovery, and writes no other files or directories within the selected folder
