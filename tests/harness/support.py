"""Test infrastructure only: receiver lifecycle and black-box contract assertions."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import subprocess
import threading
import time
from typing import Iterator

if not __debug__:
    raise RuntimeError("webhook-lab test harness requires Python assertions; remove -O/PYTHONOPTIMIZE")


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class Observation:
    event_id: str | None
    payload: object
    content_type: str | None
    arrived_at: float
    path: str


class Receiver:
    """A bounded local test receiver; never forwards or implements CLI behavior."""

    def __init__(self, status: int = 204, delay: float = 0, gate_width: int = 0):
        self.status = status
        self.delay = delay
        self.gate_width = gate_width
        self.observations: list[Observation] = []
        self.errors: list[str] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.gate = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def do_POST(self):
                active = False
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= length <= 1048576:
                        raise ValueError("invalid test request size")
                    body = self.rfile.read(length)
                    payload = json.loads(body)
                    observation = Observation(
                        self.headers.get("X-Webhook-Lab-Event-Id"), payload,
                        self.headers.get("Content-Type"), time.monotonic(), self.path,
                    )
                    with owner.lock:
                        owner.observations.append(observation)
                        owner.active += 1
                        active = True
                        owner.max_active = max(owner.max_active, owner.active)
                        if owner.max_active >= owner.gate_width:
                            owner.gate.set()
                    if owner.gate_width:
                        owner.gate.wait(timeout=2)
                    if owner.delay:
                        time.sleep(owner.delay)
                    # The response can reach the client before this handler's finally
                    # executes. End server-side work before publishing completion.
                    with owner.lock:
                        owner.active -= 1
                        active = False
                    self.send_response(owner.status)
                    if 300 <= owner.status < 400:
                        self.send_header("Location", "/redirected")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Expected when a timed-out test client disconnects.
                except (OSError, ValueError) as exc:
                    with owner.lock:
                        owner.errors.append(type(exc).__name__)
                finally:
                    if active:
                        with owner.lock:
                            owner.active -= 1

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = False
        self.server.block_on_close = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02})

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/hook"

    def __enter__(self) -> Receiver:
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("test receiver did not stop")

    def snapshot(self) -> list[Observation]:
        with self.lock:
            return list(self.observations)


@contextmanager
def unavailable_target() -> Iterator[str]:
    """Reserve a bound, non-listening socket to avoid a free-port race."""
    import socket
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        yield f"http://127.0.0.1:{reserved.getsockname()[1]}/hook"


def fixture(name: str, kind: str) -> dict:
    return json.loads((FIXTURES / f"{name}.{kind}.json").read_text(encoding="utf-8"))


def exact_keys(value: object, keys: set[str]) -> None:
    assert isinstance(value, dict), "expected an object"
    assert set(value) == keys, f"unexpected object keys: {set(value) ^ keys}"


def integer(value: object, low: int, high: int) -> None:
    assert type(value) is int and low <= value <= high, "integer outside contract bounds"


def validate_scenario(value: dict) -> None:
    """Validate checked-in test inputs, including constraints beyond JSON Schema."""
    exact_keys(value, {"schema_version", "timeout_ms", "concurrency", "events", "deliveries"})
    integer(value["schema_version"], 1, 1)
    integer(value["timeout_ms"], 1, 60000)
    integer(value["concurrency"], 1, 64)
    assert isinstance(value["events"], list) and len(value["events"]) <= 10000
    assert isinstance(value["deliveries"], list) and len(value["deliveries"]) <= 10000
    ids = set()
    for event in value["events"]:
        exact_keys(event, {"id", "payload"})
        assert isinstance(event["id"], str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", event["id"]), "unsafe event ID"
        assert event["id"] not in ids, "duplicate event ID"
        ids.add(event["id"])
        assert isinstance(event["payload"], dict)
    last_offset = 0
    for delivery in value["deliveries"]:
        exact_keys(delivery, {"event", "at_ms"})
        assert delivery["event"] in ids, "unknown event reference"
        integer(delivery["at_ms"], 0, 60000)
        assert delivery["at_ms"] >= last_offset, "decreasing schedule"
        last_offset = delivery["at_ms"]


def assert_report(actual: object, expected: dict) -> None:
    exact_keys(actual, {"schema_version", "deliveries", "summary"})
    integer(actual["schema_version"], 1, 1)
    assert isinstance(actual["deliveries"], list)
    succeeded = 0
    for index, row in enumerate(actual["deliveries"]):
        exact_keys(row, {"index", "event", "scheduled_at_ms", "outcome", "http_status"})
        integer(row["index"], index, index)
        assert isinstance(row["event"], str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", row["event"])
        integer(row["scheduled_at_ms"], 0, 60000)
        outcome, status = row["outcome"], row["http_status"]
        assert outcome in {"success", "http_error", "timeout", "transport_error"}
        if outcome in {"timeout", "transport_error"}:
            assert status is None
        else:
            integer(status, 100, 599)
            assert (200 <= status < 300) == (outcome == "success")
        succeeded += outcome == "success"
    exact_keys(actual["summary"], {"total", "succeeded", "failed"})
    for key in actual["summary"]:
        integer(actual["summary"][key], 0, 10000)
    assert actual["summary"] == {
        "total": len(actual["deliveries"]), "succeeded": succeeded,
        "failed": len(actual["deliveries"]) - succeeded,
    }, "inconsistent report summary"
    assert actual == expected, "report differs from expected-output fixture"


def load_report(path: Path, expected: dict) -> dict:
    assert path.is_file(), "runtime did not create its report"
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AssertionError("runtime report is not valid UTF-8 JSON") from exc
    assert_report(actual, expected)
    return actual


def assert_observations(observations: list[Observation], scenario: dict, ordered: bool = True) -> None:
    events = {event["id"]: event["payload"] for event in scenario["events"]}
    expected = [(item["event"], events[item["event"]]) for item in scenario["deliveries"]]
    actual = [(item.event_id, item.payload) for item in observations]
    if ordered:
        assert actual == expected, "receiver event order, ID, or payload mismatch"
    else:
        canonical = lambda pair: json.dumps(pair, sort_keys=True, separators=(",", ":"))
        assert sorted(map(canonical, actual)) == sorted(map(canonical, expected)), "receiver delivery multiset mismatch"
    assert all(item.content_type and item.content_type.split(";")[0].lower() == "application/json" for item in observations), "missing JSON content type"
    assert all(item.path == "/hook" for item in observations), "unexpected request target"


def resolve_binary(path: str) -> Path:
    binary = Path(path).resolve()
    if os.name == "nt" and not binary.is_file() and not binary.suffix:
        binary = binary.with_suffix(".exe")
    if not binary.is_file():
        raise ValueError(f"binary not found: {binary}")
    return binary


def run_binary(binary: Path, scenario: Path, target: str, report: Path, timeout: float = 12) -> subprocess.CompletedProcess:
    command = [str(binary), "run", "--scenario", str(scenario), "--target", target, "--report", str(report)]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for its child before raising.
        raise AssertionError("runtime exceeded the harness subprocess timeout") from exc


def expected_success(scenario: dict) -> dict:
    rows = [{"index": index, "event": item["event"], "scheduled_at_ms": item["at_ms"],
             "outcome": "success", "http_status": 204} for index, item in enumerate(scenario["deliveries"])]
    return {"schema_version": 1, "deliveries": rows,
            "summary": {"total": len(rows), "succeeded": len(rows), "failed": 0}}
