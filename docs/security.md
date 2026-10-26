# Security controls and scope

## Assets and boundaries

Future webhook payloads, target URLs, signing keys, and reports may be sensitive. CLI arguments/scenario files cross the local input boundary; outbound HTTP crosses a network boundary; report paths cross the filesystem boundary. The future runtime must validate inputs, enforce time/body/concurrency bounds, avoid leaking secrets into reports/logs, and avoid surprising redirects or ambient proxy behavior as required by the contract. These are implementation requirements; the placeholder provides no runtime protection or network behavior.

Only send requests to authorized endpoints. The harness uses loopback HTTP and synthetic fixtures. Do not add real credentials, customer data, or externally addressed traffic to fixtures. Keep local credentials in ignored files; environment placeholders alone do not confer secure storage.

## Automated controls

- cargo-deny checks the locked graph for RustSec advisories, yanked crates, license policy, wildcard dependencies, and unknown sources. Duplicate crate versions warn because ecosystem graphs may legitimately contain them; investigate changes during review.
- cargo-audit independently checks Cargo.lock with warnings denied. Both auditors refresh advisory data over the network; a pinned scanner does not freeze the vulnerability database.
- Gitleaks scans all available Git history and staged changes with redacted output. It is heuristic and cannot prove absence of secrets; untracked files are not staged changes. CI checks out full history. Revoke exposed credentials immediately and follow incident response even after deleting a file.
- actionlint checks workflow syntax/expressions. Actions are pinned to full commit SHAs. Untrusted pull requests receive read-only repository permissions, no stored checkout credentials, and no deployment secrets; no pull_request_target workflow is used.
- CodeQL scans Rust, Python harness/tooling, and GitHub Actions on trusted main pushes and weekly schedules. Only its scan job has security-events write permission. PR workflows do not execute project code with a write token. [Rust support is generally available](https://github.blog/changelog/2025-10-14-codeql-scanning-rust-and-c-c-without-builds-is-now-generally-available/); [build mode none supports Rust](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options). Configure advanced setup rather than simultaneously enabling default CodeQL setup.
- Dependabot proposes weekly dependency and action updates. Scheduled auditing catches newly published advisories even when source code is unchanged.
- Release candidates require implemented status and all executable behavior/performance checks before artifacts are uploaded. Candidate jobs have read-only contents access. Only a separate tag-only publication job has contents-write access, executes no checked-out project code, and creates a draft after all platforms pass. Tags must match the package version and be reachable from main; maintainer review precedes public release.

## Triage and exceptions

Scanner findings need review of the affected version, prerequisites, reachability, and published advisory. Do not silence findings globally or lower severity merely to pass CI. Prefer upgrading or removing the dependency. Any necessary bounded exception must document advisory/license identity, why it applies, owner, expiry/review date, mitigation, and verification; keep the exception as narrow as the tool permits. deny.toml starts with no advisory exceptions.

The license allowlist describes policy, not legal advice. A dependency update outside it requires deliberate review. A clean audit covers the scanned graph and available database at that time; CodeQL, secret scanning, and test passes are complementary checks with coverage limits. Runtime security remains unverified until the application exists and receives review.

## Repository maintenance

Enable private vulnerability reporting, Dependabot alerts/security updates, and secret scanning/push protection where available. Protect main with pull-request review and **CI gate**, requiring branches to be current. Restrict Actions to reviewed providers and immutable pins. Recheck fork token restrictions and permissions in hosted runs. Repository settings are separate from committed workflow configuration and need owner verification.

See [SECURITY.md](../SECURITY.md) for private reporting.
