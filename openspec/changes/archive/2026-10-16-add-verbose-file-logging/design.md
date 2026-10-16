# Design

## Context

The application uses module-level Python loggers in several processing modules, but it does not configure a persistent handler. Pipeline failures are logged with a traceback; recoverable cache and extraction issues are logged inconsistently, and API handlers may return errors without logging them. The application is launched through `treesleuth.__main__` and also exposes an ASGI app from `treesleuth.main`.

## Goals / Non-Goals

**Goals:**
- Initialize persistent verbose diagnostics for both the documented command-line launch and direct ASGI app startup.
- Include error context and tracebacks where available while retaining existing user-visible error behavior.
- Keep logs in a hidden repository-local directory, append across restarts, and ensure Git ignores generated logs.

**Non-Goals:**
- Add a remote logging service, a log viewer, or a new API for downloading logs.
- Change error response shapes, pipeline events, or recovery behavior.

## Decisions

- Use the standard Python logging package and attach a DEBUG-level file handler to the `treesleuth` logger. Existing module loggers are already descendants of this namespace. Keep logger propagation and existing console handlers intact, and make configuration idempotent so importing and launching the ASGI app does not duplicate records.
- Store logs under `.treesleuth/logs/treesleuth.log` in the source repository, deriving the repository directory from the installed package location rather than the selected research directory. Create the directory on startup and append to existing records. Keep rotated log files alongside the active log.
- Use size-based rotation (10 MiB per file, retaining five backups) to bound disk use without discarding the most recent diagnostic history. The active and rotated files share the Git-ignored log directory.
- Extend logging at existing handled-error boundaries in API and processing paths. Record operation, run/source/person context where available, the diagnostic details already available to the operation, and exception tracebacks when an exception object exists. Leave normal response, warning, and event handling unchanged.
- Treat log content as sensitive local data: detailed processing diagnostics can include genealogy paths and content. Do not transmit logs, and document their location and sensitivity; the ignore rule prevents generated logs from being committed.

## Risks / Trade-offs

- Detailed logs may expose sensitive family research to anyone with access to the local account or checkout → keep the output local, ignore the entire generated-log directory, and document its contents and location.
- Rotated files eventually discard older records → retain several backups to balance diagnosis history and bounded disk use.
- Logging setup can accidentally suppress existing console output or duplicate records → add the file handler without replacing other handlers and test repeated setup and both supported startup paths.

## Migration Plan

No migration is required. On startup, the application creates `.treesleuth/logs` if missing and appends to the active log. Rolling back the code stops new log writes; locally generated files can remain for investigation or be removed by the user.
