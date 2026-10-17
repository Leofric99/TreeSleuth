# Genealogy Analysis Specification

## Purpose

This capability connects unstructured research evidence with people and family facts, identifies potentially inconsistent historical claims, and creates chronological biographies grounded in the available records. Analysis uses a locally running language model and preserves enough source provenance for users to inspect its conclusions.

## Requirements

### Requirement: Correlate source documents with indexed individuals
The system SHALL associate extracted document content with likely individuals using the available GEDCOM index and SHALL retain the evidence and confidence basis for each association.

#### Scenario: A document matches a GEDCOM individual
- **WHEN** extracted text contains identifying information consistent with a person in the GEDCOM index
- **THEN** the system associates the document with that person and records the source document identity

#### Scenario: A document may match multiple individuals
- **WHEN** extracted text is insufficient to distinguish between multiple indexed people
- **THEN** the system presents the association as ambiguous rather than silently assigning a definitive person

#### Scenario: No GEDCOM index is available
- **WHEN** documents are analyzed without a GEDCOM baseline
- **THEN** the system groups documents into provisional person clusters based on names and overlapping timeline evidence and identifies those groups as inferred

### Requirement: Audit evidence against genealogical facts and chronology
The system SHALL compare associated document claims with available GEDCOM facts and SHALL present potential contradictions with the relevant person, source, claims, and explanation.

#### Scenario: A source conflicts with a known date or event
- **WHEN** a source indicates an event after the person's recorded death or supplies a materially different date or location
- **THEN** the system reports a potential conflict and shows both the source claim and GEDCOM fact with their provenance

#### Scenario: No contradiction is found
- **WHEN** evaluated source claims do not conflict with available facts
- **THEN** the system reports no detected conflict for those evaluated claims without asserting that the records are definitively correct

#### Scenario: Evidence is insufficient to decide
- **WHEN** source text, dates, or identity association is too uncertain to establish a contradiction
- **THEN** the system marks the finding as uncertain and does not present it as a confirmed conflict

### Requirement: Generate a chronological biography from attributable evidence
The system SHALL generate a per-person life story only when the user explicitly requests it for one person, a selected group, or all people, combining available GEDCOM events with correlated source details in chronological order and making source attribution available for generated claims.

#### Scenario: A person has GEDCOM and document evidence
- **WHEN** document preparation is complete and the user requests a biography for a person with GEDCOM and document evidence
- **THEN** the system generates a chronological story that synthesizes the available evidence and identifies supporting sources

#### Scenario: A user requests stories for all people
- **WHEN** document preparation is complete and the user requests biographies for all people
- **THEN** the system attempts each person's generation and reports each result independently

#### Scenario: A user requests stories for selected people
- **WHEN** document preparation is complete and the user requests biographies for a selected group of people
- **THEN** the system generates only the selected people's biographies and reports each result independently

#### Scenario: A user requests an individual story
- **WHEN** document preparation is complete and the user explicitly requests a biography for one person
- **THEN** the system generates only that person's biography and reports its result

#### Scenario: A person has only document evidence
- **WHEN** biography generation runs without a GEDCOM baseline for a provisional person cluster
- **THEN** the story uses only available document evidence and identifies the cluster and unsupported dates or relationships as provisional

#### Scenario: There is not enough evidence for a story
- **WHEN** a person has no usable timeline or correlated source text
- **THEN** the system reports that a biography could not be generated instead of returning an empty or success-shaped result

#### Scenario: Document preparation completes without a generation request
- **WHEN** all documents have been read and correlated but the user has not requested story generation
- **THEN** the system completes preparation without auditing or generating biographies

### Requirement: Use local model inference and report failures
The system SHALL send analysis prompts and source content only to the selected local Ollama service and SHALL report model unavailability, inference errors, and incomplete generation to the user.

#### Scenario: A selected local model is available
- **WHEN** analysis is requested with an installed model and reachable local Ollama service
- **THEN** the system performs inference through that service and returns the result with its completion status

#### Scenario: The local model cannot be used
- **WHEN** Ollama is unreachable, the selected model is unavailable, or inference fails
- **THEN** the system reports the error and marks affected analysis as failed or incomplete without presenting it as complete

### Requirement: Save analysis results under the selected research root
The system SHALL save generated biographies and conflict results beneath the application's repository-local `.cache` directory and SHALL use safe, deterministic per-person output names that do not overwrite another person's results.

#### Scenario: Analysis results are saved
- **WHEN** a biography and its audit results are successfully generated
- **THEN** the user can review the saved outputs and their association with the analyzed person

#### Scenario: Two people have colliding display names
- **WHEN** multiple people normalize to the same display-name filename
- **THEN** the system uses stable identity information to produce distinct output files

#### Scenario: Results are generated for a selected research folder
- **WHEN** story generation runs for files in a user-selected research folder
- **THEN** the system writes result files only to the repository-local `.cache` directory, which is the sole application-managed write when that directory lies within the selected folder
