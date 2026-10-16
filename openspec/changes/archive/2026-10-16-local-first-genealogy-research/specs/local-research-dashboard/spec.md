# Spec Delta

## Purpose

This capability gives users a local browser interface and API for inspecting a research folder, selecting an available local model, monitoring analysis, and reviewing results. It exposes the analysis workflow without requiring a frontend build system or a hosted application service.

## ADDED Requirements

### Requirement: Check local model service availability
The system SHALL provide a system-check operation that reports whether the local Ollama service is reachable and which local models are available.

#### Scenario: Ollama is available
- **WHEN** the user requests a system check while Ollama is reachable
- **THEN** the response reports service availability and the installed model names

#### Scenario: Ollama is unavailable
- **WHEN** the user requests a system check while Ollama cannot be reached
- **THEN** the response reports the service failure explicitly and does not report a successful model check

### Requirement: Preview directory workload before ingestion
The system SHALL provide a directory-analysis operation that returns discovered-file counts, supported document workload, and whether a GEDCOM baseline was found before expensive document extraction begins.

#### Scenario: A valid directory is analyzed
- **WHEN** the user submits a readable research directory
- **THEN** the response summarizes discovered supported files, GEDCOM presence, and expected document processing workload without starting OCR or biography generation

#### Scenario: A directory cannot be analyzed
- **WHEN** the submitted location is invalid or inaccessible
- **THEN** the response identifies the path error and does not return a successful workload summary

### Requirement: Run pipeline with real-time progress
The system SHALL expose an operation that starts the requested directory analysis and streams ordered progress events and completion or failure status to the requesting client.

#### Scenario: Pipeline is processing
- **WHEN** a pipeline run discovers GEDCOM data, extracts documents, correlates evidence, audits conflicts, or generates biographies
- **THEN** the client receives progress events identifying the current stage and relevant file or person where available

#### Scenario: Pipeline finishes or fails
- **WHEN** the pipeline completes or an unrecoverable error stops it
- **THEN** the client receives a terminal event with the run outcome and access to any successfully completed results

#### Scenario: Client disconnects during processing
- **WHEN** a client closes its event stream while work is running
- **THEN** the pipeline's execution outcome is explicit and is not falsely reported as completed merely because the connection closed

### Requirement: Present people and their processing status
The dashboard SHALL display discovered or inferred people with available lifespan, correlated-document count, and a visible per-person processing status.

#### Scenario: A pipeline has identified people
- **WHEN** the scan or analysis identifies GEDCOM individuals or provisional clusters
- **THEN** the dashboard shows their names, available lifespan, associated document counts, and current status

#### Scenario: Processing moves through stages
- **WHEN** a person's records are being parsed, compared, written, or completed
- **THEN** the dashboard updates that person's status to reflect the current stage or a reported failure

#### Scenario: A document is still being extracted
- **WHEN** OCR has not completed a document within the progress interval
- **THEN** the live event feed identifies the document and reports elapsed processing time without implying completion or cancelling the work

### Requirement: Review generated stories and conflicts
The dashboard SHALL allow users to inspect each completed biography and its associated potential conflicts and evidence.

#### Scenario: A user opens a completed person's results
- **WHEN** the user selects a person with completed analysis
- **THEN** the dashboard displays the generated story and separately highlights reported conflicts with source and baseline evidence

#### Scenario: A person's analysis is incomplete or failed
- **WHEN** the selected person has no completed results or analysis failed
- **THEN** the dashboard displays the available status and error rather than implying a successful biography exists

### Requirement: Restrict the service to local use
The application SHALL serve its dashboard and API on the local host by default and SHALL not expose research contents or analysis endpoints to remote network clients by default.

#### Scenario: The application starts with default settings
- **WHEN** the local service is launched without an explicit network-exposure configuration
- **THEN** its dashboard and API are reachable only from the local machine
