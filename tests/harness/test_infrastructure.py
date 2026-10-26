"""Infrastructure checks remain valid before and after the user implements Rust."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from support import (
    FIXTURES, ROOT, Observation, Receiver, assert_observations, assert_report,
    fixture, load_report, validate_scenario,
)


def post(url, payload, event_id="created", content_type="application/json"):
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": content_type, "X-Webhook-Lab-Event-Id": event_id}, method="POST")
    with urlopen(request, timeout=5) as response:
        return response.status


class FixtureTests(unittest.TestCase):
    def test_optimized_python_is_refused(self):
        command = [sys.executable, "-O", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import support", str(ROOT / "tests" / "harness")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires Python assertions", result.stderr)

    def test_all_golden_scenarios_and_reports_are_consistent(self):
        scenarios = sorted(FIXTURES.glob("*.scenario.json"))
        self.assertGreaterEqual(len(scenarios), 9)
        for path in scenarios:
            with self.subTest(path=path.name):
                name = path.name.removesuffix(".scenario.json")
                scenario, report = fixture(name,"scenario"), fixture(name,"report")
                validate_scenario(scenario)
                assert_report(report, report)
                self.assertEqual(len(scenario["deliveries"]), len(report["deliveries"]))
                for index, (delivery, row) in enumerate(zip(scenario["deliveries"], report["deliveries"])):
                    self.assertEqual((row["index"],row["event"],row["scheduled_at_ms"]), (index,delivery["event"],delivery["at_ms"]))
                self.assertLessEqual(path.stat().st_size, 1048576)

    def test_examples_are_valid(self):
        for path in (ROOT / "examples").glob("*.json"):
            validate_scenario(json.loads(path.read_text(encoding="utf-8")))

    def test_schema_shapes_track_fixture_fields(self):
        for name in ["scenario", "report"]:
            schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
            sample = fixture("success", name)
            self.assertEqual(set(schema["required"]), set(sample))
            self.assertEqual(set(schema["properties"]), set(sample))
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["properties"]["schema_version"], {"const":1})

    def test_scenario_mutations_are_rejected(self):
        mutations = [
            lambda value: value.update(concurrency=True),
            lambda value: value["events"][0].update(id="bad\nheader"),
            lambda value: value["events"][0].update(id="nonascii-\u00e9"),
            lambda value: value["events"][0].update(id="x"*129),
            lambda value: value.update(concurrency=65),
            lambda value: value.update(timeout_ms=0),
            lambda value: value.update(schema_version=2),
            lambda value: value.update(extra="unknown"),
            lambda value: value["deliveries"][0].update(event="absent"),
            lambda value: value["events"].append(deepcopy(value["events"][0])),
            lambda value: value.update(deliveries=[{"event":"created","at_ms":2},{"event":"created","at_ms":1}]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                value=fixture("success","scenario")
                mutate(value)
                with self.assertRaises(AssertionError):
                    validate_scenario(value)


class OracleMutationTests(unittest.TestCase):
    def test_report_mutations_fail(self):
        expected=fixture("success","report")
        mutations = [
            lambda value: value.update(schema_version=True),
            lambda value: value.update(extra="unexpected"),
            lambda value: value.update(deliveries=[]),
            lambda value: value["summary"].update(failed=1),
            lambda value: value["deliveries"][0].update(index=2),
            lambda value: value["deliveries"][0].update(event="wrong"),
            lambda value: value["deliveries"][0].update(http_status=503),
            lambda value: value["deliveries"][0].update(outcome="timeout",http_status=204),
            lambda value: value["deliveries"][0].update(http_status=True),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                actual=deepcopy(expected)
                mutate(actual)
                with self.assertRaises(AssertionError):
                    assert_report(actual, expected)

    def test_missing_and_malformed_reports_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/"report.json"
            with self.assertRaisesRegex(AssertionError,"did not create"):
                load_report(report,fixture("success","report"))
            report.write_text("{broken",encoding="utf-8")
            with self.assertRaisesRegex(AssertionError,"not valid"):
                load_report(report,fixture("success","report"))
            report.write_text("null",encoding="utf-8")
            with self.assertRaises(AssertionError):
                load_report(report,fixture("success","report"))

    def test_bad_receiver_observations_fail(self):
        scenario=fixture("success","scenario")
        valid=Observation("created",scenario["events"][0]["payload"],"application/json",0,"/hook")
        assert_observations([valid],scenario)
        cases=[[],[valid,valid],[replace(valid,event_id="wrong")],
               [replace(valid,payload={"wrong":True})],[replace(valid,content_type=None)],
               [replace(valid,path="/wrong")]]
        for observations in cases:
            with self.subTest(observations=observations):
                with self.assertRaises(AssertionError):
                    assert_observations(observations,scenario)

    def test_unordered_mode_preserves_duplicate_counts(self):
        scenario=fixture("duplicate","scenario")
        valid=Observation("created",scenario["events"][0]["payload"],"application/json",0,"/hook")
        assert_observations([valid,valid],scenario,ordered=False)
        with self.assertRaises(AssertionError):
            assert_observations([valid],scenario,ordered=False)


class ReceiverTests(unittest.TestCase):
    def test_receiver_records_real_http_request_and_stops(self):
        scenario=fixture("success","scenario")
        with Receiver() as receiver:
            self.assertEqual(post(receiver.url,scenario["events"][0]["payload"]),204)
            assert_observations(receiver.snapshot(),scenario)
            self.assertFalse(receiver.errors)
        self.assertFalse(receiver.thread.is_alive())
        self.assertEqual(receiver.server.fileno(),-1)

    def test_receiver_status_behavior(self):
        with Receiver(status=503) as receiver:
            with self.assertRaises(HTTPError) as raised:
                post(receiver.url,{"type":"test"})
            self.assertEqual(raised.exception.code,503)
            raised.exception.close()
            self.assertEqual(len(receiver.snapshot()),1)

    def test_receiver_gate_proves_overlap(self):
        with Receiver(gate_width=2) as receiver:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(post,receiver.url,{"type":"test"}) for _ in range(2)]
                self.assertEqual([future.result(timeout=5) for future in futures],[204,204])
            self.assertEqual(receiver.max_active,2)
            self.assertFalse(receiver.errors)

    def test_receiver_delay_is_real(self):
        with Receiver(delay=0.05) as receiver:
            started=time.monotonic()
            post(receiver.url,{"type":"test"})
            self.assertGreaterEqual(time.monotonic()-started,0.04)

    def test_receiver_malformed_payload_is_observable(self):
        import http.client
        with Receiver() as receiver:
            connection=http.client.HTTPConnection("127.0.0.1",receiver.server.server_port,timeout=3)
            try:
                connection.request("POST","/hook",body=b"not-json",headers={"Content-Type":"application/json"})
                with self.assertRaises(http.client.RemoteDisconnected):
                    connection.getresponse()
            finally:
                connection.close()
            self.assertEqual(receiver.snapshot(),[])
            self.assertEqual(receiver.errors,["JSONDecodeError"])


if __name__ == "__main__":
    unittest.main()
