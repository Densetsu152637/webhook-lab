"""Opt-in local throughput workload, validated before any successful timing claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import tempfile
import time

from harness.support import Receiver, assert_observations, expected_success, load_report, resolve_binary, run_binary


def machine_metadata(binary: Path) -> dict:
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
        revision_value = revision.stdout.strip() if revision.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        revision_value = None
    return {"platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "python": platform.python_version(),
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "git_revision": revision_value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deliveries", type=int, default=1000)
    parser.add_argument("--max-seconds", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.deliveries <= 10000 or not 0 < args.max_seconds <= 3600:
        parser.error("deliveries must be 1..10000 and max-seconds must be >0 and <=3600")
    try:
        binary = resolve_binary(args.binary)
    except ValueError as exc:
        parser.error(str(exc))
    scenario = {"schema_version":1,"timeout_ms":5000,"concurrency":8,
                "events":[{"id":"benchmark","payload":{"type":"benchmark","padding":"x"*256}}],
                "deliveries":[{"event":"benchmark","at_ms":0} for _ in range(args.deliveries)]}
    result = {"schema_version":1, "recorded_at": datetime.now(timezone.utc).isoformat(),
              "machine":machine_metadata(binary),
              "workload":{"deliveries":args.deliveries,"concurrency":8,"payload_padding_bytes":256,
                          "receiver":"Python stdlib ThreadingHTTPServer on loopback", "build":"caller-selected binary"},
              "budget_seconds":args.max_seconds, "validated":False, "budget_passed":False,
              "elapsed_seconds":None, "deliveries_per_second":None, "error":None}
    try:
        with tempfile.TemporaryDirectory(prefix="webhook-lab-performance-") as directory, Receiver() as receiver:
            path, output = Path(directory)/"scenario.json", Path(directory)/"report.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            started = time.monotonic()
            completed = run_binary(binary, path, receiver.url, output, timeout=args.max_seconds + 10)
            elapsed = time.monotonic() - started
            result["elapsed_seconds"] = elapsed
            assert completed.returncode == 0, "runtime failed (exit 78 means implementation is pending)"
            load_report(output, expected_success(scenario))
            assert_observations(receiver.snapshot(), scenario, ordered=False)
            assert not receiver.errors, "receiver rejected runtime requests"
            assert receiver.max_active <= 8, "runtime exceeded workload concurrency"
            result["validated"] = True
            result["deliveries_per_second"] = args.deliveries / elapsed
            result["budget_passed"] = elapsed <= args.max_seconds
            if not result["budget_passed"]:
                result["error"] = "explicit wall-time budget exceeded"
    except (AssertionError, OSError, ValueError) as exc:
        result["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"validated":result["validated"],"budget_passed":result["budget_passed"],"error":result["error"]}))
    return 0 if result["validated"] and result["budget_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
