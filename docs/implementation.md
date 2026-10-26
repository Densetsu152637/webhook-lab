# User-owned implementation milestones

The repository currently supplies a locked Rust package, an exit-78 placeholder, fixtures, test infrastructure, and automation. **All application runtime work is yours.** The dependency list prepares the intended implementation; its successful build does not mean the runtime exists.

1. Implement the public CLI and fully validate scenario/target/report configuration before network I/O. Start with the empty scenario and invalid-input cases. Preserve the contract's byte, count, type, reference, and URL limits.
2. Implement one sequential POST with redirects disabled and a bounded request timeout; produce canonical outcome/report types. Use `reqwest` with Rustls; preserve event IDs and decoded JSON payload values.
3. Add complete-run reporting, failure exits, safe report replacement, duplicate and reordered plans. Compare public output to the golden fixtures.
4. Add monotonic scheduled eligibility and bounded concurrency. Separate a request's dispatch timeout from schedule/slot waiting. Keep reports in plan order. Use the receiver overlap/delay tests to validate actual behavior.
5. Run complete acceptance, then benchmark a release build. Only after both are green update the runtime status and enable release through the documented guard. Extend tests for specification details not yet directly exercised.

Use `docs/contract.md` as the external boundary and `docs/architecture.md` for responsibilities, not as a mandate for a complex internal framework. Avoid implementing retries, a database, public hosting, a GUI, plugin APIs, or provider-specific signing before v1 is complete.

The scaffold's unused intended runtime dependencies are deliberate: clap (CLI), serde/serde_json (data contracts), tokio (timers/tasks/semaphore), reqwest/Rustls (HTTP), thiserror (domain errors). No tracing dependency is included until a concrete diagnostic need exists. Do not treat infrastructure-green checks as runtime acceptance.
