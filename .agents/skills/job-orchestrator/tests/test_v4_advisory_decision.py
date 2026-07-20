from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import load_v4_state, write_v4_document  # noqa: E402


JOBCTL = ROOT / "scripts" / "jobctl.py"
NOW = "2026-07-14T12:00:00Z"


class Version4AdvisoryDecisionTest(unittest.TestCase):
    def job(
        self,
        job_id: str,
        *,
        status: str,
        parent_job_id: str | None = None,
        creation_sequence: int,
    ) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": creation_sequence,
            "depends_on": [],
            "parent_job_id": parent_job_id,
            "waiting_on": [],
            "pending_question": None,
            "answers": [],
            "related_reports": [],
            "report_required": parent_job_id is not None,
            "report_path": f"jobs/{job_id}/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        if status == "waiting_for_job":
            question = "Which implementation policy should be used?"
            job.update({
                "session_ref": "session-origin",
                "waiting_on": ["J002"],
                "pending_question": {
                    "text": question,
                    "context": "The implementation has two valid policies.",
                },
                "outcome": {
                    "status": "needs_input",
                    "summary": "An advisory decision is required.",
                    "question": question,
                },
            })
        elif status == "failed":
            job.update({
                "session_ref": f"session-{job_id}",
                "outcome": {
                    "status": "failed",
                    "summary": "The advisory job could not provide a report.",
                },
            })
        return job

    def write_run(
        self,
        root: Path,
        *,
        advisory_status: str = "failed",
        with_replacement: bool = False,
    ) -> None:
        jobs = [
            self.job("J001", status="waiting_for_job", creation_sequence=1),
            self.job(
                "J002",
                status=advisory_status,
                parent_job_id="J001",
                creation_sequence=2,
            ),
        ]
        if with_replacement:
            jobs.append(self.job(
                "J003",
                status="queued",
                parent_job_id="J001",
                creation_sequence=3,
            ))

        root.mkdir(parents=True)
        write_v4_document(root / "run.json", "run", {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-ADVISORY-DECISION",
            "goal": "Resolve an advisory failure explicitly",
            "status": "active",
            "job_ids": [job["id"] for job in jobs],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        })
        (root / "setup.json").write_text(json.dumps({
            "schema_version": 4,
            "request_path": "request.md",
            "workspace": str(root),
            "execution_mode": "sequential",
            "jobs": [{
                "id": job["id"],
                "title": job["title"],
                "goal": f"Complete {job['id']} without broadening its scope.",
                "completion_conditions": [f"{job['id']} is complete."],
                "parent_job_id": job["parent_job_id"],
                "report_required": job["report_required"],
            } for job in jobs],
        }), encoding="utf-8")
        (root / "request.md").write_text("Resolve the policy question.\n", encoding="utf-8")
        for job in jobs:
            write_v4_document(
                root / "jobs" / job["id"] / "job.json", "job", job
            )
            (root / job["prompt_path"]).write_text(
                f"Complete {job['id']}.\n", encoding="utf-8"
            )
            (root / job["report_path"]).write_text("", encoding="utf-8")
        (root / "jobs" / "index.json").write_text(
            json.dumps({"jobs": [job["id"] for job in jobs]}), encoding="utf-8"
        )

    def run_jobctl(self, *arguments: object) -> dict:
        process = subprocess.run(
            [sys.executable, str(JOBCTL), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
        return json.loads(process.stdout)

    def snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and "lock" not in path.name
        }

    def test_keep_waiting_is_explicit_and_does_not_mutate_failed_or_canceled_state(self) -> None:
        for advisory_status in ("failed", "canceled"):
            with self.subTest(advisory_status=advisory_status):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / "run"
                    self.write_run(root, advisory_status=advisory_status)
                    before = self.snapshot(root)

                    next_operation = self.run_jobctl("next", "--run", root)
                    decision = self.run_jobctl(
                        "advisory-decision",
                        "--run", root,
                        "--origin", "J001",
                        "--advisory", "J002",
                        "--decision", "keep_waiting",
                    )

                    self.assertEqual(next_operation["operation"], "wait")
                    self.assertEqual(
                        next_operation["reason"], "advisory_decision_required"
                    )
                    self.assertEqual(next_operation["advisory_jobs"], [{
                        "job_id": "J002",
                        "status": advisory_status,
                    }])
                    self.assertEqual(next_operation["allowed_decisions"], [
                        "keep_waiting", "ask_user", "select_another", "fail_origin",
                    ])
                    self.assertFalse(decision["recorded"])
                    self.assertEqual(decision["status"], "waiting_for_job")
                    self.assertEqual(self.snapshot(root), before)

    def test_ask_user_transitions_origin_without_inferring_an_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_run(root)

            result = self.run_jobctl(
                "advisory-decision",
                "--run", root,
                "--origin", "J001",
                "--advisory", "J002",
                "--decision", "ask_user",
            )

            origin = load_v4_state(root)["jobs"]["J001"]
            self.assertEqual(result["status"], "waiting_for_input")
            self.assertEqual(origin["waiting_on"], [])
            self.assertEqual(origin["outcome"]["status"], "needs_input")
            self.assertIn("Advisory job J002 failed", origin["pending_question"]["context"])
            next_operation = self.run_jobctl("next", "--run", root)
            self.assertEqual(next_operation["operation"], "ask_user")
            self.assertEqual(next_operation["job_id"], "J001")

    def test_select_another_replaces_only_the_failed_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_run(root, with_replacement=True)

            result = self.run_jobctl(
                "advisory-decision",
                "--run", root,
                "--origin", "J001",
                "--advisory", "J002",
                "--decision", "select_another",
                "--replacement", "J003",
            )

            origin = load_v4_state(root)["jobs"]["J001"]
            self.assertEqual(result["replacement_job_id"], "J003")
            self.assertEqual(origin["status"], "waiting_for_job")
            self.assertEqual(origin["waiting_on"], ["J003"])
            next_operation = self.run_jobctl("next", "--run", root)
            self.assertEqual(next_operation["operation"], "start_job")
            self.assertEqual(next_operation["job_id"], "J003")

    def test_fail_origin_requires_and_records_the_explicit_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_run(root)

            result = self.run_jobctl(
                "advisory-decision",
                "--run", root,
                "--origin", "J001",
                "--advisory", "J002",
                "--decision", "fail_origin",
                "--reason", "No safe implementation decision is available.",
            )

            state = load_v4_state(root)
            origin = state["jobs"]["J001"]
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["run_status"], "failed")
            self.assertEqual(origin["waiting_on"], [])
            self.assertIsNone(origin["pending_question"])
            self.assertEqual(origin["outcome"], {
                "status": "failed",
                "summary": "No safe implementation decision is available.",
                "context": (
                    "Origin failed by explicit decision after advisory job J002 failed."
                ),
            })
            self.assertEqual(state["run"]["status"], "failed")
            self.assertEqual(
                self.run_jobctl("next", "--run", root),
                {"operation": "run_complete"},
            )


if __name__ == "__main__":
    unittest.main()
