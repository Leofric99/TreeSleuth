# Spec Delta

## Purpose

This capability provides persistent local diagnostics for TreeSleuth execution so users can investigate failures after the process ends. It keeps generated logs in a hidden repository directory that is excluded from version control.

## ADDED Requirements

### Requirement: Persist detailed execution diagnostics locally
TreeSleuth SHALL write verbose diagnostic records to a persistent log file under a hidden directory in the repository, including timestamps, severity, and the context needed to identify the operation and analyze its outcome.

#### Scenario: Application starts
- **WHEN** TreeSleuth starts through its supported application entry points
- **THEN** it creates the hidden log directory and writes subsequent diagnostic records to a local log file without requiring the user to create the directory

#### Scenario: The process exits and starts again
- **WHEN** a user examines the diagnostic log after an execution or starts another execution
- **THEN** records from prior executions remain available and new records are appended or retained in the same log destination

### Requirement: Record errors with actionable context
TreeSleuth SHALL log application errors and recoverable processing failures with their severity, operation context, relevant run or source identifiers, exception details, and traceback when an exception is available.

#### Scenario: A processing operation fails
- **WHEN** a pipeline, extraction, cache, analysis, or result-writing operation encounters an error
- **THEN** the log identifies the failed operation and includes available diagnostic context and exception traceback while the existing user-facing warning or failure reporting remains intact

#### Scenario: An API operation returns an error
- **WHEN** an application API operation encounters an error while processing a request
- **THEN** the error is recorded locally with request-operation context and any available exception details, without changing the response contract

### Requirement: Keep generated logs out of version control
TreeSleuth SHALL exclude its generated diagnostic log files from Git while leaving the log files available on the local machine.

#### Scenario: A log file is generated in a Git working tree
- **WHEN** TreeSleuth creates or updates a diagnostic log
- **THEN** Git does not report the generated log file as an untracked or modified file

### Requirement: Preserve existing reporting and local privacy boundary
Persistent logging SHALL supplement, not replace, existing console, API, pipeline-event, and dashboard error reporting, and SHALL keep diagnostic records on the local machine.

#### Scenario: An error is reported to a user
- **WHEN** an error is already returned or published by TreeSleuth
- **THEN** that reporting continues unchanged while the corresponding diagnostic information is also written locally

#### Scenario: Execution produces detailed diagnostics
- **WHEN** diagnostic records include research paths or detailed processing context
- **THEN** those records remain local and are not sent to a hosted logging service
