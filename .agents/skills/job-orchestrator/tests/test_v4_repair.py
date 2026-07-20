from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    load_json,
    load_v4_state,
    select_v4_next_operation,
    write_v4_document,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"
NOW = "2026-07-14T12:00:00Z"


class Version4RepairCliTest(unittest.TestCase):
    def write_state(self, root: Path, *, status: str, session_ref: str | None) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-REPAIR",
            "goal": "Repair one job",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Repair this job",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": session_ref,
            "priority": 10,
            "creation_sequence": 1,
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": False,
            "report_path": "jobs/J001/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        if status == "waiting_for_input":
            job["pending_question"] = {
                "text": "Which recovery option should be used?",
                "context": "The prior session cannot decide safely.",
            }
            job["outcome"] = {
                "status": "needs_input",
                "summary": "Recovery needs operator input.",
                "question": "Which recovery option should be used?",
            }
        elif status == "completed":
            job["outcome"] = {"status": "completed", "summary": "Complete."}
        elif status == "failed":
            job["outcome"] = {"status": "failed", "summary": "Failed."}
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text("", encoding="utf-8")

    def invoke(
        self,
        root: Path,
        disposition: str,
        reason: str,
        *,
        job_id: str = "J001",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(JOBCTL),
                "repair",
                "--run",
                str(root),
                "--job",
                job_id,
                "--disposition",
                disposition,
                "--reason",
                reason,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_failed_disposition_atomically_replaces_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="running", session_ref="transport-session-1")
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            process = self.invoke(root, "failed", "  Transport state is unrecoverable.  ")

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            result = json.loads(process.stdout)
            repaired = load_json(job_path)
            self.assertEqual(
                result,
                {
                    "repaired": True,
                    "job_id": "J001",
                    "disposition": "failed",
                    "reason": "Transport state is unrecoverable.",
                    "run_status": "failed",
                    "ready_job_ids": [],
                },
            )
            self.assertEqual(repaired["status"], "failed")
            self.assertEqual(
                repaired["outcome"],
                {"status": "failed", "summary": "Transport state is unrecoverable."},
            )
            self.assertEqual(repaired["revision"], 2)
            self.assertEqual(
                (job_path.parent / "job.previous.json").read_bytes(), before
            )
            state = load_v4_state(root)
            self.assertEqual(state["run"]["status"], "failed")
            self.assertEqual(
                select_v4_next_operation(state, run_root=root),
                {"operation": "run_complete"},
            )
            self.assertFalse((root / "events.jsonl").exists())
            self.assertFalse((root / "actions").exists())

    def test_canceled_disposition_is_job_level(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="queued", session_ref=None)

            process = self.invoke(root, "canceled", "Operator no longer wants this job.")

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            repaired = load_json(root / "jobs" / "J001" / "job.json")
            self.assertEqual(repaired["status"], "canceled")
            self.assertIsNone(repaired["outcome"])
            self.assertEqual(repaired["revision"], 2)
            self.assertEqual(load_json(root / "run.json")["status"], "canceled")

    def test_repair_preserves_session_reports_recovery_evidence_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(
                root,
                status="waiting_for_input",
                session_ref="transport-session-1",
            )
            job_path = root / "jobs" / "J001" / "job.json"
            before = load_json(job_path)
            before["checkpoint_path"] = "jobs/J001/checkpoint.md"
            before["recovery_policy"] = {
                "effect": "external_non_idempotent",
                "check": "Query whether the external operation completed.",
            }
            write_v4_document(job_path, "job", before)
            report_path = root / before["report_path"]
            checkpoint_path = root / before["checkpoint_path"]
            report_path.write_text("Partial durable report.\n", encoding="utf-8")
            checkpoint_path.write_text("Recovery checkpoint.\n", encoding="utf-8")
            report_before = report_path.read_bytes()
            checkpoint_before = checkpoint_path.read_bytes()

            process = self.invoke(root, "canceled", "  Unsafe to continue.  ")

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            repaired = load_json(job_path)
            self.assertEqual(repaired["session_ref"], before["session_ref"])
            self.assertEqual(repaired["report_path"], before["report_path"])
            self.assertEqual(repaired["related_reports"], before["related_reports"])
            self.assertEqual(repaired["checkpoint_path"], before["checkpoint_path"])
            self.assertEqual(repaired["recovery_policy"], before["recovery_policy"])
            self.assertEqual(report_path.read_bytes(), report_before)
            self.assertEqual(checkpoint_path.read_bytes(), checkpoint_before)
            self.assertEqual(
                repaired["repair"],
                {
                    "disposition": "canceled",
                    "reason": "Unsafe to continue.",
                    "repaired_at": repaired["updated_at"],
                    "previous_status": "waiting_for_input",
                    "previous_outcome": before["outcome"],
                    "previous_pending_question": before["pending_question"],
                    "previous_waiting_on": [],
                },
            )

    def test_failed_repair_keeps_dependent_job_blocked_and_run_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="running", session_ref="transport-session-1")
            run_path = root / "run.json"
            run = load_json(run_path)
            write_v4_document(run_path, "run", {**run, "job_ids": ["J001", "J002"]})
            dependent = {
                **load_json(root / "jobs" / "J001" / "job.json"),
                "id": "J002",
                "title": "Blocked dependent job",
                "status": "queued",
                "prompt_path": "jobs/J002/prompt.md",
                "session_ref": None,
                "creation_sequence": 2,
                "depends_on": ["J001"],
                "report_path": "jobs/J002/report.md",
            }
            write_v4_document(root / "jobs" / "J002" / "job.json", "job", dependent)
            (root / dependent["prompt_path"]).write_text("Wait for J001.\n", encoding="utf-8")
            (root / dependent["report_path"]).write_text("", encoding="utf-8")

            process = self.invoke(root, "failed", "The dependency cannot recover.")

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            result = json.loads(process.stdout)
            state = load_v4_state(root)
            self.assertEqual(result["run_status"], "active")
            self.assertEqual(result["ready_job_ids"], [])
            self.assertEqual(state["jobs"]["J001"]["status"], "failed")
            self.assertEqual(state["jobs"]["J002"]["status"], "queued")
            self.assertEqual(state["ready_job_ids"], [])
            self.assertEqual(state["run"]["status"], "active")
            self.assertEqual(
                select_v4_next_operation(state, run_root=root),
                {"operation": "wait"},
            )
            self.assertFalse((root / "events.jsonl").exists())
            self.assertFalse((root / "actions").exists())

    def test_empty_operator_reason_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="running", session_ref="transport-session-1")
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            process = self.invoke(root, "failed", "   ")

            self.assertEqual(process.returncode, 2, process.stderr or process.stdout)
            self.assertEqual(
                json.loads(process.stdout),
                {"error": "repair reason must be a non-empty string"},
            )
            self.assertEqual(job_path.read_bytes(), before)
            self.assertFalse((job_path.parent / "job.previous.json").exists())

    def test_unknown_job_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="running", session_ref="transport-session-1")
            run_path = root / "run.json"
            job_path = root / "jobs" / "J001" / "job.json"
            before = (run_path.read_bytes(), job_path.read_bytes())

            process = self.invoke(
                root,
                "failed",
                "Unknown work cannot continue.",
                job_id="J999",
            )

            self.assertEqual(process.returncode, 2, process.stderr or process.stdout)
            self.assertEqual(json.loads(process.stdout), {"error": "unknown job 'J999'"})
            self.assertEqual((run_path.read_bytes(), job_path.read_bytes()), before)
            self.assertFalse((job_path.parent / "job.previous.json").exists())

    def test_conflicting_terminal_repairs_are_rejected_without_mutation(self) -> None:
        cases = (
            ("completed", "failed", "transport-session-1"),
            ("failed", "canceled", "transport-session-1"),
            ("canceled", "failed", None),
        )
        for status, disposition, session_ref in cases:
            with self.subTest(status=status, disposition=disposition), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                self.write_state(root, status=status, session_ref=session_ref)
                job_path = root / "jobs" / "J001" / "job.json"
                before = job_path.read_bytes()

                process = self.invoke(root, disposition, "Conflicting terminal repair.")

                self.assertEqual(process.returncode, 2, process.stderr or process.stdout)
                self.assertIn("already terminal", json.loads(process.stdout)["error"])
                self.assertEqual(job_path.read_bytes(), before)
                self.assertFalse((job_path.parent / "job.previous.json").exists())

    def test_completion_repair_claim_is_rejected_with_reconciliation_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="running", session_ref="transport-session-1")
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            process = self.invoke(root, "completed", "Operator claims completion.")

            self.assertEqual(process.returncode, 2, process.stderr or process.stdout)
            error = json.loads(process.stdout)["error"]
            self.assertIn("cannot claim completion", error)
            self.assertIn("coherent completed outcome", error)
            self.assertIn("required report", error)
            self.assertIn("recover", error)
            self.assertEqual(job_path.read_bytes(), before)
            self.assertFalse((job_path.parent / "job.previous.json").exists())

    def test_default_repair_help_does_not_expose_abort_dispatch(self) -> None:
        process = subprocess.run(
            [sys.executable, str(JOBCTL), "repair", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--job", process.stdout)
        self.assertIn("--disposition {failed,canceled}", process.stdout)
        self.assertIn("--reason", process.stdout)
        self.assertNotIn("abort-dispatch", process.stdout)


if __name__ == "__main__":
    unittest.main()
