# Local API

The API is served by the local TreeSleuth process. Its default bind address is
loopback; it does not enable cross-origin access. Paths in request bodies must
be absolute paths on the host where TreeSleuth is running. The selected
research directory must exist and be readable.

## Check Ollama

`GET /api/system-check` returns whether Ollama is reachable and the names of
installed local models.

```json
{
  "ollama_available": true,
  "models": ["qwen2.5:14b"],
  "error": null
}
```

If the local service cannot be reached, `ollama_available` is false and
`error` contains the reason; the response does not imply a successful check.

## Preview a directory

`POST /api/analyze-directory` accepts:

```json
{"path": "<absolute-local-directory-path>"}
```

It returns the selected root, GEDCOM and document counts, counts grouped by
file type, and `has_gedcom_baseline`. This structural preview does not start
OCR or model inference. An invalid or unreadable path returns HTTP 400 with a
path-specific `detail`.

## Start and monitor a pipeline

`POST /api/run-pipeline` accepts:

```json
{
  "path": "<absolute-local-directory-path>",
  "model": "qwen2.5:14b"
}
```

On acceptance it returns HTTP 202:

```json
{
  "run_id": "<run-id>",
  "events_url": "/api/runs/<run-id>/events"
}
```

The run is independent of the event-stream connection. `GET
/api/runs/<run-id>/events` streams server-sent events as they occur and
continues until a terminal `complete` or `error` event. The API uses the
following event names:

- `stage`: pipeline stage transition and scan summary
- `file`: file discovery, extraction, or person correlation
- `person`: person status and, when complete, biography and conflict data
- `warning`: recoverable per-file or per-person issue
- `error`: terminal pipeline failure
- `complete`: successful terminal result

Each SSE message has an integer `id`, an `event` name, and a JSON `data`
payload containing `run_id`, `sequence`, `event`, `stage`, `message`, and
optional source/person details. Clients may reconnect with `Last-Event-ID` to
resume after the latest event still retained by the bounded in-memory event
buffer. Closing the stream does not cancel a running analysis.

`GET /api/runs/<run-id>` returns the current run status, people, warnings, and
any terminal error. Person statuses are `Idle`, `Parsing Records`,
`Comparing with GEDCOM`, `Writing Biography`, `Finished`, or `Failed`.
Successfully completed biographies and conflict reports are saved beneath
the selected root's `output` directory; the API does not provide arbitrary
filesystem reads.

Invalid requests return HTTP 422, invalid directories return HTTP 400,
unknown run IDs return HTTP 404, and run-capacity limits return HTTP 429.
Ollama and model failures are reported in system-check or pipeline status
without disguising an incomplete run as successful.
