# Contributing

This repository supplies a development foundation and executable contracts. Application runtime implementation is intentionally pending and belongs to the project owner. Discuss implementation scope before submitting runtime code.

Read [the contract](docs/contract.md), [development setup](docs/development.md), and [testing guide](docs/testing.md). Use synthetic payloads and loopback receivers in tests. Keep dependency changes small; commit Cargo.lock and explain the dependency's purpose.

Before proposing a change, run the infrastructure, audit, and workflow checks in the development guide. Report commands, results, and unavailable checks in the pull request. Runtime validation must fail until behavior is implemented; never replace assertions with skips to obtain a green run. Update relevant documentation with behavior and configuration changes.

Only change project-status.json to `implemented` once the complete runtime contract and acceptance/performance suites pass on Windows and Linux. A readiness flag is a gate, not proof of correctness; CI reruns the suites when enabled.
