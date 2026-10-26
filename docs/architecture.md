# Architecture decision: a deterministic black-box boundary

Status: accepted design; application runtime not implemented. The only Rust source is a clear exit-78 placeholder. Proposed responsibilities below are descriptive; no internal public API is frozen.

## Decision and boundaries

The CLI reads a strict versioned scenario, validates the complete plan, dispatches explicit event references to one target, then writes a canonical report. Types should represent validated configuration, event identity/payload, delivery plan, and outcome separately. Domain decisions should not depend on HTTP clients or filesystem APIs. Keep orchestration, scheduling, transport, and report persistence cohesive; introduce modules when their responsibility exists, not empty interfaces for every concept.

A future CLI boundary owns arguments and stable exit behavior. A scenario boundary converts raw JSON into a validated plan. A runner owns the monotonic clock, concurrency slots and task completion. An HTTP boundary classifies one attempt without retries/redirects. A report boundary restores plan order, derives counts and persists complete output. Resource ownership stays explicit: the runner awaits its work, requests release slots on completion/timeout, and the top-level command owns errors and final exit status.

The Python harness is separate test infrastructure: it starts local receiver fixtures, invokes the Rust binary, and checks externally observable outputs. It never substitutes for the application's scheduler, CLI parser, or HTTP sender. It has no dependence on application types or a project-status flag.

## Alternatives and tradeoffs

- Explicit repeated/reordered delivery references were selected over randomized fault rules. They are easy to reproduce and avoid seed/algorithm compatibility obligations. Revisit only when stochastic exploration is useful.
- Canonical reports omit timing and raw diagnostics. This supports exact stable fixtures; timing is checked independently with tolerances. Add versioned optional telemetry only when needed.
- A local CLI and stdlib receiver were selected over a hosted service/dashboard and a Python dependency stack. This keeps the learning project installable and the testing surface small.
- Locked intended dependencies prepare common Rust concerns without writing runtime logic for the learner. The cost is a larger dependency graph while the source is still a placeholder.

## Validation and staged delivery

Milestones and ownership are in `docs/implementation.md`; executable commands and known coverage limits are in `docs/testing.md`. Infrastructure green means the scaffolding and harness checks pass. Runtime acceptance must remain visibly red until implemented; a release gate must execute actual runtime acceptance and refuse pending status. Performance output is projected evidence only after actual successful deliveries are verified. CI/release owners maintain automation outside this foundation's owned paths.
