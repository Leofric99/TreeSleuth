# Tasks

## 1. Configure persistent local logging

- [x] 1.1 Add idempotent DEBUG-level file logging under `.treesleuth/logs/treesleuth.log` with append and rotation behavior; verify startup, repeated configuration, persistence across restarts, and rotation with focused tests.
- [x] 1.2 Ignore generated files under `.treesleuth/logs/` and document the log location and sensitivity in the README; verify the ignore rule with `git check-ignore` and confirm the documented path matches the implementation.

## 2. Capture actionable application failures

- [x] 2.1 Initialize logging for command-line and ASGI startup without replacing existing console handlers; verify both supported startup paths create one active file handler and preserve existing console reporting.
- [x] 2.2 Add diagnostic records at handled API and processing failure boundaries, including available operation and run/source context and exception tracebacks; verify API responses and pipeline events remain unchanged while failures are present in the log.
- [x] 2.3 Run focused logging, API, pipeline, extraction, cache, and result tests; verify existing behavior passes alongside assertions for persistent detailed diagnostics.
