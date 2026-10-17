# Proposal

## Why

Starting analysis currently couples GEDCOM loading, document extraction, conflict auditing, and biography generation, so users wait through the full workflow before they can review people or decide which stories to create. It also writes extraction cache and generated results beneath the selected research folder; keeping that folder read-only and storing application data in the repository's ignored `.cache` directory gives users control over generation without altering their source material.

## What Changes

- Load discovered GEDCOM people as the first analysis step and expose them promptly in expandable surname groups, sorted by surname.
- Show people in collapsible surname groups and let users merge a selected source spelling into a selected destination surname without changing GEDCOM source records or person identities.
- After document extraction and correlation, leave stories ungenerated until a user requests one person, a checkbox-selected group, or all eligible people.
- Move extraction cache and generated story, conflict, analysis, and surname-mapping data beneath the repository's gitignored `.cache` directory; do not write application files to the selected research folder except for this TreeSleuth-owned cache, including when it lies within that selected folder.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-research-dashboard`: Expose the early people list, surname consolidation, review-ready state after document reading, and explicit individual/all story-generation actions.
- `genealogy-analysis`: Separate evidence preparation from optional story generation and change where generated analysis artifacts are stored.
- `research-ingestion`: Store extraction cache in the repository's gitignored `.cache` directory while treating the selected research folder as read-only.

## Impact

Affected areas include the pipeline coordinator and run state, GEDCOM person presentation and surname grouping, API request/response and event models, the dashboard and its tests, extraction-cache and result-storage path resolution, `.gitignore`, and user-facing documentation. The dashboard supports individual generation, checkbox-selected people, select-all checkboxes, and a distinct generate-all action. The existing local Ollama integration, evidence correlation, citation validation, and per-person identity keys remain in use.
