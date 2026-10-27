# Plan: JSON object deduplicator (CLI and microservice)

Revision: 2026-10-27; inspected baseline `d7f8635` plus the uncommitted scaffold (`src/main.rs`, `src/server.rs`, `src/cache.rs`, `.dockerfile`, `axum` in `Cargo.toml`).

This plan **supersedes** [runtime-implementation.md](runtime-implementation.md). The webhook replay runtime (scenario files, delivery scheduling, HTTP delivery, reports) and all JSON Schema functionality are dropped. Nothing in this plan is implemented yet; it changes no code and no readiness flag.

## Goals and scope

One Rust binary, two deployment modes sharing one deduplication core:

| Mode         | Invocation (proposed)                                              | Input                                        | Output                                              |
| ------------ | ------------------------------------------------------------------ | -------------------------------------------- | --------------------------------------------------- |
| CLI          | `webhook-lab dedupe --input events.json [--output out.json]`       | A `.json` file whose top level is an array of objects | Array of first occurrences, original order kept; summary on stderr |
| Microservice | `webhook-lab serve [--host 0.0.0.0] [--port 8080] [--window-ms 5000]` | HTTP `POST` of one object or an array        | JSON verdicts; duplicates remembered for `window-ms` |

Completion goals:

- [ ] CLI dedupes a file deterministically and never writes partial output.
- [ ] Service answers duplicate/unique correctly under concurrent identical requests, bounds memory, and shuts down cleanly on SIGTERM.
- [ ] Container image builds from the pinned toolchain, runs as non-root and passes a smoke test.
- [ ] Infrastructure, audit and workflow checks pass; runtime readiness flips only after new acceptance tests pass on Windows and Linux.

