"""Shared local and CI checks. Every subprocess failure is a failure."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def runtime_status(path=ROOT / "project-status.json"):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"runtime"} or value["runtime"] not in ("pending", "implemented"):
        raise ValueError("project-status.json must contain only runtime: pending|implemented")
    return value["runtime"]


def require_implemented(path=ROOT / "project-status.json"):
    if runtime_status(path) != "implemented":
        raise ValueError("Runtime implementation is pending; release is blocked.")


def run(*command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True, timeout=1800)


def binary(profile):
    return ROOT / "target" / profile / ("webhook-lab.exe" if os.name == "nt" else "webhook-lab")


def infrastructure():
    runtime_status()
    run("cargo", "fmt", "--all", "--", "--check")
    run("cargo", "clippy", "--locked", "--all-targets", "--", "-D", "warnings")
    run("cargo", "test", "--locked")
    run("cargo", "build", "--locked")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests/harness", "-p", "test_*.py", "-v")
    run(sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-v")


def audit():
    run("cargo", "deny", "--locked", "check")
    run("cargo", "audit", "--deny", "warnings")


def workflow():
    # Gitleaks may return success after a Git discovery error: fail before scanning.
    run("git", "rev-parse", "--show-toplevel")
    run("git", "log", "-1", "--format=%H")
    suffix = ".exe" if os.name == "nt" else ""
    run(ROOT / ".tools" / ("actionlint" + suffix), "-shellcheck=", "-pyflakes=")
    run(ROOT / ".tools" / ("gitleaks" + suffix), "git", "--redact", "--no-banner", "--log-opts=--all")
    run(ROOT / ".tools" / ("gitleaks" + suffix), "git", "--redact", "--no-banner", "--staged")


def runtime():
    run("cargo", "build", "--locked")
    run(sys.executable, "tests/acceptance.py", "--binary", binary("debug"))


def performance():
    run("cargo", "build", "--locked", "--release")
    run(sys.executable, "tests/performance.py", "--binary", binary("release"), "--output", ".bench-results/performance.json", "--deliveries", "1000", "--max-seconds", "30")


def release():
    require_implemented()
    infrastructure()
    audit()
    workflow()
    runtime()
    performance()


def status():
    print(runtime_status())


def main():
    commands = {item.__name__: item for item in (infrastructure, audit, workflow, runtime, performance, release, status)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=commands)
    args = parser.parse_args()
    try:
        commands[args.check]()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
