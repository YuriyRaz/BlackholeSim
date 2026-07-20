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
    derive_v4_run_status,
    load_v4_state,
    record_v4_outcome,
    select_v4_next_operation,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4RunCompletionTest(unittest.TestCase):
    def run_document(self, job_ids: list[str], *, status: str = "active") -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-COMPLETION",
            "goal": "Derive coherent run completion",
            "status": status,
            "job_ids": job_ids,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def job_document(self, job_id: str, *, status: str) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": int(job_id[1:]),
            "depends_on": [],
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
        if status in {"running", "waiting_for_input", "waiting_for_job", "completed"}:
            job["session_ref"] = f"session-{job_id}"
        if status == "completed":
            job["outcome"] = {"status": "completed", "summary": "Complete."}
        elif status == "failed":
            job["outcome"] = {"status": "failed", "summary": "Failed."}
        elif status in {"waiting_for_input", "waiting_for_job"}:
            question = f"What does {job_id} require?"
            job["pending_question"] = {"text": question}
            job["outcome"] = {
                "status": "needs_input",
                "summary": "Input is required.",
                "question": question,
            }
        return job

    def write_state(self, root: Path, jobs: list[dict], *, status: str = "active") -> None:
        write_v4_document(
            root / "run.json",
            "run",
            self.run_document([job["id"] for job in jobs], status=status),
        )
        for job in jobs:
            write_v4_document(root / "jobs" / job["id"] / "job.json", "job", job)
            (root / job["prompt_path"]).write_text("Prompt\n", encoding="utf-8")
            (root / job["report_path"]).write_text(
                "Report\n" if job["status"] == "completed" else "",
                encoding="utf-8",
            )

    def test_derives_terminal_success_failure_and_cancellation_policy(self) -> None:
        cases = (
            (["completed"], "completed"),
            (["failed"], "failed"),
            (["canceled"], "canceled"),
            (["completed", "canceled"], "canceled"),
            (["completed", "canceled", "failed"], "failed"),
        )
        for statuses, expected in cases:
            with self.subTest(statuses=statuses):
                jobs = {
                    f"J{index:03d}": self.job_document(
                        f"J{index:03d}", status=status
                    )
                    for index, status in enumerate(statuses, 1)
                }
                state = {
                    "run": self.run_document(list(jobs)),
                    "jobs": jobs,
                }

                self.assertEqual(derive_v4_run_status(jobs), expected)
                self.assertEqual(
                    select_v4_next_operation(state, run_root=Path("unused")),
                    {"operation": "run_complete"},
                )

    def test_outcome_recording_persists_terminal_aggregate_run_status(self) -> None:
        cases = (
            ({"status": "completed", "summary": "Complete."}, "completed"),
            ({"status": "failed", "summary": "Failed."}, "failed"),
        )
        for outcome, expected in cases:
            with self.subTest(status=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                self.write_state(root, [self.job_document("J001", status="queued")])

                result = record_v4_outcome(
                    root,
                    "J001",
                    outcome,
                    controller="completion-test",
                    session_ref="session-J001",
                )

                state = load_v4_state(root)
                self.assertEqual(result["run_status"], expected)
                self.assertEqual(state["run"]["status"], expected)
                self.assertEqual(state["run"]["revision"], 2)
                self.assertEqual(
                    select_v4_next_operation(state, run_root=root),
                    {"operation": "run_complete"},
                )

    def test_unresolved_question_blocks_completion(self) -> None:
        job = self.job_document("J001", status="waiting_for_input")
        state = {"run": self.run_document(["J001"]), "jobs": {"J001": job}}

        self.assertEqual(derive_v4_run_status(state["jobs"]), "active")
        self.assertEqual(
            select_v4_next_operation(state, run_root=Path("unused"))["operation"],
            "ask_user",
        )

    def test_required_advisory_report_blocks_completion(self) -> None:
        origin = self.job_document("J001", status="waiting_for_job")
        advisory = self.job_document("J002", status="completed")
        origin["waiting_on"] = ["J002"]
        jobs = {"J001": origin, "J002": advisory}
        state = {"run": self.run_document(list(jobs)), "jobs": jobs}

        self.assertEqual(derive_v4_run_status(jobs), "active")
        self.assertEqual(
            select_v4_next_operation(state, run_root=Path("unused")),
            {"operation": "wait"},
        )

    def test_recovery_decision_blocks_completion(self) -> None:
        job = self.job_document("J001", status="running")
        job["status"] = "recovering"
        jobs = {"J001": job}
        state = {"run": self.run_document(["J001"]), "jobs": jobs}

        self.assertEqual(derive_v4_run_status(jobs), "active")
        self.assertEqual(
            select_v4_next_operation(state, run_root=Path("unused")),
            {"operation": "wait"},
        )

    def test_terminal_run_status_cannot_hide_unresolved_work(self) -> None:
        job = self.job_document("J001", status="waiting_for_input")
        run = self.run_document(["J001"], status="completed")
        state = {"run": run, "jobs": {"J001": job}}

        with self.assertRaisesRegex(OrchestratorError, "disagrees with required job state"):
            select_v4_next_operation(state, run_root=Path("unused"))

        original = copy.deepcopy(run)
        self.assertEqual(state["run"], original)


if __name__ == "__main__":
    unittest.main()
