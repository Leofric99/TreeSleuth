# Spec Delta

## MODIFIED Requirements

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
- **WHEN** a requested person has no usable timeline or correlated source text
- **THEN** the system reports that a biography could not be generated instead of returning an empty or success-shaped result

#### Scenario: Document preparation completes without a generation request
- **WHEN** all documents have been read and correlated but the user has not requested story generation
- **THEN** the system completes preparation without auditing or generating biographies

### Requirement: Save analysis results under the selected research root
The system SHALL save generated biographies and conflict results beneath the application's repository-local `.cache` directory and SHALL use safe, deterministic per-person output names that do not overwrite another person's results.

#### Scenario: Analysis results are saved
- **WHEN** a biography and its audit results are successfully generated
- **THEN** the user can review the saved outputs and their association with the analyzed person in the application

#### Scenario: Two people have colliding display names
- **WHEN** multiple people normalize to the same display-name filename
- **THEN** the system uses stable identity information to produce distinct output files

#### Scenario: Results are generated for a selected research folder
- **WHEN** story generation runs for files in a user-selected research folder
- **THEN** the system writes result files only to the repository-local `.cache` directory, which is the sole application-managed write when that directory lies within the selected folder
