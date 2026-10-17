## ADDED Requirements

### Requirement: Select a vision model for document transcription
The dashboard SHALL present a vision model selector, populated from the installed local Ollama models returned by the system check and separate from the story-generation model selector, and the pipeline start operation SHALL accept the selected vision model.

#### Scenario: Models are loaded
- **WHEN** the system check reports installed models
- **THEN** both the story model and vision model selectors list them, and the user may choose each independently

#### Scenario: Start requires a vision model for scanned content
- **WHEN** the previewed folder contains PDF or image documents and no vision model is selected
- **THEN** the dashboard disables starting the pipeline and indicates a vision model is required

#### Scenario: Start without scanned content
- **WHEN** the previewed folder contains only GEDCOM and text notes
- **THEN** the dashboard allows starting without a vision model

#### Scenario: Ollama is unavailable
- **WHEN** the system check reports Ollama unreachable or no installed models
- **THEN** the vision model selector is disabled with the same explicit status as the story model selector
