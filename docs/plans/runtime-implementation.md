# Plan: implement the webhook-lab runtime

Revision: 2026-10-26; inspected baseline `11cab783d5cd7806770243d451a29b4bb2b29a67`.

## Goals and scope

This is a future implementation roadmap for the learner. The current executable is still the exit-78 placeholder; creating this plan implements no runtime behavior and changes no readiness flag.

Completion goals:

- [ ] Actual executable passes complete acceptance and added correctness tests: `python scripts/check.py runtime` and `cargo test --locked`.
- [ ] Infrastructure, dependency/license and workflow checks pass: `python scripts/check.py infrastructure`, `python scripts/check.py audit`, `python scripts/check.py workflow`.
- [ ] Validated release-build performance passes the explicit budget on Windows and Linux, with machine/workload metadata: `python scripts/check.py performance` plus its artifact and hosted logs.
- [ ] Only after local and hosted runtime/performance evidence exists, readiness changes to implemented and hosted CI actually runs and passes its runtime job.

**Scope:** strict validation, canonical reports, one-attempt HTTP delivery, monotonic scheduling, bounded concurrency, safe persistence and measured verification. **Non-goals:** random scheduling, retries, provider signing, authentication configuration, UI, database, public hosting, plugin APIs and cancellation guarantees. This plan-writing task executes no release.

**Assumptions:** you own all Rust implementation; Rust 1.99.1 and Cargo.lock are the baseline; fixtures use synthetic data and endpoints you control. Proposed files below are suggestions, not frozen internal APIs. Introduce modules when their responsibility exists, rather than creating every empty module or a trait per operation.

**Relevant paths:** `src/`, `tests/acceptance.py`, `tests/fixtures/`, `tests/harness/`, `tests/performance.py`, `schemas/`, `scripts/check.py`, `scripts/prepare_release.py`, `project-status.json`, `.github/workflows/`.

**Precedence:** [public contract](../contract.md) > this plan. Also read [architecture](../architecture.md), [testing](../testing.md), [development](../development.md) and the [short implementation guide](../implementation.md). Resolve any contract/schema/test disagreement before claiming completion. Contract decisions below require explicit documentation alignment; they do not silently change the existing contract.

## Stages and verification method

| Stage | Depends on | Observable outcome | Status |
| --- | --- | --- | --- |
| 0 | None | Verified foundation | Done, infrastructure only |
| 1 | 0 | CLI/help/errors | Pending |
| 2 | 1 | Full validation before effects | Pending |
| 3 | 2 | Empty run and safe canonical report | Pending |
| 4 | 3 | One classified HTTP attempt | Pending |
| 5 | 4 | Complete sequential plans | Pending |
| 6 | 5 | Monotonic delayed dispatch | Pending |
| 7 | 6 | Bounded concurrency and draining | Pending |
| 8 | 7 | Correctness/platform gaps closed | Pending |
| 9 | 8 | Performance evidence and readiness | Pending |

Keep completed-stage tests green; leave readiness pending through stages 1-8 and stage 9 verification. Each stage ends with a focused commit and a recorded outcome: revision, tests added, commands/results/platform, remaining gaps and next responsibility. All future-stage outcomes below are currently **unimplemented, no evidence**.

Commands already available, run from the repository root:

```text
cargo test --locked
cargo build --locked
python scripts/check.py infrastructure
python scripts/check.py runtime
python scripts/check.py performance
python scripts/check.py audit
python scripts/check.py workflow
```

Infrastructure includes format/lint/build/Rust tests plus 14 harness self-tests and 5 automation guard tests at this baseline. Runtime correctness is separate. Auditing/workflow tools require the documented development setup. Keep Python assertions enabled: no `-O` or nonzero `PYTHONOPTIMIZE`.

The complete direct acceptance command is:

```text
python tests/acceptance.py --binary target/debug/webhook-lab
```

Windows can use the `.exe` suffix or let the harness resolve it. The runner requires `--binary`, has no filter option, and fails fast at `test_01_success` today. To test empty/rejection milestones first, initialize its module-level `BINARY` and select existing methods:

```text
python -c "import sys, unittest; sys.path.insert(0, 'tests'); import acceptance as a; a.BINARY=a.resolve_binary('target/debug/webhook-lab'); suite=unittest.TestSuite(a.RuntimeAcceptance(name) for name in sys.argv[1:]); result=unittest.TextTestRunner(verbosity=2, failfast=True).run(suite); sys.exit(0 if result.wasSuccessful() else 1)" test_empty test_rejections_send_nothing
```

