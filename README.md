# webhook-lab

A Rust learning project for testing how webhook consumers handle duplicate, delayed, reordered, and concurrent events.

**Status: development foundation. The application runtime is not implemented.** The current binary prints a not-implemented diagnostic and exits with code 78. Infrastructure checks can pass independently; runtime acceptance and performance tests are executable specifications and will fail until the application is implemented.

## The problem

A successful HTTP response alone does not prove an integration is correct. Consumers also need to handle events delivered twice, delivered late, or delivered out of order. webhook-lab is intended to replay explicit delivery scenarios against a local test endpoint and write a deterministic report.

## What is ready

- A pinned Rust toolchain, dependency lockfile, formatter and Clippy checks.
- A versioned CLI, scenario and report contract, with examples and expected reports.
- An independent Python test harness with a local HTTP receiver, behavioural acceptance cases and a performance workload.
- CI, dependency/license audits, workflow and secret scanning, dependency-update configuration, and guarded release automation.
- A staged implementation guide so the Rust runtime remains your work.

These are development assets, not claims that webhook delivery is implemented or benchmarked.

## Start here

1. Follow [development setup](docs/development.md).
2. Read the [v1 contract](docs/contract.md) and [architecture decisions](docs/architecture.md).
3. Implement the milestones in [the implementation guide](docs/implementation.md), beginning in `src/main.rs`.
4. Run the [test suites](docs/testing.md) as each milestone is completed.
5. Mark the runtime implemented only after the full acceptance suite passes; the release gate also verifies it.

The planned command interface is:

```text
webhook-lab run --scenario examples/duplicate.json --target http://127.0.0.1:8080/hook --report report.json
```

This command is a specification for the future runtime. The current placeholder does not parse arguments or send requests. See the examples directory for the exact fixture filenames.

## Scope of v1

One CLI, one HTTP(S) destination, explicit JSON events and delivery offsets, a concurrency limit, request timeouts, and deterministic JSON reports. Automatic retries, a hosted service, provider-specific signatures, a dashboard, and random scenario generation are outside the first implementation.

## Verification and contributions

See [testing](docs/testing.md), [contributing](CONTRIBUTING.md), and [security](SECURITY.md). Use synthetic payloads and endpoints you control. The test receiver exists only in the harness and is not application runtime code.

## License

[MIT](LICENSE).
