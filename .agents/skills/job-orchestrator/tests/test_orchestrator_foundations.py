from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    Lease,
    OrchestratorError,
    canonical_bytes,
    load_json,
    parse_time,
    snapshot_differences,
    stable_id,
    validate_schema,
    write_json,
)


class FoundationTest(unittest.TestCase):
    def test_canonical_json_and_ids_are_deterministic(self) -> None:
        left = {"é": [1, True], "a": "value"}
        right = {"a": "value", "é": [1, True]}
        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(stable_id("TEST", left), stable_id("TEST", right))
        with self.assertRaisesRegex(OrchestratorError, "canonical JSON"):
            canonical_bytes({"bad": float("nan")})

    def test_timestamps_require_an_offset(self) -> None:
        self.assertEqual(parse_time("2026-07-09T12:00:00Z").tzinfo, timezone.utc)
        with self.assertRaisesRegex(OrchestratorError, "UTC offset"):
            parse_time("2026-07-09T12:00:00")

    def test_schema_rejects_wrong_types_formats_and_unknown_fields(self) -> None:
        action = {
            "schema_version": 3,
            "action_id": "ACT-1",
            "type": "wait",
            "run_id": "run-1",
            "job_id": None,
            "status": "unresolved",
            "correlation_id": "run-1",
            "created_at": "2026-07-09T12:00:00Z",
            "prompt": None,
        }
        validate_schema("action", action)
        for key, value, message in (
            ("status", "unknown", "one of"),
            ("created_at", "yesterday", "RFC 3339"),
            ("unexpected", True, "unexpected fields"),
        ):
            invalid = {**action, key: value}
            with self.assertRaisesRegex(OrchestratorError, message):
                validate_schema("action", invalid)

    def test_lease_contention_handoff_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "orchestrator.lock"
            first = Lease(path, "controller-a", 30)
            first.acquire()
            with self.assertRaisesRegex(OrchestratorError, "lease held"):
                Lease(path, "controller-b", 30).acquire()

            first.handoff("controller-b")
            first.release()
            persisted = load_json(path)
            self.assertEqual(persisted["handoff"]["to_controller_id"], "controller-b")

            second = Lease(path, "controller-b", 30)
            second.acquire()
            self.assertEqual(load_json(path)["controller_id"], "controller-b")
            second.release()
            self.assertFalse(path.exists())

            expired = Lease(path, "controller-a", 30)
            expired.acquire()
            record = load_json(path)
            record["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat().replace("+00:00", "Z")
            write_json(path, record)
            with self.assertRaisesRegex(OrchestratorError, "expired"):
                expired.renew()
            replacement = Lease(path, "controller-b", 30)
            replacement.acquire()
            replacement.release()

    def test_simultaneous_lease_acquisition_has_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "orchestrator.lock"
            start = threading.Barrier(2)
            winner_ready = threading.Event()
            loser_done = threading.Event()
            outcomes: list[str] = []

            def contend(controller: str) -> None:
                lease = Lease(path, controller, 30)
                start.wait()
                try:
                    lease.acquire()
                except OrchestratorError:
                    outcomes.append("contended")
                    loser_done.set()
                    return
                outcomes.append("acquired")
                winner_ready.set()
                loser_done.wait(2)
                lease.release()

            threads = [
                threading.Thread(target=contend, args=(controller,))
                for controller in ("controller-a", "controller-b")
            ]
            for thread in threads:
                thread.start()
            self.assertTrue(winner_ready.wait(2))
            for thread in threads:
                thread.join(2)
            self.assertEqual(sorted(outcomes), ["acquired", "contended"])

    def test_snapshot_difference_reports_every_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = {
                "run": {"run_id": "run-1"},
                "jobs": {},
                "workflows": {},
                "steps": {},
                "sessions": {},
                "actions": {},
                "dispatches": {},
            }
            write_json(root / "run.json", {"run_id": "corrupt"})
            differences = snapshot_differences(root, state)
            self.assertEqual(
                differences,
                [
                    "jobs\\index.json snapshot missing"
                    if sys.platform == "win32"
                    else "jobs/index.json snapshot missing",
                    "queue.json snapshot missing",
                    "run.json snapshot disagrees with journal",
                ],
            )

    def test_load_json_strips_markdown_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "wrapped.json"
            path.write_text("```json\n{\"a\": 1}\n```", encoding="utf-8")
            self.assertEqual(load_json(path), {"a": 1})
            
            path.write_text("  ```\n{\"b\": 2}\n```  ", encoding="utf-8")
            self.assertEqual(load_json(path), {"b": 2})

    def test_analyze_json_failure_provides_heuristic_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "truncated.json"
            path.write_text('[\n  {"a": 1},\n  {"b": 2},\n  {"c": 3', encoding="utf-8")
            with self.assertRaisesRegex(OrchestratorError, "Best effort partial read: Found 2 complete top-level objects"):
                load_json(path)


if __name__ == "__main__":
    unittest.main()