**Non-goals (v1):** JSON Schema validation of any kind, shared/distributed dedupe state (Redis etc.), persistence across restarts, authentication, TLS termination in-process (use the platform's ingress), streaming inputs larger than the configured file limit, NDJSON.

**Assumptions:** the binary keeps the name `webhook-lab` (renaming is a separate decision, see ledger). You still own the Rust implementation; the automation maintainer owns CI, readiness and release changes.

## Behavior to specify (new contract)

`docs/contract.md` is rewritten around these rules before stage 2 starts.

**Identity.** Two objects are duplicates when their canonical forms are equal. Canonical form: object keys sorted recursively, no insignificant whitespace, strings and numbers serialized exactly as `serde_json` preserves them. Optional `--key <json-pointer>` (e.g. `/id`) dedupes on one field instead of the whole object; an object missing that field is an error in the CLI and a `422` in the service.

**Input rules.** Valid UTF-8, exactly one JSON document, no trailing content. CLI top level must be an array; every element must be an object. Duplicate keys *inside* one object are rejected (serde_json silently keeps the last one, which would make two different inputs look identical). Size limits: CLI file ≤ 64 MiB by default (`--max-bytes`), service body ≤ 1 MiB (`DefaultBodyLimit`).

**Window.** The service remembers a canonical key for `window-ms` after first sight (default 5,000 ms, range 1..=86,400,000). A repeat inside the window is a duplicate; after expiry it is new again. The CLI dedupes the whole file and ignores the window (ledger item 2).

**CLI exits.** 0 = output written; 2 = invalid arguments/input or write failure. Output goes to stdout unless `--output` is given; `--output` uses a temporary sibling plus rename so a failed run never leaves a partial file. Input and output paths must differ.

**Service API.**

| Route            | Request                    | Response                                                                 |
| ---------------- | -------------------------- | ------------------------------------------------------------------------ |
| `POST /dedupe`   | One JSON object            | `200 {"duplicate": false}` first sight, `200 {"duplicate": true}` repeat |
| `POST /dedupe`   | Array of objects           | `200 {"unique": [...], "duplicates": n}` (intra-batch and cross-request) |
| `GET /healthz`   | —                          | `200` while serving, `503` once shutdown has begun                       |
| Any invalid body | —                          | `400` malformed, `413` too large, `415` wrong content type, `422` bad shape |
| Cache full       | —                          | `503` with `Retry-After` (ledger item 4)                                 |

Responses never echo payloads in error messages; logs record counts, status and latency only.

## Stages

| Stage | Depends on | Observable outcome                              | Status  |
| ----- | ---------- | ----------------------------------------------- | ------- |
| 0     | None       | Schema and webhook-replay assets removed        | Pending |
| 1     | 0          | CLI surface fixed; scaffold compiles            | Pending |
| 2     | 1          | Pure dedupe core with canonicalization          | Pending |
| 3     | 2          | CLI batch mode complete                         | Pending |
| 4     | 2          | TTL cache with bounded memory                   | Pending |
| 5     | 3, 4       | HTTP service with graceful shutdown             | Pending |
| 6     | 5          | Container image and deployment manifest         | Pending |
| 7     | 6          | CI, performance evidence and readiness          | Pending |

Stages 3 and 4 are independent and can proceed in either order. Each stage ends in one focused commit with its tests green.

### Stage 0: remove schema functionality and the replay runtime

- **Delete:** `schemas/report.schema.json`, `schemas/scenario.schema.json`, `examples/reorder-and-duplicate.json`, all `tests/fixtures/*.scenario.json` and `*.report.json`.
- **Edit harness:** drop `test_schema_shapes_track_fixture_fields` and the scenario/report validators in `tests/harness/support.py` and `tests/harness/test_infrastructure.py` (`schema_version`, `exact_keys`, delivery-row checks). Keep the receiver only if a later test needs it; otherwise remove it.
- **Replace:** `tests/acceptance.py` and `tests/performance.py` become dedupe suites (stage 3/5). Until then, `scripts/check.py runtime`/`performance` should report "not implemented" rather than run stale webhook tests.
- **Docs:** rewrite `README.md`, `docs/contract.md`, `docs/architecture.md`, `docs/implementation.md`, `docs/testing.md`; remove every `schema_version` reference; mark `runtime-implementation.md` superseded.
- **Dependencies:** `reqwest` is no longer needed by the runtime. Keep it only as a dev-dependency if Rust integration tests call the service over HTTP.
- **Exit gate:** `python scripts/check.py infrastructure` passes with no file referencing `schemas/` or `schema_version` (`git grep -n schema` matches only files under `docs/plans/`).

### Stage 1: CLI surface and scaffold fixes

The uncommitted scaffold does not compile and mixes both modes into one flat `Args`. Problems to resolve:

| Location             | Problem                                                                                                  | Plan                                                         |
| -------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `src/main.rs` imports | `clap::Parser` imported twice; `Subcommand` unused; `Runtime` not imported; `use tokio;` redundant       | Clean imports                                                |
| `Args.input_file`    | Required `String`, so `serve` mode cannot start without an input file                                     | Split into `dedupe` and `serve` subcommands (clap `Subcommand`) |
| `run_detatched`      | Misspelt; clap renders it `--run-detatched`, and the README still documents a `run` subcommand            | Replaced by the `serve` subcommand                           |
| `timeout_ms: i16`    | Signed, caps at 32,767 ms, accepts negatives, and it is a dedupe window, not a timeout                   | `window_ms: u64` with a clap range, converted to `Duration`  |
| `run_server` port    | `unwrap_or_else({ ... })` evaluates the block eagerly instead of passing a closure                       | Default port 8080 via clap; no manual exit                   |
| `concurrency`        | `worker_threads(0)` panics                                                                               | Range `1..=1024`; default `available_parallelism()`          |
| `src/server.rs`      | `mod cache;` inside `server.rs` resolves to `src/server/cache.rs`; `server_body` returns an `async` block from a `()` fn | Declare `mod cache;` in `main.rs`; make handlers `async fn` |
| Env vars             | Dockerfile sets `HOST`, `PORT`, `SERVER_MODE`, but nothing reads them                                    | Enable clap `env` feature: `--host`/`--port`/`--window-ms` read `HOST`/`PORT`/`WINDOW_MS`; drop `SERVER_MODE` (the subcommand decides the mode) |

- **Tests to add:** help/version exit 0; unknown flag exit 2; `serve` without input file starts; out-of-range window/port/concurrency rejected; env var fallback.
- **Suggested commit:** `feat(cli): split dedupe and serve subcommands`.

### Stage 2: pure deduplication core

- **Suggested paths:** `src/canonical.rs` (canonical bytes), `src/dedupe.rs` (first-occurrence filter over an iterator, key extraction by JSON pointer).
- **Tasks:** duplicate-aware parse that rejects repeated keys at every depth before building `serde_json::Value`; recursive key-sorted serialization; hash canonical bytes to a fixed-size key (ledger item 3) so memory per entry is bounded; batch filter that preserves order and returns counts.
- **Tests to add:** key order `{"a":1,"b":2}` == `{"b":2,"a":1}`; nested objects and arrays (array order matters); `1` vs `1.0` per ledger item 1; Unicode escapes vs literal characters; duplicate key rejection at depth; `--key` present/missing; empty array; 10,000 objects all duplicates.
- **Suggested commit:** `feat(dedupe): canonical identity and first-occurrence filter`.

### Stage 3: CLI batch mode

- **Tasks:** bounded read (`max-bytes + 1` then reject); validate top-level array of objects with element index in errors; run the stage 2 filter; write to stdout or atomically to `--output`; summary `read=N unique=U duplicates=D` on stderr.
- **Fixtures:** `tests/fixtures/<name>.input.json` with `<name>.expected.json` (cases: none-duplicated, all-duplicated, reordered keys, nested, key mode, empty).
- **Tests to add:** golden pairs; malformed/trailing JSON; non-array top level; non-object element; oversize file; same input/output path; existing output preserved on failure.
- **Suggested commit:** `feat(cli): dedupe JSON array files`.

### Stage 4: TTL cache

- **Suggested path:** `src/cache.rs`.
- **Tasks:** `check_and_insert(key, now) -> Seen | New` as one atomic operation under a short `std::sync::Mutex` (never held across `.await`) so two concurrent identical requests cannot both be `New`; expiry by stored `Instant`; a background sweep every `window/2` removes expired entries; hard `max_entries` cap (default 1,000,000) with the behavior chosen in ledger item 4. Shard the map only if profiling shows lock contention.
- **Tests to add:** repeat inside/after window using Tokio paused time; concurrent identical inserts yield exactly one `New`; cap reached; sweep frees memory.
- **Suggested commit:** `feat(cache): bounded TTL dedupe cache`.

### Stage 5: HTTP service

- **Suggested path:** `src/server.rs`.
- **Tasks:** axum router for the API table above; shared state `Arc<Cache>` plus config; `DefaultBodyLimit`; JSON content-type enforcement; `axum::serve(...).with_graceful_shutdown` on SIGTERM and Ctrl-C (enable tokio `signal` and `net` features), with `/healthz` returning 503 during drain; structured logs via `tracing` (counts and latency only, never payloads).
- **Dependency check:** the scaffold pins axum 0.7; check crates.io for the current release and prefer it unless a reason exists, and run `python scripts/check.py audit` after adding `tracing`/`tower-http`.
- **Tests to add (black-box, against the real binary on an ephemeral port):** first/repeat verdicts; batch with intra-batch duplicates; window expiry; 400/413/415/422; cache-full 503; SIGTERM finishes in-flight requests then exits 0.
- **Suggested commit:** `feat(server): serve dedupe API with graceful shutdown`.

### Stage 6: container and deployment

- **Dockerfile** (rename `.dockerfile` → `Dockerfile` so `docker build .` finds it):
    - Builder `rust:1.99.1-slim` to match `rust-toolchain.toml` (the scaffold's `rust:1.80` cannot build edition 2024); `cargo build --release --locked`.
    - Copy `target/release/webhook-lab` (the scaffold copies a non-existent `dedup-tool`).
    - Runtime `gcr.io/distroless/cc-debian12:nonroot` or `debian:bookworm-slim` with a created non-root user; no TLS certs needed because the service makes no outbound calls.
    - `ENV HOST=0.0.0.0 PORT=8080`; `ENTRYPOINT ["./webhook-lab"]`, `CMD ["serve"]`.
    - Cache dependency builds with a dummy-`main` layer or `cargo-chef` if build time matters.
- **Add `.dockerignore`:** `target/`, `.venv/`, `.tools/`, `.bench-results/`, `.git/`; without it the build context ships the virtualenv and binaries.
- **Deployment manifest (example, e.g. `deploy/compose.yaml` or a Kubernetes Deployment):** one replica, liveness/readiness on `/healthz`, `terminationGracePeriodSeconds` > drain time, memory limit sized from `max_entries` × measured bytes per entry.
- **Scaling caveat:** the cache is per process. Running more than one replica splits dedupe state, so duplicates routed to different replicas are not caught. v1 runs a single replica; horizontal scaling requires a shared store (non-goal) or consistent-hash routing on the dedupe key.
- **Verification:** `docker build -t webhook-lab .`; `docker run -p 8080:8080 webhook-lab`; POST the same object twice and see `false` then `true`; `docker stop` exits within the grace period.
- **Suggested commit:** `build(docker): container image for dedupe service`.

### Stage 7: CI, performance and readiness

- **CI (automation maintainer):** run the new acceptance suites in `scripts/check.py runtime`; add a container build plus smoke-test job on Linux; keep CodeQL, audit and secret scanning.
- **Performance:** replace `tests/performance.py` with two workloads: CLI on a 50 MB file with ~50% duplicates; service at fixed concurrency for 60 s. Record throughput, p99 latency, peak RSS and bytes per cache entry; set explicit budgets before claiming them.
- **Readiness:** flip `project-status.json` to implemented only after local and hosted runtime + performance evidence on Windows and Linux. Release packaging adds the container image only if publishing an image is decided (ledger item 6).
- **Suggested commits:** `ci(runtime): run dedupe acceptance and container smoke test`, then `chore(readiness): record verified dedupe implementation`.

## Decision ledger

| #   | Decision                                   | Recommendation                                                                                         | Resolve in |
| --- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ---------- |
| 1   | Is `1` equal to `1.0`?                     | No: compare numbers as written, so no precision is lost; document it                                    | 2          |
| 2   | Does the CLI honor `window-ms`?            | No: whole-file dedupe. Revisit only if inputs carry a timestamp field                                   | 1          |
| 3   | Store canonical bytes or a hash?           | SHA-256 digest (`sha2` crate, 32 bytes/entry); collision risk is negligible and memory stays bounded    | 2          |
| 4   | Cache full: reject or evict?               | Reject with 503 + `Retry-After`; evicting silently lets duplicates through                              | 4          |
| 5   | Keep the `webhook-lab` name?               | Keep for now; rename crate, binary, repo and docs together in one later commit if wanted                | 0          |
| 6   | Publish a container image on release?      | Not in v1; release keeps binary archives, image publishing is a separate workflow decision              | 7          |
| 7   | Batch response shape                       | Return `unique` objects plus `duplicates` count; per-item verdicts only if a client needs them          | 5          |

Replace each stage's status only after its exit gate holds: record commit, tests added, commands run, platform and remaining gaps. Compiling is not completion.
