"""Test readiness boundaries without running the application."""
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import check


class ReleaseGuardTests(unittest.TestCase):
    def test_release_rejects_pending_before_subprocess(self):
        with patch.object(check, "runtime_status", return_value="pending"), patch.object(check, "run") as run:
            with self.assertRaisesRegex(ValueError, "pending"):
                check.release()
            run.assert_not_called()

    def test_workflow_refuses_missing_git_history(self):
        with patch.object(check, "run", side_effect=subprocess.CalledProcessError(128, "git")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                check.workflow()
            self.assertEqual(run.call_count, 1)

    def test_validated_status_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            for value in ({"runtime": "unknown"}, {"runtime": True}, {}, {"runtime": "implemented", "extra": 1}, []):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    check.runtime_status(path)
            for value in ("pending", "implemented"):
                path.write_text(json.dumps({"runtime": value}), encoding="utf-8")
                self.assertEqual(check.runtime_status(path), value)

    def test_implemented_guard_allows_gate_to_continue(self):
        with patch.object(check, "runtime_status", return_value="implemented"):
            check.require_implemented()


if __name__ == "__main__":
    unittest.main()
