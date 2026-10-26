"""Execute the actual binary's public contract. Fails until runtime is implemented."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest

from harness.support import (
    FIXTURES, Receiver, assert_observations, fixture, load_report,
    resolve_binary, run_binary, unavailable_target,
)

BINARY: Path


class RuntimeAcceptance(unittest.TestCase):
    def run_golden(self, name, *, status=204, delay=0, gate_width=0):
        scenario = fixture(name, "scenario")
        with tempfile.TemporaryDirectory(prefix="webhook-lab-acceptance-") as directory:
            output = Path(directory) / "report.json"
            with Receiver(status=status, delay=delay, gate_width=gate_width) as receiver:
                started = time.monotonic()
                result = run_binary(BINARY, FIXTURES / f"{name}.scenario.json", receiver.url, output)
                elapsed = time.monotonic() - started
                expected = fixture(name, "report")
                wanted_exit = 1 if expected["summary"]["failed"] else 0
                self.assertEqual(result.returncode, wanted_exit, "unexpected exit; runtime may still be the exit-78 placeholder")
                load_report(output, expected)
                observations = receiver.snapshot()
                assert_observations(observations, scenario, ordered=scenario["concurrency"] == 1)
                self.assertFalse(receiver.errors, "test receiver could not parse runtime output")
                self.assertLessEqual(receiver.max_active, scenario["concurrency"])
                if gate_width:
                    self.assertGreaterEqual(receiver.max_active, gate_width, "configured concurrency did not overlap")
                if name == "delay":
                    self.assertGreaterEqual(observations[0].arrived_at - started, 0.19, "request arrived before its 200ms schedule")
                    self.assertLess(elapsed, 5, "small scenario stalled")
                if name == "timeout":
                    self.assertLess(elapsed, 2, "timeout did not bound request duration")

    def test_01_success(self):
        self.run_golden("success")

    def test_empty(self):
        self.run_golden("empty")

    def test_duplicate(self):
        self.run_golden("duplicate")

    def test_reorder(self):
        self.run_golden("reorder")

    def test_delay(self):
        self.run_golden("delay")

    def test_http_error(self):
        self.run_golden("http_error", status=503)

    def test_timeout(self):
        self.run_golden("timeout", delay=0.6)

    def test_concurrent(self):
        self.run_golden("concurrent", gate_width=2)

    def test_serial_concurrency_limit(self):
        # Four requests at the same offset; a delayed receiver exposes accidental overlap.
        scenario = fixture("concurrent", "scenario")
        scenario["concurrency"] = 1
        with tempfile.TemporaryDirectory() as directory, Receiver(delay=0.05) as receiver:
            path, output = Path(directory) / "scenario.json", Path(directory) / "report.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            result = run_binary(BINARY, path, receiver.url, output)
            self.assertEqual(result.returncode, 0)
            load_report(output, fixture("concurrent", "report"))
            assert_observations(receiver.snapshot(), scenario)
            self.assertEqual(receiver.max_active, 1)
            self.assertFalse(receiver.errors)

    def test_transport_error(self):
        with tempfile.TemporaryDirectory() as directory, unavailable_target() as target:
            output = Path(directory) / "report.json"
            result = run_binary(BINARY, FIXTURES / "transport_error.scenario.json", target, output)
            self.assertEqual(result.returncode, 1)
            load_report(output, fixture("transport_error", "report"))

    def test_redirect_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory, Receiver(status=307) as receiver:
            output = Path(directory) / "report.json"
            result = run_binary(BINARY, FIXTURES / "success.scenario.json", receiver.url, output)
            self.assertEqual(result.returncode, 1)
            expected = fixture("http_error", "report")
            expected["deliveries"][0]["http_status"] = 307
            load_report(output, expected)
            self.assertEqual(len(receiver.snapshot()), 1, "redirect was followed")

    def test_rejections_send_nothing(self):
        base = fixture("success", "scenario")
        cases = []
        def changed(name, mutate):
            value = deepcopy(base)
            mutate(value)
            cases.append((name, json.dumps(value)))
        changed("version", lambda value: value.update(schema_version=2))
        changed("unknown", lambda value: value.update(secret="DO_NOT_ECHO_PAYLOAD"))
        changed("zero_timeout", lambda value: value.update(timeout_ms=0))
        changed("boolean_integer", lambda value: value.update(concurrency=True))
        changed("zero_concurrency", lambda value: value.update(concurrency=0))
        changed("large_concurrency", lambda value: value.update(concurrency=65))
        changed("unknown_event", lambda value: value["deliveries"][0].update(event="missing"))
        changed("duplicate_id", lambda value: value["events"].append(deepcopy(value["events"][0])))
        changed("negative_offset", lambda value: value["deliveries"][0].update(at_ms=-1))
        changed("too_late", lambda value: value["deliveries"][0].update(at_ms=60001))
        changed("decreasing", lambda value: value.update(deliveries=[{"event":"created","at_ms":2},{"event":"created","at_ms":1}]))
        changed("too_many", lambda value: value.update(deliveries=[{"event":"created","at_ms":0}]*10001))
        changed("missing_field", lambda value: value.pop("events"))
        changed("newline_id", lambda value: value["events"][0].update(id="bad\nheader"))
        changed("nonascii_id", lambda value: value["events"][0].update(id="nonascii-\u00e9"))
        changed("long_id", lambda value: value["events"][0].update(id="x"*129))
        changed("invalid_payload", lambda value: value["events"][0].update(payload="DO_NOT_ECHO_PAYLOAD"))
        cases.append(("duplicate_json_key", '{"schema_version":2,"schema_version":1,"timeout_ms":1000,"concurrency":1,"events":[],"deliveries":[]}'))
        cases.extend([("malformed", '{"secret":"DO_NOT_ECHO_PAYLOAD",'), ("oversize", " " * (1048576 + 1)), ("invalid_utf8", b"\xff")])
        with tempfile.TemporaryDirectory() as directory, Receiver() as receiver:
            for name, content in cases:
                with self.subTest(name=name):
                    path, output = Path(directory) / f"{name}.json", Path(directory) / f"{name}.report.json"
                    path.write_bytes(content if isinstance(content, bytes) else content.encode())
                    result = run_binary(BINARY, path, receiver.url, output)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(output.exists(), "invalid input created a report")
                    self.assertTrue(result.stderr.strip(), "invalid input needs a useful diagnostic")
                    self.assertNotIn("DO_NOT_ECHO_PAYLOAD", result.stdout + result.stderr)
                    self.assertEqual(receiver.snapshot(), [], "input was not fully validated before sending")
            missing = Path(directory) / "DO_NOT_ECHO_PRIVATE_PATH.json"
            output = Path(directory) / "missing.report.json"
            result = run_binary(BINARY, missing, receiver.url, output)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(missing), result.stdout + result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(receiver.snapshot(), [])

    def test_invalid_target_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory, Receiver() as receiver:
            for target in ["not-a-url", "ftp://127.0.0.1/file", "http://", "http://user:DO_NOT_ECHO_URL@127.0.0.1/hook", receiver.url + "#fragment"]:
                with self.subTest(target=target):
                    output = Path(directory) / "report.json"
                    result = run_binary(BINARY, FIXTURES / "success.scenario.json", target, output)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(output.exists())
                    self.assertNotIn("DO_NOT_ECHO_URL", result.stdout + result.stderr)
                    self.assertEqual(receiver.snapshot(), [])

    def test_scenario_report_paths_must_differ(self):
        with tempfile.TemporaryDirectory() as directory, Receiver() as receiver:
            path = Path(directory) / "scenario.json"
            original = json.dumps(fixture("success", "scenario"))
            path.write_text(original, encoding="utf-8")
            result = run_binary(BINARY, path, receiver.url, path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(receiver.snapshot(), [])

    def test_report_write_failure(self):
        # Directory as report path is an OS-independent write failure.
        with tempfile.TemporaryDirectory(prefix="webhook-lab-private-") as directory, Receiver() as receiver:
            output = Path(directory)
            result = run_binary(BINARY, FIXTURES / "empty.scenario.json", receiver.url, output)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr.strip())
            self.assertNotIn(str(output), result.stdout + result.stderr)
            self.assertEqual(receiver.snapshot(), [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    args = parser.parse_args()
    global BINARY
    try:
        BINARY = resolve_binary(args.binary)
    except ValueError as exc:
        parser.error(str(exc))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeAcceptance)
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
