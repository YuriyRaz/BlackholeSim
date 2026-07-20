from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    load_json,
    load_v4_state,
    write_v4_document,
)
from jobctl import parser, record_session  # noqa: E402


NOW = "2026-07-14T12:00:00Z"


class Version4SessionRecordingTest(unittest.TestCase):
    def run_document(self, job_ids: list[str]) -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-SESSION",
            "goal": "Record transport sessions",
            "status": "active",
            "job_ids": job_ids,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def job_document(
        self,
        job_id: str = "J001",
        *,
        status: str = "queued",
        depends_on: list[str] | None = None,
    ) -> dict:
        return {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": int(job_id.removeprefix("J")),
            "depends_on": depends_on or [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": False,
            "report_path": f"jobs/{job_id}/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def write_state(self, root: Path, jobs: list[dict]) -> None:
        root.mkdir(parents=True)
        write_v4_document(
            root / "run.json",
            "run",
            self.run_document([job["id"] for job in jobs]),
        )
        for job in jobs:
            write_v4_document(root / "jobs" / job["id"] / "job.json", "job", job)
            (root / job["prompt_path"]).write_text("Complete the job.\n", encoding="utf-8")
            (root / job["report_path"]).write_text("", encoding="utf-8")

    def invoke_session(
        self, root: Path, job_id: str, session_ref: str
    ) -> dict:
        args = parser().parse_args([
            "session",
            "--run",
            str(root),
            "--job",
            job_id,
            "--session-ref",
            session_ref,
        ])
        return record_session(args)

    def test_cli_records_pre_execution_session_and_identical_repeat_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, [self.job_document()])

            first = self.invoke_session(root, "J001", "transport://opaque session/1")
            self.assertEqual(
                first,
                {
                    "job_id": "J001",
                    "session_ref": "transport://opaque session/1",
                    "status": "running",
                    "recorded": True,
                },
            )
            recorded = load_v4_state(root)["jobs"]["J001"]
            self.assertEqual(recorded["status"], "running")
            self.assertEqual(recorded["session_ref"], "transport://opaque session/1")
            self.assertEqual(recorded["revision"], 2)

            before = (root / "jobs" / "J001" / "job.json").read_bytes()
            repeated = self.invoke_session(root, "J001", "transport://opaque session/1")
            self.assertFalse(repeated["recorded"])
            self.assertEqual(
                (root / "jobs" / "J001" / "job.json").read_bytes(), before
            )

    def test_cli_accepts_starting_and_rejects_conflicting_or_invalid_recordings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            starting_root = base / "starting"
            self.write_state(starting_root, [self.job_document(status="starting")])
            accepted = self.invoke_session(starting_root, "J001", "session-starting")
            self.assertTrue(accepted["recorded"])
            self.assertEqual(
                load_v4_state(starting_root)["jobs"]["J001"]["status"], "running"
            )

            conflict_before = (starting_root / "jobs" / "J001" / "job.json").read_bytes()
            with self.assertRaisesRegex(OrchestratorError, "different session reference"):
                self.invoke_session(starting_root, "J001", "session-conflict")
            self.assertEqual(
                (starting_root / "jobs" / "J001" / "job.json").read_bytes(),
                conflict_before,
            )

            blocked_root = base / "blocked"
            dependency = self.job_document("J001")
            blocked = self.job_document("J002", depends_on=["J001"])
            self.write_state(blocked_root, [dependency, blocked])
            blocked_before = (blocked_root / "jobs" / "J002" / "job.json").read_bytes()
            with self.assertRaisesRegex(OrchestratorError, "completed dependencies"):
                self.invoke_session(blocked_root, "J002", "session-blocked")
            self.assertEqual(
                (blocked_root / "jobs" / "J002" / "job.json").read_bytes(),
                blocked_before,
            )

            with self.assertRaisesRegex(OrchestratorError, "non-empty string"):
                self.invoke_session(blocked_root, "J001", "   ")

    def test_transition_path_can_atomically_record_session_and_first_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            current = self.job_document()
            self.write_state(root, [current])
            path = root / "jobs" / "J001" / "job.json"

            proposed = {
                **copy.deepcopy(current),
                "status": "completed",
                "session_ref": "session-with-first-response",
                "outcome": {
                    "status": "completed",
                    "summary": "The first response completed the job.",
                },
                "updated_at": "2026-07-14T12:01:00Z",
                "revision": 2,
            }
            write_v4_document(
                path,
                "job",
                proposed,
                transition_path=["starting", "running", "completed"],
            )
            self.assertEqual(load_json(path), proposed)
            self.assertEqual(load_v4_state(root)["jobs"]["J001"], proposed)

    def test_incoherent_first_outcome_path_does_not_partially_record_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            current = self.job_document()
            self.write_state(root, [current])
            path = root / "jobs" / "J001" / "job.json"
            before = path.read_bytes()
            incoherent = {
                **copy.deepcopy(current),
                "status": "completed",
                "session_ref": "session-with-bad-response",
                "revision": 2,
            }

            with self.assertRaisesRegex(OrchestratorError, "coherent completed outcome"):
                write_v4_document(
                    path,
                    "job",
                    incoherent,
                    transition_path=["starting", "running", "completed"],
                )

            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(load_v4_state(root)["jobs"]["J001"], current)

    def test_transition_path_must_include_each_valid_status_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            current = self.job_document()
            self.write_state(root, [current])
            path = root / "jobs" / "J001" / "job.json"
            proposed = {
                **copy.deepcopy(current),
                "status": "running",
                "session_ref": "session-skipping-starting",
                "revision": 2,
            }
            before = path.read_bytes()

            with self.assertRaisesRegex(
                OrchestratorError, "invalid job status transition 'queued' -> 'running'"
            ):
                write_v4_document(
                    path,
                    "job",
                    proposed,
                    transition_path=["running"],
                )

            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
