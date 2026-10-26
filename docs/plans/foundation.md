# Plan: webhook-lab development foundation

Revision: 2026-10-26

## Outcome and scope
Create a public MIT-licensed Rust learning project with a verified Windows environment, CI/CD, dependency auditing, and executable acceptance/performance contracts. The user owns all application runtime implementation. Only a clearly nonfunctional entry-point placeholder is permitted in src/.

## Acceptance goals
- Public GitHub repository Densetsu152637/webhook-lab exists and main matches the validated local commit (gh repo view; git ls-remote).
- Pinned Rust toolchain, dependencies and lockfile build locally (cargo build --locked; cargo fmt; cargo clippy).
- Test infrastructure validates its fixtures and receiver; runtime expected-output, behaviour and performance suites are runnable and explicitly pending implementation (documented test commands).
- Hosted infrastructure CI and auditing pass; release automation refuses an unfinished runtime (GitHub checks and local guard tests).
- README, contract, development and security guidance accurately describe the scaffold and the user's implementation milestones.

## Stage 1: contract and foundation
- Depends on: none.
- Owner: root integrating architect guidance.
- Status: in progress.
- Deliverables: CLI/scenario/report contract and isolated worktrees.

## Stage 2: package and acceptance harness
- Depends on: stage 1.
- Owner: foundation worker.
- Paths: Cargo.toml, Cargo.lock, rust-toolchain.toml, src/, tests/, docs/contract.md, docs/testing.md, docs/implementation.md, schemas/, examples/.
- Status: pending.
- Checks: locked build, formatter, lint, harness self-tests and explicit expected failure of runtime acceptance.

## Stage 3: automation and auditing
- Depends on: stage 1 contract; integrate stage 2 before final validation.
- Owner: automation worker.
- Paths: .github/, scripts/, deny.toml, .pre-commit-config.yaml, SECURITY.md, CONTRIBUTING.md, development documentation.
- Status: pending.
- Checks: actionlint; local project scripts; supply-chain audits; release guard; supported act rehearsal and hosted workflows.

## Stage 4: integration and publication
- Depends on: stages 2 and 3.
- Owner: root.
- Status: pending.
- Checks: combined checks; scoped review; public repository settings; push; hosted results; clean checkout and worktree retirement.

## Worktree records
Foundation and automation worktrees will be rooted at D:/Git-Worktrees/webhook-lab/ with separate task branches from the initial committed base. Root owns creation, integration and cleanup. No worker may write application implementation or publish independently.
