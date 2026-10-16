# Proposal

## Why

TreeSleuth currently has no persistent application log destination, so diagnostic messages and unexpected execution failures can be lost when the process exits. Detailed, local log files will make failures easier to investigate while keeping generated logs out of version control.

## What Changes

- Configure verbose file logging for application execution, recording errors and the context needed to analyze them, including exception tracebacks and detailed processing diagnostics.
- Store generated logs in a hidden directory within the repository and ensure the log files are ignored by Git.
- Preserve existing user-facing warnings, pipeline events, and console behavior while adding persistent diagnostics.

## Capabilities

### New Capabilities
- `diagnostic-logging`: Persistent, detailed local diagnostics for TreeSleuth execution, with generated log files excluded from version control.

### Modified Capabilities

## Impact

- Application startup and logging setup in `treesleuth`.
- Existing error and warning reporting across the API, pipeline, extraction, cache, and result-writing paths.
- `.gitignore` and logging-related tests.
- Log files may contain sensitive research paths and detailed processing context; they remain local and are not committed.
