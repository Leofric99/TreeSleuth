# Tasks

## 1. Repository-Local Application Data

- [x] 1.1 Add an application-data root anchored to the TreeSleuth package/repository and scope extraction-cache entries by canonical research root; update cache tests to verify root isolation, reuse, and cache warnings under `.cache`.
- [x] 1.2 Store biography, conflict, and analysis outputs under the application `.cache` while preserving atomic writes and person-identity filenames; update result tests to verify no result files are created in the selected research folder, including when it contains the repository.
- [x] 1.3 Exclude the application `.cache` from source discovery while retaining legacy `.tree_cache` and `output` exclusions; verify with directory-scanner tests and document the app-owned cache boundary in the README.

## 2. Separate GEDCOM and Document Preparation from Generation

- [x] 2.1 Parse GEDCOM before document extraction and publish all available individuals and initial statuses immediately; test that the people event precedes a deliberately blocked extractor and that parse failures are reported without dropping other valid trees.
- [x] 2.2 Complete document extraction and person correlation without calling audit or biography inference, then publish prepared people with document counts; test GEDCOM-backed and provisional-person preparation and verify that generation has not run.
- [x] 2.3 Add separate single-person and generate-all jobs that reuse prepared evidence, report progress and per-person failures independently, and prevent duplicate concurrent generation for one person; cover API, SSE, capacity, and error behavior with pipeline/API tests and update `docs/API.md`.

## 3. Surname Mapping and Dashboard Actions

- [x] 3.1 Persist validated surname display mappings under root-scoped application `.cache` state without changing GEDCOM identities; add tests for merging variants, persistence across runs, and isolation between selected roots.
- [x] 3.2 Display people grouped and sorted by effective surname, and add a control to map surname variants to a chosen display name; add browser tests for sorting, unchanged person identity, and retained mappings.
- [x] 3.3 Add per-person and generate-all story controls that remain unavailable until preparation completes, display generation statuses/results, and handle failures explicitly; add browser coverage for both actions and update README workflow instructions.
- [x] 3.4 Add expandable surname groups, source/destination surname selectors, per-person checkboxes, select-all and individual/selected/all generation actions; cover the controls and selected-person API batch with browser and API tests.
- [x] 3.5 Start surname groups collapsed by default while retaining the ability to expand them; add or update browser coverage for the initial collapsed state.
