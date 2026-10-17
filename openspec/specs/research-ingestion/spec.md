# Research Ingestion Specification

## Purpose

This capability discovers genealogical source material in a user-selected local folder and turns GEDCOM and supported documents into reusable structured and textual inputs for analysis. It provides a cross-platform, repeatable ingestion foundation while keeping source material on the user's machine.

## Requirements

### Requirement: Recursively discover local genealogical source files
The system SHALL scan a user-selected existing directory and its nested directories for GEDCOM trees and supported research documents, without requiring a predefined folder layout.

#### Scenario: Mixed files are found in nested folders
- **WHEN** the user analyzes a directory containing GEDCOM, PDF, image, and text research files at different nesting levels
- **THEN** the system reports each supported file and its type in the scan results

#### Scenario: The selected path is not a readable directory
- **WHEN** the user submits a missing path, a regular file, or a directory the application cannot read
- **THEN** the system reports a path-specific error and does not start ingestion

### Requirement: Parse discovered GEDCOM trees into a genealogical index
The system SHALL parse every discovered GEDCOM file into an index of individuals, family relationships, and available names, dates, locations, and event facts, retaining identifiers needed to relate people and families.

#### Scenario: One or more valid GEDCOM files are found
- **WHEN** the scan finds parseable GEDCOM files
- **THEN** the ingestion results expose the parsed individuals and relationships and identify which tree each record came from

#### Scenario: No GEDCOM file is found
- **WHEN** the scan completes without finding a GEDCOM file
- **THEN** the system reports that no GEDCOM baseline is available and permits document ingestion to continue

#### Scenario: A GEDCOM file cannot be parsed
- **WHEN** one discovered GEDCOM file is malformed or unsupported
- **THEN** the system reports the file and parse failure while preserving results from other parseable files

### Requirement: Extract text from supported research documents
The system SHALL extract readable text from PDF, JPG, JPEG, PNG, TIF, TIFF, TXT, and Markdown files and associate each extracted result with its source file.

#### Scenario: Scanned or text-based records are readable
- **WHEN** a supported PDF or image is processed successfully
- **THEN** the system makes its extracted text available to downstream analysis and retains the document's source identity

#### Scenario: Plain-text notes are discovered
- **WHEN** a TXT or Markdown research note is encountered
- **THEN** the system reads its text directly and includes it as a source for downstream analysis

#### Scenario: A document cannot be processed
- **WHEN** a supported file is corrupt, inaccessible, or produces no readable text
- **THEN** the system reports the affected file and processing outcome without treating it as successfully extracted

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
