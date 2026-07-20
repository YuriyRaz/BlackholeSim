from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    RunLock,
    load_json,
    run_lock,
)


class Version4RunLockTest(unittest.TestCase):
    def write_run(self, root: Path, version: int = 4) -> None:
        root.mkdir()
        document = {
            "schema_version": version,
            "run_id": "RUN-1",
        }
        if version == 4:
            document["protocol_version"] = 4
        else:
            document["protocol"] = {"version": version}
        (root / "run.json").write_text(
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_live_lock_refuses_contention_without_lease_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            self.write_run(run)
            owner = RunLock(run / "orchestrator.lock", "controller-a")
            owner.acquire()
            record = load_json(owner.path)

            self.assertEqual(
                set(record),
                {
                    "schema_version", "lock_id", "controller_id", "owner_pid",
                    "owner_host", "acquired_at",
                },
            )
            self.assertEqual(record["schema_version"], 4)
            self.assertEqual(record["owner_pid"], os.getpid())
            self.assertEqual(record["owner_host"], socket.gethostname())
            with self.assertRaisesRegex(OrchestratorError, "active controller"):
                RunLock(owner.path, "controller-b").acquire()

            self.assertEqual(load_json(owner.path), record)
            owner.release()
            self.assertFalse(owner.path.exists())

    def test_stale_lock_requires_explicit_takeover(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            self.write_run(run)
            path = run / "orchestrator.lock"
            owner = RunLock(path, "controller-a")
            owner.acquire()
            stale_record = load_json(path)
            contender = RunLock(path, "controller-b")

            with patch("orchestrator_core._process_is_running", return_value=False):
                with self.assertRaisesRegex(
                    OrchestratorError, "stale run lock.*explicit takeover"
                ):
                    contender.acquire()
                self.assertEqual(load_json(path), stale_record)
                contender.acquire(takeover=True)

            self.assertEqual(load_json(path)["controller_id"], "controller-b")
            contender.release()

    def test_explicit_takeover_cannot_steal_live_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            self.write_run(run)
            path = run / "orchestrator.lock"
            owner = RunLock(path, "controller-a")
            owner.acquire()

            with self.assertRaisesRegex(OrchestratorError, "active controller"):
                RunLock(path, "controller-b").acquire(takeover=True)

            self.assertEqual(load_json(path)["controller_id"], "controller-a")
            owner.release()

    def test_mutation_context_uses_v4_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            self.write_run(run)

            with run_lock(run, "controller-a"):
                record = load_json(run / "orchestrator.lock")
                self.assertEqual(record["schema_version"], 4)
                self.assertNotIn("expires_at", record)
                self.assertNotIn("heartbeat", record)

            self.assertFalse((run / "orchestrator.lock").exists())

if __name__ == "__main__":
    unittest.main()
