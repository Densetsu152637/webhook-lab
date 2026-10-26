# Development

## Environment

Use the Rust version in rust-toolchain.toml (including rustfmt and Clippy), Python 3.13, Git, and a native compiler/linker. On Windows install Visual Studio Build Tools with the Desktop development with C++ workload and Windows SDK for the MSVC toolchain. Linux needs a C compiler/linker (for example the distribution's build-essential package); macOS needs Xcode command-line tools. No containers, databases, API credentials, or Python test packages are needed for the CLI harness.

Install Rust using [rustup](https://rustup.rs/) and Python using [python.org](https://www.python.org/downloads/). From the repository root:

```text
rustup show active-toolchain
python scripts/bootstrap.py
```

Bootstrap installs cargo-deny 0.20.2 and cargo-audit 0.22.2 with their published lockfiles, creates a repository-local .venv with pre-commit 4.7.0, and downloads actionlint 1.7.12 and gitleaks 8.30.1 to ignored .tools/. Downloaded archives must match the committed SHA256 manifest before their executable is extracted. Supported portable platforms are Windows, Linux, and macOS on amd64 and arm64. The bootstrap requires network access and a functioning compiler; it fails on unsupported platforms or mismatched checksums. `--binaries-only` installs only actionlint and gitleaks.

Install Git hooks using `.venv/Scripts/pre-commit.exe install` on Windows or `.venv/bin/pre-commit install` on Unix. Run the same executable with `run --all-files` for a full hook check. Hooks check formatting, readiness syntax, workflows, history, and staged secrets; full build/runtime checks remain explicit. Hooks never replace CI.

## Shared local and CI commands

```text
python scripts/check.py infrastructure
python scripts/check.py audit
python scripts/check.py workflow
python scripts/check.py status
python scripts/check.py runtime
python scripts/check.py performance
python scripts/check.py release
```

Infrastructure runs `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets -- -D warnings`, `cargo test --locked`, `cargo build --locked`, harness self-tests, and release-guard tests. It always runs for PRs and main, including documentation changes. Audit runs cargo-deny (advisories, licenses, sources, bans) and cargo-audit with warnings denied. Workflow runs actionlint and gitleaks on Git history and staged files; actionlint's optional shellcheck/pyflakes integrations are disabled for identical checks across platforms.

Runtime builds the debug binary and runs acceptance. Performance builds release outside the timed workload, then runs 1,000 deliveries with a 30-second threshold and writes .bench-results/performance.json. Runtime and performance fail against the placeholder by design. See [testing](testing.md) for the behavior and performance contracts.

`project-status.json` accepts exactly one key, `runtime`, with `pending` or `implemented`. CI validates it, visibly reports pending application behavior, and runs runtime/performance automatically once implemented. The manual runtime workflow always runs real runtime checks regardless of that flag. Required check **CI gate** succeeds only if infrastructure/auditing/readiness pass and the runtime result agrees with status. Pending runtime is never reported as validated.

## Release candidates

The Release candidate workflow runs manually or for `v*` tags. It immediately rejects pending status before installing tooling, then checks infrastructure, supply chain, workflows, acceptance, and performance on Linux and Windows. Only successful jobs upload the validated executable and SHA256SUMS as 14-day Actions artifacts. It does not publish GitHub Releases, packages, or deployments; a maintainer reviews artifacts and evidence before any future publication. Partial matrix success is not a release approval. The CLI needs no hosted deployment service.

## Maintaining tools and workflows

Dependabot proposes weekly Cargo and action updates. Review changed upstream releases, lockfile diffs, license changes, and advisories; never auto-merge solely because a scanner is green. Actions use complete upstream commit SHAs with version comments. Resolve annotated tags to their commit object. For portable tool updates, review official release assets/checksums, update scripts/tool-versions.json and documented versions together, rerun bootstrap and static checks, and review binaries' `--version` output. Cargo auditors and pre-commit versions appear in bootstrap and CI: update all copies together.

Primary release sources: [actionlint](https://github.com/rhysd/actionlint/releases/tag/v1.7.12), [gitleaks](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1), [cargo-deny](https://github.com/EmbarkStudios/cargo-deny/releases/tag/0.20.2), [cargo-audit](https://github.com/rustsec/rustsec/releases/tag/cargo-audit/v0.22.2), and [pre-commit](https://github.com/pre-commit/pre-commit/releases/tag/v4.7.0). Portable SHA256 values were checked against those official release checksum files on 2026-10-26. Checksums detect changed downloads; they do not replace review of publisher provenance.

For local Linux workflow rehearsal with Docker running: `act pull_request -W .github/workflows/ci.yml -j workflow`. Other jobs need a Rust-capable runner image and setup time. Hosted Windows jobs, token restrictions, concurrency, cancellation, artifact permissions, and schedules require GitHub verification: act does not reproduce these controls.
