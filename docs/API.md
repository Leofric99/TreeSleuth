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

On acceptance it returns HTTP 202. This operation scans the folder and parses
GEDCOM first, publishing each GEDCOM person before document extraction starts.
It then reads supported documents and correlates their evidence without
checking Ollama, auditing conflicts, or generating biographies:

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

- `stage`: preparation stage transition and scan summary
- `file`: file discovery, extraction, or person correlation
- `person`: early GEDCOM identity, preparation status and document count, or
  the status and result of explicitly requested story generation
- `warning`: recoverable per-file or per-person issue
- `error`: terminal preparation or generation failure
- `complete`: successful preparation or generation result

Each SSE message has an integer `id`, an `event` name, and a JSON `data`
payload containing `run_id`, `sequence`, `event`, `stage`, `message`, and
optional source/person details. Clients may reconnect with `Last-Event-ID` to
resume after the latest event still retained by the bounded in-memory event
buffer. Closing the stream does not cancel a running analysis.

`GET /api/runs/<run-id>` returns the current run status, people, warnings, and
any terminal error. Prepared people have `Ready` status after their document
counts are known. Preparation returns without generating stories.

## Generate stories

After preparation completes, `POST /api/runs/<prepared-run-id>/generate`
accepts a single-person request:

```json
{"person_id": "<person-id-from-run>"}
```

or an empty object to request stories for everyone:

```json
{}
```

It also accepts a selected group of people:

```json
{"person_ids": ["<person-id-1>", "<person-id-2>"]}
```

The `person_id` and `person_ids` forms are mutually exclusive. The dashboard
uses the selected-people form for checked individuals and the empty object for
the explicit generate-all action.

The operation returns a new generation `run_id` and `events_url` and reports
progress and individual outcomes independently. Its snapshot includes
`parent_run_id`, which identifies the prepared run. A person already being
generated cannot be requested again concurrently.

Person statuses are `Idle`, `Parsing Records`, `Comparing with GEDCOM`,
`Writing Biography`, `Ready`, `Finished`, or `Failed`. Successfully completed
biographies, conflict reports, and structured analysis are saved beneath the
repository's gitignored `.cache` directory; extraction cache and surname
display mappings are also stored there. This is the only application-managed
write allowed inside the selected research folder when that folder contains
the repository. The API does not provide arbitrary filesystem reads.

Invalid requests return HTTP 422, invalid directories return HTTP 400,
unknown run or person IDs return HTTP 404, generation before preparation is
ready and duplicate person-generation requests return HTTP 409, and
run-capacity limits return HTTP 429. Ollama and model failures are reported in
system-check or generation status without disguising incomplete work as
successful.