This works in PowerShell and POSIX shells. Build first; change only the trailing method names to select cases from the matrix below. Do not run `python -m unittest tests.acceptance` without initializing `BINARY`. This exact recipe was executed on the scaffold: it reached `test_empty` and correctly failed with `78 != 0`, exit 1. No passing application was mocked.

## Stage 0: retain the verified foundation

- **Objective:** begin from a verified development environment while recognizing pending behavior.
- **Depends on / owned paths:** none; existing tooling and fixtures only.
- **Status/outcome:** done for infrastructure. [Recorded provenance](../development.md#initial-foundation-verification) identifies hosted Linux/Windows [CI](https://github.com/Densetsu152637/webhook-lab/actions/runs/40319635150) and [CodeQL](https://github.com/Densetsu152637/webhook-lab/actions/runs/40319635308) at `49b23da2f96a82a1601a3facb48f5e28a233c323`. Inspected plan baseline is `11cab783...`; runtime remains four-line exit 78 and status pending.
- **Tasks/checks:** confirm the pinned toolchain and lockfile; read one scenario/report pair; run `python scripts/check.py infrastructure` when starting implementation.
- **Exit gate:** foundation checks pass and the learner understands why runtime acceptance fails. Infrastructure green is not an application pass.
- **Rust focus / handoff:** learn Cargo's build/test workflow; no dependency upgrades or speculative modules are necessary. **Suggested commit:** none for this historical stage.

## Stage 1: CLI and diagnostic boundary

- **Objective:** predictable argument parsing, help/version and sanitized errors.
- **Depends on:** 0. **Suggested paths:** `src/main.rs` orchestrates exits; add `src/cli.rs` and `src/error.rs` only when useful; new CLI tests under `tests/`.
- **Tasks:**
  - Parse `run` and its three required options with clap. Keep parsing separate from network/file-writing effects.
  - Explicitly settle the conventional help/version exception: exit 0 for `--help`/`--version`, exit 2 for malformed arguments. The current exit table describes completed runs without spelling out this exception; align the contract when implementing it.
  - Keep reports file-based; diagnostics go to stderr and identify category/field/index without raw payloads, credentials, full private paths or response bodies. Clap help text is distinct from application diagnostics.
- **Existing checks:** infrastructure/self-tests. Existing runtime cases are mostly still red.
- **Tests to add:** root/run help, version, unknown subcommand/flag, each missing option, exit/stream conventions, no request/report on argument errors. Avoid asserting every word of clap formatting.
- **Verification:** `cargo test --locked`, `cargo build --locked`; after implementation, `cargo run --locked -- --help` and `cargo run --locked -- --version`.
- **Exit gate:** new CLI tests pass, help/version decision is documented, invalid arguments exit 2 without effects, infrastructure passes.
- **Rust focus/pitfall:** derive macros, enums and `Result`; do not exit deep inside helpers and bypass cleanup.
- **Suggested commit:** `feat(cli): add parsing and sanitized errors`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** pass parsed configuration to validation, not global mutable state.

## Stage 2: bounded strict input validation

- **Objective:** reject invalid inputs before sending requests or touching an existing report.
- **Depends on:** 1. **Suggested paths:** `src/scenario.rs` for reading/strict decoding and validated types; a separate validation module only if cohesive; boundary tests under `tests/`.
- **Tasks:**
  - Read at most 1,048,577 bytes (1 MiB + 1), rejecting the extra byte; a metadata check followed by an unbounded read is insufficient. Validate UTF-8, exactly one JSON document and no trailing content.
  - Reject all duplicate object keys, including nested payload objects, before conversion into `serde_json::Value` loses overwritten keys. Use a duplicate-aware deserialization path/visitor; typed outer structs alone do not solve payload duplicates.
  - Require fields; deny unknown keys at defined scenario/event/delivery boundaries while allowing arbitrary payload keys. Decode strict integers without bool/fraction coercion; enforce every range, count, reference, unique ID and nondecreasing offset.
  - Validate event IDs/references as safe ASCII `[A-Za-z0-9._-]{1,128}` before header construction. Validate absolute HTTP(S) URL, host, no credentials and no fragment using a URL parser, without DNS probes.
  - Resolve paths relative to the caller. Reject identical/normalized scenario/report paths; preserve the input and existing report on validation failure. Decide/test symlink and hard-link identity behavior on Windows/Linux, justifying any small extra identity dependency. Document unsupported alias cases and hostile filesystem replacement races explicitly; do not promise race-proof checks.
  - Resolve payload number/depth support before conversion: the contract requires value preservation without defining its precision/depth envelope. Do not silently round large numbers or invent an undocumented rejection limit.
- **Existing cases (selective recipe):** `test_rejections_send_nothing`, `test_invalid_target_sends_nothing`, `test_scenario_report_paths_must_differ`.
- **Tests to add:** exact byte/count/type/range boundaries; nested duplicates/unknown record fields; 128/129-character IDs; fractional/exponent integer syntax; malformed/trailing JSON; supported numeric fidelity; URL edge cases; relative paths and supported aliases; existing report unchanged for every invalid case. Deterministically generated cases come before any optional property-test dependency.
- **Verification:** `cargo test --locked`, `cargo build --locked`, selected cases above and `python -m unittest discover -s tests/harness -p 'test_*.py' -v`.
- **Exit gate:** new boundary tests and selected cases pass, receivers observe zero requests for rejected inputs, existing files survive, alias/numeric decisions are explicit.
- **Rust focus/pitfall:** serde visitors, checked conversions, maps and validated structs; parse once rather than repeat loose validation throughout the runner.
- **Suggested commit:** `feat(scenario): validate bounded plans before effects`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** a validated plan with stable delivery indices; valid nonempty execution can remain incomplete during these pending stages.

## Stage 3: pure reports, persistence and empty success

- **Objective:** an empty valid scenario produces the exact zero-delivery report, safely, without network traffic.
- **Depends on:** 2. **Suggested paths:** `src/report.rs` owns typed outcomes/summary/serialization; `src/output.rs` if needed owns persistence; private unit tests plus black-box filesystem tests.
- **Tasks:**
  - Model four outcomes explicitly with correct status/null invariants. Derive summary from indexed rows, restore plan order, and serialize only contract fields; test mixed outcomes before network integration.
  - Handle empty plans immediately after full validation. Do not construct a client/send requests unnecessarily. Exit 0 only after report persistence; write failure exits 2.
  - Serialize complete JSON, create an exclusive temporary sibling, flush/close appropriately and replace the destination using verified platform semantics. Clean up owned temporary files on error.
  - Test replacing an existing file on Windows/Linux. Delete-then-rename is not an atomic fallback and can destroy the previous report. If standard APIs are insufficient, choose a justified helper or resolve the contract before claiming support.
  - Distinguish atomic visibility from power-loss durability; decide what sync behavior is promised. Close handles before Windows replacement.
- **Existing cases:** `test_empty`, `test_report_write_failure`; empty golden pair.
- **Tests to add:** pure mixed-outcome/report-order/count tests; replacing an existing report; failure leaves old bytes intact; serialization/write/rename cleanup; relative/missing-parent paths; empty run with unreachable valid target.
- **Verification:** `cargo test --locked`, `cargo build --locked`, select `test_empty test_report_write_failure`.
- **Exit gate:** empty/report-failure and pure/persistence tests pass locally, old files survive failures; cross-platform proof remains required in stage 8.
- **Rust focus/pitfall:** algebraic data types, pure transformations, RAII; avoid contradictory optional flags or output mutation during validation.
- **Suggested commit:** `feat(report): persist canonical reports and complete empty runs`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** transport supplies outcomes, not report JSON or printing logic.

## Stage 4: one bounded HTTP attempt

- **Objective:** one real POST is classified as success, HTTP error, timeout or transport error.
- **Depends on:** 3. **Suggested paths:** `src/transport.rs` owns a reusable reqwest client/one attempt; runner/main orchestrates; report/error modules stay independent.
- **Tasks:** build one reusable client; disable redirects and explicitly disable retries. Reqwest 0.13.5 defaults to protocol-NACK retries and offers [retry::never](https://docs.rs/reqwest/0.13.5/reqwest/retry/fn.never.html); [ClientBuilder](https://docs.rs/reqwest/0.13.5/reqwest/struct.ClientBuilder.html#method.redirect) follows redirects by default (verified 2026-10-26; recheck on upgrades). Send the required header/JSON values; classify statuses directly so 3xx/4xx/5xx retain their status. Distinguish timeout through structured errors, not message text; start the deadline at dispatch, including connection work.
  - Resolve whether delivery completes at response headers or after body completion. The contract captures no body but leaves this boundary implicit; prefer headers/drop response, align the contract and test a stalled body. Do not accidentally drain an unbounded body.
  - Keep TLS certificate/hostname verification enabled. Sanitize external errors. A delivery failure still produces a complete report and exit 1; client-construction failure is a command failure, not a fabricated attempted delivery.
- **Existing cases:** `test_01_success`, `test_http_error`, `test_timeout`, `test_transport_error`, `test_redirect_is_not_followed`; four matching golden pairs plus derived 307 report.
- **Tests to add:** representative status classes, no retry where deterministically observable, stalled-body completion decision, TLS failures, secret-bearing URL/response diagnostics.
- **Verification:** `cargo test --locked`, `cargo build --locked`, select the five methods above.
- **Exit gate:** one-delivery outcomes/report/receiver observations pass, redirect sees one request, retry configuration is explicit.
- **Rust focus/pitfall:** async/await, enum/error classification and client reuse; avoid broad catches that erase failure distinctions.
- **Suggested commit:** `feat(transport): classify single webhook attempts`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** keep one attempt separate from scheduling/concurrency.

## Stage 5: complete sequential plans

- **Objective:** repeated/reordered references yield complete deterministic reports, including failures.
- **Depends on:** 4. **Suggested paths:** introduce `src/runner.rs` when orchestration exists; transport/report responsibilities remain stable; integration tests observe mixed outcomes.
- **Tasks:** iterate by index, preserve ID/payload on duplicate references, preserve sequential order, continue after ordinary delivery failures without retry, collect one result per planned delivery and persist once after completion. Do not clone the entire plan for each attempt without need.
- **Existing cases:** `test_duplicate`, `test_reorder`, `test_serial_concurrency_limit`. Their fixtures include timing offsets/ties; stage 6 closes schedule assertions. Do not claim timing completeness at this intermediate stage.
- **Tests to add:** mixed success/failure, all failures, first failure followed by success, exact ID/payload preservation and pure aggregate/order checks. Custom receiver behavior stays test-only.
- **Verification:** `cargo test --locked`, `cargo build --locked`, select duplicate/reorder/serial cases for completed functional behavior and explicitly track timing gaps.
- **Exit gate:** sequential functional/order/count checks and mixed-failure tests pass; failures exit 1 with every row; no fail-fast delivery loop.
- **Rust focus/pitfall:** indexed iteration, borrowing immutable data and distinguishing command failure from delivery outcome.
- **Suggested commit:** `feat(runner): execute sequential plans and aggregate failures`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** preserve original indices/offsets for scheduling.

## Stage 6: monotonic delayed dispatch

- **Objective:** dispatch no earlier than scheduled eligibility without cumulative drift.
- **Depends on:** 5. **Suggested paths:** runner; a timing module only if useful; pure deadline tests and receiver timing cases.
- **Tasks:** capture monotonic start after full validation; calculate absolute deadlines from that start; wait until eligibility rather than sleep each offset after prior work; dispatch overdue work without replaying elapsed delay; keep tied dispatch in list order. Request timeout excludes all scheduling/slot waiting.
- **Existing cases:** `test_delay`, `test_duplicate`, `test_reorder`, `test_serial_concurrency_limit`.
- **Tests to add:** overdue work after a slow request, tied offsets, no cumulative drift, timeout not starting at run start and maximum offset arithmetic. Prefer pure deadline tests and, if justified, Tokio test-only paused time; avoid exact stopwatch equality.
- **Verification:** `cargo test --locked`, `cargo build --locked`, select the four methods above; retain earlier tests.
- **Exit gate:** scheduled sequential cases and new deadline tests pass; no wall-clock dependency or exact arrival-time promise.
- **Rust focus/pitfall:** `Instant`, duration arithmetic and timer futures. Missed eligibility does not mean drop the delivery.
- **Suggested commit:** `feat(schedule): use monotonic delivery deadlines`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** concurrency adds slot waiting without changing the timeout origin.

## Stage 7: bounded concurrency and draining

- **Objective:** eligible deliveries overlap within the limit; reports retain original plan order.
- **Depends on:** 6. **Suggested paths:** runner owns tasks/permits; transport/report contracts stay unchanged; extend concurrency tests.
- **Tasks:** admit in plan order; wait for eligibility and a slot; start timeout only at actual dispatch; hold/release an owned slot on every outcome; await all owned work; restore results by index. Avoid detached tasks, unbounded in-flight requests and mutexes held during network awaits. Decide whether a bounded driver is simpler than one queued task per delivery.
  - Define tie **dispatch** order precisely. Merely spawning tasks in order may not establish their start order; test the dispatcher without promising concurrent wire-arrival order.
  - A task failure must not strand peers or create a misleading complete-success report. Drain/clean up owned work before command failure.
- **Existing cases:** `test_concurrent` proves overlap and bound 2; `test_serial_concurrency_limit` proves bound/order 1. Parallel receiver observations use multisets; reports use exact row order.
- **Tests to add:** limits 1/2/64, many ties, reverse completion with distinct IDs, queue wait longer than request timeout, timeout releasing a slot, peers continuing after failure, no report before draining.
- **Verification:** `cargo test --locked`, `cargo build --locked`, select concurrent/serial cases, then `python scripts/check.py runtime`.
- **Exit gate:** complete existing acceptance plus new queue/deadline/draining tests pass; concurrency stays bounded and reports deterministic.
- **Rust focus/pitfall:** shared client handles, immutable sharing, owned permits and joining tasks across await.
- **Suggested commit:** `feat(runner): bound concurrency and drain delivery tasks`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** readiness stays pending until gaps/platform checks below close.

## Stage 8: correctness gaps and platform behavior

- **Objective:** close known contract gaps before performance/readiness claims.
- **Depends on:** 7. **Suggested paths:** focused runtime fixes, private Rust tests, black-box tests/receiver extensions, contract/schema/testing docs for explicit clarifications.
- **Tasks:** finish the matrix below; verify input/existing-report preservation, alias policy, nested duplicate/value fidelity, mixed failures, queue/deadline edges and replacement/cleanup on Windows/Linux. Resolve all decision-ledger items. Add only justified test dependencies.
- **Tests to add:** exact bounds; existing-file replacement and induced failures; supported symlink/hard-link aliases; HTTPS valid/invalid certificate/hostname using controlled trust setup or a narrow internal transport test. Do not ship an insecure TLS option just to ease testing. State unverified trust/platform cases honestly. Avoid brittle permission tests that behave differently under administrator accounts.
- **Verification:** `python scripts/check.py infrastructure`, `python scripts/check.py runtime`, `python scripts/check.py audit`, `python scripts/check.py workflow` on Windows/Linux. The existing manual runtime workflow is Linux-only, so it cannot establish Windows runtime success.
- **Exit gate:** existing/added correctness checks pass on both platforms at a recorded revision, documentation aligns, no unresolved blocking decision remains. Unavailable platform evidence keeps this gate pending.
- **Rust focus/pitfall:** failure injection at real narrow boundaries, platform filesystem behavior and cleanup; never convert skipped checks into evidence of success.
- **Suggested commit:** `test(runtime): cover boundary and platform failure cases`. **Status:** pending. **Outcome:** unimplemented. **Handoff:** exact revision/platform/toolchain/commands/logs go to stage 9; flag remains pending.

## Stage 9: performance, hosted evidence and readiness

- **Objective:** establish measured usability, then make the readiness transition honestly.
- **Depends on:** 8. **Suggested paths:** evidence/docs; future narrow runtime-workflow matrix changes; `project-status.json` only after evidence; README/contract status prose when implemented.
- **Tasks:**
  - Run `python scripts/check.py performance`; inspect `.bench-results/performance.json`. Both `validated` and `budget_passed` must be true. The script validates exit/report/receiver counts/payloads/concurrency before reporting throughput.
  - Keep the explicit workload: release binary, 1,000 deliveries, concurrency 8, 256 padding bytes, 30-second configurable wall budget. Record machine/Python metadata, binary hash and revision. Startup/delivery/reporting and the Python receiver affect results; this establishes neither speedup nor memory-use improvement. Profile before optimizing, rerun correctness after changes, and compare equivalent hosts/workloads only.
  - Obtain hosted runtime **and** performance success on Windows/Linux while readiness remains pending. Extend the currently Linux-only manual workflow matrix in this future stage, or supply equivalent hosted evidence. Release workflow correctly rejects pending and cannot provide pre-transition evidence.
  - Only after local+hosted evidence, change status to implemented in a reviewed commit. Verify normal CI now actually runs runtime/performance and its CI gate passes. Update pending-status prose and record implementation outcomes.
  - Review release guard, version/tag matching, `origin/main` ancestry and package/checksum requirements. No release tag or release workflow is executed by this planning task.
- **Verification:** infrastructure/runtime/performance/audit/workflow commands above; after the supported transition, `python scripts/check.py release` repeats local checks without publishing. `scripts/prepare_release.py` and tag workflow are separate packaging/publication actions.
- **Exit gate:** both platforms have traceable correctness/performance evidence, readiness implemented, hosted runtime job actually green, status prose accurate and release gates intact.
- **Suggested commits:** `ci(runtime): validate both supported platforms`, then `chore(readiness): record verified runtime implementation` after evidence.
- **Status:** pending. **Outcome:** unimplemented. **Handoff:** a future maintainer decides when to create/review a release; implementation completion does not publish one.

## Coverage matrix: existing versus proposed

Nine golden pairs live at `tests/fixtures/<name>.scenario.json` and `<name>.report.json`. Existing method names below are exact; each executes the actual binary. Proposed coverage is work to add, not an existing test result.

| Existing acceptance method | Golden pair / current observation | Stage | Proposed additional coverage |
| --- | --- | --- | --- |
| `test_01_success` | `success`; POST/report/header/count | 4 | More 2xx, numeric payload fidelity |
| `test_empty` | `empty`; zero requests/report | 3 | Unreachable target, existing report |
| `test_duplicate` | `duplicate`; repeated ID/payload/order | 5-6 | Mixed outcomes across duplicates |
| `test_reorder` | `reorder`; paid before created | 5-6 | More events, tied offsets |
| `test_delay` | `delay`; approximate 200ms lower bound | 6 | Drift, overdue work, deadline calculations |
| `test_http_error` | `http_error`; 503/exit 1 | 4-5 | Mixed statuses without aborting peers |
| `test_timeout` | `timeout`; delayed receiver/bounded duration | 4, 7 | Queue deadline, body-completion policy |
| `test_transport_error` | `transport_error`; non-listening socket | 4 | TLS/DNS where deterministic, redaction |
| `test_concurrent` | `concurrent`; overlap/bound 2, exact report | 7 | Limit 64, reverse completion, task failures |
| `test_serial_concurrency_limit` | `concurrent` with limit 1; tied order | 5-7 | Timeout releases slot, blocked queue |
| `test_redirect_is_not_followed` | `success` input; derived 307 report, one request | 4 | Explicit no-retry behavior |
| `test_rejections_send_nothing` | Generated invalid versions/types/limits/IDs/JSON/UTF-8/outer duplicate key/missing path | 2 | All boundaries, nested duplicates, old report unchanged |
| `test_invalid_target_sends_nothing` | Five invalid target forms; no report/request | 2 | URL edges and caller-relative paths |
| `test_scenario_report_paths_must_differ` | Identical path; scenario preserved | 2 | Lexical aliases, symlinks/hard links |
| `test_report_write_failure` | Empty input; directory as output path | 3 | Atomic replacement/error/cleanup |

Add **Rust unit tests** for validated types, duplicate-aware decoding, outcome/status invariants, pure report order/counts and deadline decisions. Add **black-box tests** for preservation, aliases, HTTPS, mixed outcomes, slot/timeout behavior and platform persistence. Deterministic generated boundary/permutation checks can precede any property-testing crate. No new test is present merely because this plan names it.

Keep all 14 infrastructure self-tests and 5 automation guard tests. They protect fixture/oracle/receiver integrity, optimized-Python refusal, readiness parsing and release gating; they do not replace runtime acceptance. Performance is one explicit workload, not full correctness or production-capacity proof.

## Decision ledger and completion record

| Decision | Resolve in | Required evidence / current gap |
| --- | --- | --- |
| Help/version exit-0 exception | 1 | CLI tests and explicit contract alignment |
| Numeric/depth envelope; duplicate keys at every object | 2 | Supported-value fidelity, no silent overwrite/rounding |
| Same-file aliases and filesystem race scope | 2-3 | Windows/Linux identity tests and explicit limitations |
| Atomic visibility versus crash durability | 3, 8 | Replace-existing/failure/cleanup tests; no delete-then-rename claim |
| Completion at response headers versus body | 4 | Contract clarification and stalled-body test |
| Tie dispatch boundary versus concurrent arrival | 7 | Dispatcher test; parallel receiver multiset |
| Hosted Windows checks while pending | 9 | Future manual matrix/equivalent logs; current Linux-only job is insufficient |

For each stage, replace its pending outcome only after the exit gate is true: record commit, tests added versus existing cases run, commands/exits/platform, limitations and next responsibility. Do not mark a stage done because it compiles. If behavior changes require a contract decision, align contract/schema/tests rather than silently redefine the CLI in implementation. At completion preserve the evidence supporting readiness and keep the non-goals deferred.
