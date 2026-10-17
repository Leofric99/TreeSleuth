## ADDED Requirements

### Requirement: Transcribe document images with a local Ollama vision model
The system SHALL transcribe PDF, JPG, JPEG, PNG, TIF, and TIFF documents by sending page images to a vision-language model served by the configured local Ollama service, and SHALL NOT use Docling or any other conventional OCR engine.

#### Scenario: A scanned handwritten image is processed
- **WHEN** a supported image file is extracted
- **THEN** the system sends the image to the selected VLM with a transcription prompt and returns the model's transcribed text associated with the source file

#### Scenario: A multi-page PDF or multi-frame TIFF is processed
- **WHEN** a document has several pages or frames
- **THEN** the system renders each page locally, transcribes pages in order, and returns one combined text with page boundaries preserved

#### Scenario: A document yields no text
- **WHEN** the model returns empty text for every page of a document
- **THEN** the system reports the document as having no readable text instead of treating it as extracted

### Requirement: Let the user choose the vision model
The system SHALL let the user select the vision model for each pipeline run from the models installed in the local Ollama service, independently of the story-generation model, and SHALL NOT assume a default vision model.

#### Scenario: A user picks a vision model
- **WHEN** the user selects an installed model as the vision model and starts a run
- **THEN** all PDF and image transcription in that run uses the selected model

#### Scenario: No vision model is selected
- **WHEN** a run contains PDF or image documents and no vision model was selected
- **THEN** the system rejects the run before extraction with a message asking the user to select one

#### Scenario: Only text notes are present and no vision model is selected
- **WHEN** a run contains no PDF or image documents
- **THEN** the run proceeds without a vision model

### Requirement: Configure VLM tuning
The system SHALL allow the Ollama host, per-page timeout, page render resolution, and transcription prompt to be configured through environment variables, with documented defaults.

#### Scenario: Defaults are used
- **WHEN** no VLM tuning settings are provided
- **THEN** the system uses the configured Ollama host and default render, timeout, and prompt values

#### Scenario: Invalid configuration is supplied
- **WHEN** a VLM setting is out of range or malformed
- **THEN** the system fails with a message naming the setting

### Requirement: Validate the VLM before extraction
The system SHALL confirm that the selected vision model is installed in Ollama before extracting any document.

#### Scenario: Model is not installed
- **WHEN** a run needing VLM extraction starts and the model is absent from Ollama
- **THEN** the run fails before any extraction with a message naming the model and how to install it

#### Scenario: Ollama is unreachable
- **WHEN** the Ollama service cannot be reached
- **THEN** the run fails with an explicit connection error

#### Scenario: Only text notes are present
- **WHEN** a run contains only TXT or Markdown documents
- **THEN** no VLM validation or call is performed

### Requirement: Use local GPU acceleration through Ollama
The system SHALL perform VLM inference exclusively through the local Ollama service so that Ollama's GPU acceleration applies, and SHALL log a warning when Ollama reports the model is not fully loaded on a GPU.

#### Scenario: GPU is available to Ollama
- **WHEN** Ollama runs the model on a GPU
- **THEN** the system relies on it without additional device configuration

#### Scenario: Model runs on CPU
- **WHEN** Ollama reports the loaded model is not GPU-resident
- **THEN** the system logs a warning that transcription will be slow and continues

### Requirement: Report per-page progress and failures
The system SHALL report extraction progress per page and SHALL identify the document and page of any failure without discarding results from other documents.

#### Scenario: A page times out or errors
- **WHEN** the model call for a page times out or fails
- **THEN** the document is reported as failed with the page number and reason, and other documents continue
