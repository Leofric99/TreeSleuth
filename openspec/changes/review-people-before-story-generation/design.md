# Design

## Context

See proposal.md for motivation and the capability spec deltas for behavior. Today a pipeline run parses GEDCOM, extracts documents, correlates them, and immediately audits and generates biographies. The selected research root is also used for `.tree_cache` and `output`. The application repository is available from the installed `treesleuth` package location, and the existing `.gitignore` rule excludes `.cache`.

## Goals / Non-Goals

**Goals:**

- Make GEDCOM identities visible before document extraction or model inference.
- Keep document preparation separate from user-triggered story generation.
- Store extracted text, surname display mappings, and generated outputs in a repository-local, ignored application data directory.
- Preserve GEDCOM identity and source data while providing durable surname display aliases.

**Non-Goals:**

- Change GEDCOM records, merge person identities, or alter the evidence-correlation and citation-validation rules.
- Migrate or delete existing cache and result files from selected research folders.
- Add persistence for run history or make previously generated results available after an application restart.

## Decisions

### Split preparation from generation

The preparation run will scan the selected tree, parse GEDCOM immediately after discovery, publish the resulting people and their initial statuses, then extract and correlate documents without calling the model for audits or biographies. At preparation completion it will publish updated document counts and a ready status. When there is no usable GEDCOM, provisional people can only be formed after document extraction.

Story requests will run as separate generation jobs associated with the prepared run. Provide operations for one selected person, a checkbox-selected set of people, and all people; each job reports progress and per-person success or failure. The selected-set request passes person IDs as a batch, while the all-people request remains distinct. Jobs reuse the prepared index, document text, and associations, then perform the existing audit and biography calls and save their outputs. Separate jobs preserve the preparation run's terminal status and event-stream behavior while allowing more than one explicit generation request.

An ordinarily sized GEDCOM parse should emit the people list within a few seconds, before OCR or inference. Very large trees remain subject to local filesystem and parser performance.

### Keep surname aliases as presentation data

Store aliases separately from `IndividualRecord`, keyed by a normalized original surname and scoped to the selected research root. In the dashboard, users choose a source spelling and a destination surname from dropdowns, then confirm the merge. The chosen display surname changes only the person's effective surname and group; person IDs, original GEDCOM names, and correlation inputs remain unchanged. Persist aliases in the app cache so they apply to later runs, and report failed reads or writes rather than claiming a merge was saved.

Display people in alphabetically ordered, collapsible surname groups. Groups start collapsed so the user can open only the family names they want to review. Once preparation completes, enable each person's generation action and checkbox selection, with select-all and a separate generate-all action. Keep selections tied to stable person IDs.

### Use one repository-local application data root

Resolve the application data root from the installed package/repository location rather than the selected research root or process working directory. Place extraction cache, per-research-root surname aliases, and generated story/conflict/analysis files in distinct `.cache` subdirectories. Scope extraction and alias data by a stable hash of the canonical selected-root path so different research folders cannot reuse each other's state; retain source-content and extractor-identity validation for extracted text. Keep deterministic person-identity suffixes and atomic writes for generated files.

The existing `.cache` ignore rule already excludes this directory from version control. Exclude the application-owned `.cache` from directory discovery, including when the selected research folder contains the repository. In that overlap case `.cache` is the sole allowed application-managed write inside the selected folder; no research documents, generated stories, logs, or other application files are written there. Retain exclusions for legacy `.tree_cache` and `output` folders so old generated data is not re-ingested.

### Preserve per-person failure isolation

A generation job for all people will process each person independently. Insufficient evidence, model errors, or result-write errors remain visible for the affected person and do not prevent later people from being attempted. Cache read/write failures remain explicit warnings; fresh extraction can continue where possible. A result cannot be marked complete until its output is safely written.

## Risks / Trade-offs

- [Very large GEDCOM trees can take longer than a few seconds to parse] → Publish immediately after parsing and guarantee that extraction/OCR/model inference cannot delay the people list; exercise timing with a representative fixture.
- [The repository may be read-only or cache writes may fail] → Keep extraction fallback behavior and report cache failures; report result persistence failures as failed generation rather than success.
- [Users may select the repository as their research root] → Treat only TreeSleuth's own ignored `.cache` as application state and exclude it from source discovery; write no other application data under the selected path.
- [Existing selected-folder cache/results will not be migrated] → Leave these files untouched and excluded from future scans; use the new repository cache for subsequent work.
- [Separate generation jobs can overlap] → Enforce the existing active-work limits and prevent duplicate concurrent generation for the same person in one prepared run.

## Migration Plan

No destructive migration is performed. New runs use the repository-local `.cache`; previously written `.tree_cache` and `output` directories in research folders remain untouched and excluded from ingestion. Verify that `.cache` is ignored before using it for application data.
