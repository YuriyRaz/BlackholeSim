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
    validate_v4_job_transition,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4TransitionCoherenceTest(unittest.TestCase):
    def run_document(self, job_ids: list[str]) -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-1",
            "goal": "Complete the request",
            "status": "active",
            "job_ids": job_ids,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def job_document(
        self,
        job_id: str,
        *,
        status: str = "queued",
        depends_on: list[str] | None = None,
        parent_job_id: str | None = None,
    ) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": int(job_id.removeprefix("J")),
            "depends_on": depends_on or [],
            "parent_job_id": parent_job_id,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": True,
            "report_path": f"jobs/{job_id}/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        if status in {"running", "waiting_for_input", "waiting_for_job", "completed"}:
            job["session_ref"] = f"session-{job_id}"
        if status in {"waiting_for_input", "waiting_for_job"}:
            question = "Which policy should be used?"
            job["pending_question"] = {"text": question, "context": "Two remain."}
            job["outcome"] = {
                "status": "needs_input",
                "summary": "A policy decision is required.",
                "question": question,
            }
        if status == "completed":
            job["outcome"] = {
                "status": "completed",
                "summary": "Job complete.",
                "report_path": job["report_path"],
            }
        if status == "failed":
            job["outcome"] = {
                "status": "failed",
                "summary": "Job failed.",
            }
        return job

    def write_state(self, root: Path, jobs: list[dict]) -> None:
        write_v4_document(
            root / "run.json", "run", self.run_document([job["id"] for job in jobs])
        )
        for job in jobs:
            write_v4_document(
                root / "jobs" / job["id"] / "job.json", "job", job
            )
            if job["status"] == "completed" and job["report_required"]:
                (root / job["report_path"]).write_text(
                    f"Report for {job['id']}\n", encoding="utf-8"
                )

    def assert_load_rejected(self, jobs: list[dict], message: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, jobs)
            with self.assertRaisesRegex(OrchestratorError, message):
                load_v4_state(root)

    def test_loads_coherent_question_waiting_terminal_and_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = self.job_document("J001", status="completed")
            waiting = self.job_document("J002", status="waiting_for_job")
            waiting["waiting_on"] = ["J003"]
            advisory = self.job_document("J003", status="running", parent_job_id="J002")
            dependent = self.job_document("J004", depends_on=["J001"])
            self.write_state(root, [completed, waiting, advisory, dependent])

            state = load_v4_state(root)

            self.assertEqual(state["ready_job_ids"], ["J004"])
            self.assertEqual(state["jobs"]["J002"]["waiting_on"], ["J003"])

    def test_rejects_session_status_inconsistency(self) -> None:
        running = self.job_document("J001", status="running")
        running["session_ref"] = None
        self.assert_load_rejected([running], "requires a session_ref")

        queued = self.job_document("J001")
        queued["session_ref"] = "session-J001"
        self.assert_load_rejected([queued], "must not have a session_ref")

    def test_rejects_incoherent_pending_question_state(self) -> None:
        waiting = self.job_document("J001", status="waiting_for_input")
        waiting["pending_question"]["text"] = "A different question"
        self.assert_load_rejected([waiting], "pending question must match")

        running = self.job_document("J001", status="running")
        running["pending_question"] = {"text": "Unexpected question"}
        self.assert_load_rejected([running], "must not have a pending_question")

    def test_rejects_invalid_waiting_relationships_and_deadlocks(self) -> None:
        waiting = self.job_document("J001", status="waiting_for_job")
        waiting["waiting_on"] = ["UNKNOWN"]
        self.assert_load_rejected([waiting], "waiting on unknown jobs")

        origin = self.job_document("J001", status="waiting_for_job")
        origin["waiting_on"] = ["J002"]
        blocked_advisory = self.job_document("J002", depends_on=["J001"])
        self.assert_load_rejected(
            [origin, blocked_advisory], "dependency/waiting cycle"
        )

    def test_rejects_incoherent_terminal_outcomes_and_reports(self) -> None:
        completed = self.job_document("J001", status="completed")
        completed["outcome"] = {
            "status": "failed",
            "summary": "Contradictory failure.",
        }
        self.assert_load_rejected([completed], "requires a coherent completed outcome")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = self.job_document("J001", status="completed")
            self.write_state(root, [completed])
            (root / completed["report_path"]).unlink()
            with self.assertRaisesRegex(OrchestratorError, "accessible non-empty report"):
                load_v4_state(root)

    def test_transition_requires_completed_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dependency = self.job_document("J001")
            dependent = self.job_document("J002", depends_on=["J001"])
            self.write_state(root, [dependency, dependent])
            state = load_v4_state(root)
            proposed = copy.deepcopy(dependent)
            proposed["status"] = "starting"

            with self.assertRaisesRegex(OrchestratorError, "completed dependencies"):
                validate_v4_job_transition(
                    dependent, proposed, state["jobs"], run_root=root
                )

            dependency = self.job_document("J001", status="completed")
            write_json(root / "jobs" / "J001" / "job.json", dependency)
            (root / dependency["report_path"]).write_text("Complete.\n", encoding="utf-8")
            state = load_v4_state(root)
            validate_v4_job_transition(
                state["jobs"]["J002"], proposed, state["jobs"], run_root=root
            )

    def test_existing_job_write_rejects_invalid_transition_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = self.job_document("J001")
            self.write_state(root, [current])
            path = root / "jobs" / "J001" / "job.json"
            proposed = copy.deepcopy(current)
            proposed["status"] = "completed"
            proposed["session_ref"] = "session-J001"
            proposed["outcome"] = {
                "status": "completed",
                "summary": "Complete.",
                "report_path": proposed["report_path"],
            }
            (root / proposed["report_path"]).write_text("Complete.\n", encoding="utf-8")

            with self.assertRaisesRegex(OrchestratorError, "invalid job status transition"):
                write_v4_document(path, "job", proposed)

            self.assertEqual(load_json(path), current)


if __name__ == "__main__":
    unittest.main()
