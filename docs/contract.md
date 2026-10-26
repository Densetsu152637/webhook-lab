# Public contract v1

Status: specification and test infrastructure exist; the Rust runtime is **pending implementation**. The current binary exits 78 and does not parse arguments or send requests.

## Command

```text
webhook-lab run --scenario scenario.json --target http://127.0.0.1:8080/hook --report report.json
```

All three options are required. Paths are interpreted relative to the caller's working directory. Scenario and report paths must differ. A report is a UTF-8 JSON file; stdout is not a report channel. Diagnostics go to stderr. Targets must be absolute HTTP(S) URLs with a host, no username/password, and no fragment. Redirects are disabled. V1 has no retries, authentication configuration, provider signature generation, random scheduling, or response-body capture. Use synthetic fixtures against endpoints you own.

## Scenario

See `schemas/scenario.schema.json` and `examples/reorder-and-duplicate.json`. All fields are required; reject unknown fields at every defined record boundary. `payload` is an arbitrary JSON object, so its own keys are unrestricted.

| Field | Rule |
| --- | --- |
| `schema_version` | Integer 1 |
| `timeout_ms` | Integer 1..60,000 |
| `concurrency` | Integer 1..64 |
| `events` | Up to 10,000 `{id, payload}` objects; unique ASCII IDs matching `[A-Za-z0-9._-]{1,128}` |
| `deliveries` | Up to 10,000 `{event, at_ms}` objects; event references an existing ID with the same safe ASCII pattern |
| `at_ms` | Integer 0..60,000; nondecreasing across deliveries |

Boolean and fractional values are not integers. Empty deliveries are valid. The entire scenario file is limited to 1,048,576 bytes, including whitespace. Reject invalid UTF-8, malformed JSON, duplicate JSON object keys, missing fields, unsupported versions, invalid ranges/types, duplicate event IDs, unknown references, decreasing offsets, unreadable files, and invalid targets **before sending any request**. Existing report files must not be touched on validation failure. JSON Schema documents structural constraints; cross-field and byte-size constraints need semantic validation.

One delivery sends one POST with JSON payload, `Content-Type: application/json`, and `X-Webhook-Lab-Event-Id` equal to the event ID. JSON formatting and object-key order are not meaningful; values must be preserved. Repeated references deliver the same payload and event ID. List references in a different order to simulate reordered events.

The monotonic run clock starts after complete validation. `at_ms` is the earliest eligibility time, not a delivery deadline. Dispatch waits for an available concurrency slot; the request timeout starts at dispatch and excludes queue time. Plan ties are dispatched in list order. Concurrency 1 preserves receiver arrival order; concurrency >1 does not promise arrival/completion order. Bound in-flight requests by `concurrency`, and drain all dispatched work before writing the report. Timeouts release their slots. Schedule accuracy is approximate and subject to OS scheduling.

## Report and errors

See `schemas/report.schema.json` and `tests/fixtures/*.report.json`. Reports contain exactly `schema_version`, `deliveries`, and `summary`. Delivery rows contain exactly `index`, `event`, `scheduled_at_ms`, `outcome`, and `http_status`. Rows are ordered by zero-based delivery index regardless of completion order. The summary has `total`, `succeeded`, and `failed`, consistent with the rows. Reports contain no timings, response bodies, target URLs, raw library diagnostics, or local paths.

| Outcome | HTTP status |
| --- | --- |
| `success` | 200..299 |
| `http_error` | Other final HTTP status, including unfollowed 3xx |
| `timeout` | null |
| `transport_error` | null |

| Exit | Meaning |
| --- | --- |
| 0 | Complete report; every delivery successful, including an empty run |
| 1 | Complete report; one or more delivery failures |
| 2 | Invalid arguments/input, report-write failure, or other command-level failure |
| 78 | Current scaffold only: runtime not implemented |

A run with delivery failures still writes a complete report. Report-write failure overrides delivery exit status and must not claim success. Use a temporary sibling and atomic replacement where supported so an existing report is not replaced with partial JSON. A scenario path equal to the report path is invalid input. Diagnostics should identify the failure category and relevant field/index without echoing payloads, credentials, full private file paths, or response bodies. Ctrl-C/cancellation semantics are intentionally deferred; the harness enforces a process-level timeout and does not establish cancellation support.
