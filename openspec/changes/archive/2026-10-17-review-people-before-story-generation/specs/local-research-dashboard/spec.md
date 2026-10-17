# Spec Delta

## MODIFIED Requirements

### Requirement: Run pipeline with real-time progress
The system SHALL expose an operation that starts GEDCOM and document preparation and streams ordered progress events, followed by an explicit user-requested story-generation operation and its completion or failure status.

#### Scenario: Pipeline is processing
- **WHEN** a pipeline run prepares GEDCOM records and research documents or performs user-requested generation
- **THEN** the client receives ordered progress events identifying the current stage and relevant file or person where available, and preparation itself does not audit or generate biographies

#### Scenario: User requests story generation
- **WHEN** the user requests generation for one person or all people after document preparation
- **THEN** the client receives progress and a terminal outcome for each requested person's audit and biography generation

#### Scenario: Pipeline finishes or fails
- **WHEN** preparation or a generation job completes or an unrecoverable error stops it
- **THEN** the client receives a terminal event with the outcome and access to any successfully completed results

#### Scenario: Client disconnects during processing
- **WHEN** a client closes its event stream while preparation or requested generation is running
- **THEN** the work continues and its outcome remains available through the run state

### Requirement: Present people and their processing status
The dashboard SHALL show GEDCOM individuals promptly after GEDCOM parsing and before document extraction, sorted by their effective surname, with available lifespan, correlated-document count, and a visible status.

#### Scenario: A pipeline has identified people
- **WHEN** analysis finds a parseable GEDCOM tree
- **THEN** the dashboard presents its individuals within a few seconds for an ordinarily sized local tree and before document extraction or model inference begins, with available names, lifespan, document counts, and status

#### Scenario: People are grouped in collapsible surname dropdowns
- **WHEN** GEDCOM individuals are displayed
- **THEN** the dashboard groups people into expandable surname dropdowns ordered by effective display surname, starts each group collapsed, and shows its people when the group is expanded

#### Scenario: People are sorted using merged display surnames
- **WHEN** GEDCOM individuals are displayed
- **THEN** they are ordered alphabetically by effective display surname, with individuals sharing a surname kept together

#### Scenario: Document preparation finishes
- **WHEN** all supported documents have been read and associated with people
- **THEN** the dashboard reports preparation as complete and leaves biography generation available only through an explicit user action

#### Scenario: No GEDCOM index is available
- **WHEN** documents are prepared without a parseable GEDCOM baseline
- **THEN** the dashboard displays any provisional person clusters with their inferred status rather than presenting them as GEDCOM individuals

#### Scenario: Processing moves through stages
- **WHEN** a person's records are being prepared or requested generation is running
- **THEN** the dashboard updates the person's status to reflect the current stage or a reported failure

#### Scenario: A document is still being extracted
- **WHEN** OCR has not completed a document within the progress interval
- **THEN** the live event feed identifies the document and reports elapsed processing time without implying completion or cancelling the work

### Requirement: Review generated stories and conflicts
The dashboard SHALL allow users to explicitly generate and inspect each person's biography and its associated potential conflicts and evidence, individually, for checkbox-selected people, or for all people.

#### Scenario: A user selects people for generation
- **WHEN** document preparation is complete and the user checks one or more people
- **THEN** the dashboard enables a selected-stories action that generates only those people and reports each outcome

#### Scenario: A user generates one person's story
- **WHEN** document preparation is complete and the user activates a person's individual story action
- **THEN** the system generates only that person's story and reports its status and result

#### Scenario: A user selects all people
- **WHEN** document preparation is complete and the user activates the select-all checkbox
- **THEN** all eligible people are selected for the selected-stories action, without conflating that action with the separate generate-all action

#### Scenario: A user opens a completed person's results
- **WHEN** the user selects a person whose requested analysis completed
- **THEN** the dashboard shows that person's generation status, story, and separately reported conflicts with source and baseline evidence

#### Scenario: A user generates stories for everyone
- **WHEN** document preparation is complete and the user requests generation for everyone
- **THEN** the system attempts generation per person and reports each person's success or failure without stopping other people's results

#### Scenario: A person's analysis is incomplete or failed
- **WHEN** a requested person's analysis cannot complete or lacks sufficient evidence
- **THEN** the dashboard displays the available status and error rather than implying that a biography exists

## ADDED Requirements

### Requirement: Manage surname display merges
The dashboard SHALL let users map multiple GEDCOM surname spellings to one chosen display surname for organization without merging person identities or modifying source records.

#### Scenario: User chooses source and destination surnames
- **WHEN** the user selects a source spelling and destination surname from the dashboard dropdowns and confirms the merge
- **THEN** the selected spelling is persistently mapped to the destination surname

#### Scenario: User merges surname spellings
- **WHEN** the user maps spellings such as “Edmonds” and “Edmunds” to a chosen surname
- **THEN** affected individuals are displayed and sorted under that surname while their original GEDCOM names and identifiers remain unchanged

#### Scenario: User revisits a surname merge
- **WHEN** the user starts another analysis after saving a surname merge
- **THEN** the same display mapping is applied to matching surnames
