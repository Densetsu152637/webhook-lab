# Testing the foundation and future runtime

The harness refuses optimized Python (`-O` / nonzero `PYTHONOPTIMIZE`) because assertions are acceptance gates. A subprocess self-test verifies this refusal.

The Python harness uses only the standard library (Python 3.11+). It launches the actual executable as a subprocess and observes HTTP traffic; it does not depend on Rust modules or implement the Rust application in Python.

## Infrastructure checks: expected green now

```text
cargo build --locked
cargo fmt --all -- --check
cargo clippy --locked --all-targets --all-features -- -D warnings
python -m unittest discover -s tests/harness -p 'test_*.py' -v
```

The infrastructure suite validates golden fixture semantics, example/schema field alignment, real receiver requests and cleanup, deliberate report mutations, missing/malformed reports, and incorrect receiver observations. The schema check is deliberately a stdlib structural consistency check, not a complete JSON Schema evaluator. Full semantic checks live in test-only fixture validation. These tests remain applicable after runtime implementation; they never require `src/main.rs` to remain a placeholder.

## Runtime acceptance: expected red until implemented

```text
python tests/acceptance.py --binary target/debug/webhook-lab
```

Windows also accepts `target/debug/webhook-lab.exe`; the harness resolves the suffix. Acceptance fail-fast executes the actual binary. The exit-78 scaffold therefore fails at the first success fixture, without masking pending behavior as a skip or expected pass. The command is intended to become completely green after the user implements the contract. No project-status file can make it pass.

Cases cover full expected reports and receiver observations for successful, empty, duplicate, reordered, delayed, HTTP-error, timeout, transport-error, and concurrent delivery; serialization with concurrency 1; disabled redirects; invalid input and targets before network effects; and report-write failure. Subprocesses have hard timeouts. Receivers use ephemeral loopback ports, bounded handler I/O, closed sockets, and joined threads. Transport-error tests hold a bound non-listening port to reduce free-port races. Timing checks use monotonic clocks and generous bounds; concurrent cases compare delivery multisets and maximum overlap, not nondeterministic arrival order.

Tests are a bounded acceptance suite, not proof of every specification detail. Additional runtime tests should cover atomic replacement, HTTPS behavior, and platform-specific filesystem errors as implementation progresses. The harness does not verify cancellation or global resource behavior.

## Performance: explicit opt-in, expected red now

```text
cargo build --release --locked
python tests/performance.py --binary target/release/webhook-lab --output .bench-results/performance.json --deliveries 1000 --max-seconds 30
```

The workload uses one synthetic 256-byte padding field, 1,000 deliveries at offset zero, concurrency 8, and a Python threaded HTTP receiver on loopback. The broad 30-second wall-time budget is configurable, not a historical baseline or Rust performance claim. It includes binary startup, delivery and report writing, excludes fixture preparation and receiver teardown, and is sensitive to the test receiver and host.

A machine-readable artifact records host/Python metadata, binary SHA-256, available Git revision, workload, budget, and outcome. Delivery exit code, complete report, exact receiver delivery multiset and payloads, and concurrency bound must pass before throughput is populated. Failed runs still write metadata with `validated: false`; a fast exit-78 process cannot pass. Missing binary or invalid benchmark options are command setup errors and do not produce a benchmark artifact. No peak-memory measurement or speedup is claimed.

Benchmark output belongs in ignored `.bench-results/`; do not commit host-specific results. Do not compare runs with different workloads, machines, build profiles, or receiver implementations as equivalent. Run correctness acceptance before interpreting performance results.
