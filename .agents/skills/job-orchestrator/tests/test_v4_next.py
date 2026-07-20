from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    load_v4_state,
    render_v4_initial_prompt,
    select_v4_next_operation,
    write_v4_document,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"
NOW = "2026-07-14T12:00:00Z"


class Version4NextOperationTest(unittest.TestCase):
    def run_document(self, job_ids: list[str], *, status: str = "active") -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-NEXT",
            "goal": "Select the next operation",
            "status": status,
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
        priority: int = 10,
        creation_sequence: int = 1,
        depends_on: list[str] | None = None,
    ) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": priority,
            "creation_sequence": creation_sequence,
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
        if status in {"running", "waiting_for_input", "waiting_for_job", "completed"}:
            job["session_ref"] = f"session-{job_id}"
        if status in {"waiting_for_input", "waiting_for_job"}:
            question = f"What input does {job_id} require?"
            job["pending_question"] = {
                "text": question,
                "context": "The job cannot continue without it.",
            }
            job["outcome"] = {
                "status": "needs_input",
                "summary": "Input is required.",
                "question": question,
            }
        if status == "completed":
            job["outcome"] = {"status": "completed", "summary": "Complete."}
        if status == "failed":
            job["outcome"] = {"status": "failed", "summary": "Failed."}
        return job

    def write_state(
        self,
        root: Path,
        jobs: list[dict],
        *,
        status: str = "active",
        prompts: dict[str, str] | None = None,
    ) -> None:
        root.mkdir(parents=True)
        write_v4_document(
            root / "run.json",
            "run",
            self.run_document([job["id"] for job in jobs], status=status),
        )
        (root / "setup.json").write_text(json.dumps({
            "schema_version": 4,
            "request_path": "request.md",
            "workspace": str(root),
            "execution_mode": "sequential",
            "jobs": [{
                "id": job["id"],
                "title": job["title"],
                "goal": f"Complete the original goal for {job['id']}.",
                "completion_conditions": [f"{job['id']} is complete."],
                "report_required": job["report_required"],
            } for job in jobs],
        }), encoding="utf-8")
        for job in jobs:
            write_v4_document(root / "jobs" / job["id"] / "job.json", "job", job)
            (root / job["prompt_path"]).write_text(
                (prompts or {}).get(job["id"], "Prompt\n"), encoding="utf-8"
            )
            if job["status"] == "completed":
                (root / job["report_path"]).write_text("Report\n", encoding="utf-8")

    def run_next(self, root: Path) -> dict:
        process = subprocess.run(
            [sys.executable, str(JOBCTL), "next", "--run", str(root)],
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
            if path.is_file()
        }

    def test_cli_selects_each_operation_from_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            start_root = base / "start"
            self.write_state(start_root, [
                self.job_document("J001", priority=20, creation_sequence=2),
                self.job_document("J002", priority=50, creation_sequence=1),
            ])
            self.assertEqual(
                self.run_next(start_root),
                {
                    "operation": "start_job",
                    "job_id": "J002",
                    "title": "Job J002",
                    "prompt": "Prompt\n",
                    "correlation": {
                        "run_id": "RUN-NEXT",
                        "job_id": "J002",
                    },
                },
            )

            ask_root = base / "ask"
            asking = self.job_document("J001", status="waiting_for_input")
            self.write_state(ask_root, [asking])
            self.assertEqual(
                self.run_next(ask_root),
                {
                    "operation": "ask_user",
                    "job_id": "J001",
                    "question": asking["pending_question"],
                },
            )

            resume_root = base / "resume"
            origin = self.job_document("J001", status="waiting_for_job")
            advisory = self.job_document(
                "J002", status="completed", creation_sequence=2
            )
            origin["waiting_on"] = ["J002"]
            origin["related_reports"] = [advisory["report_path"]]
            self.write_state(resume_root, [origin, advisory])
            resumed = self.run_next(resume_root)
            self.assertEqual(resumed["operation"], "resume_job")
            self.assertEqual(resumed["job_id"], "J001")
            self.assertEqual(resumed["session_ref"], "session-J001")
            self.assertIn(
                "## Original Job Goal\nComplete the original goal for J001.",
                resumed["prompt"],
            )
            self.assertIn("- `jobs/J002/report.md`", resumed["prompt"])

            wait_root = base / "wait"
            self.write_state(
                wait_root, [self.job_document("J001", status="running")]
            )
            self.assertEqual(self.run_next(wait_root), {"operation": "wait"})

            complete_root = base / "complete"
            self.write_state(
                complete_root, [self.job_document("J001", status="completed")]
            )
            self.assertEqual(
                self.run_next(complete_root), {"operation": "run_complete"}
            )

    def test_selection_is_pure_and_repeated_cli_calls_do_not_mutate_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, [self.job_document("J001")])
            state = load_v4_state(root)
            original_state = copy.deepcopy(state)

            first_selection = select_v4_next_operation(state, run_root=root)
            second_selection = select_v4_next_operation(state, run_root=root)

            self.assertEqual(first_selection, second_selection)
            self.assertEqual(state, original_state)

            before = self.snapshot(root)
            first_cli = self.run_next(root)
            middle = self.snapshot(root)
            second_cli = self.run_next(root)
            after = self.snapshot(root)

            self.assertEqual(first_cli, second_cli)
            self.assertEqual(before, middle)
            self.assertEqual(middle, after)

    def test_start_job_immediately_returns_complete_prompt_and_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            job = self.job_document("J001")
            job["title"] = "Apply the focused change"
            prompt = render_v4_initial_prompt(
                {
                    "id": "J001",
                    "title": job["title"],
                    "goal": "Implement task 5.2.",
                    "workflow": "Inspect, implement, and run focused tests.",
                    "requirements": ["Return the complete result."],
                    "constraints": ["Do not broaden scope."],
                    "completion_conditions": ["The start payload is complete."],
                    "context": ["Use the persisted job definition."],
                    "escalation": "Return needs_input only for a blocking decision.",
                    "report_required": False,
                    "recovery_policy": {
                        "effect": "repository",
                        "check": "Inspect the workspace before retrying.",
                    },
                },
                workspace="C:/work/repository",
                report_path=job["report_path"],
            )
            self.write_state(root, [job], prompts={"J001": prompt})

            result = self.run_next(root)

            self.assertEqual(result["operation"], "start_job")
            self.assertEqual(result["job_id"], "J001")
            self.assertEqual(result["title"], "Apply the focused change")
            self.assertEqual(
                result["correlation"],
                {"run_id": "RUN-NEXT", "job_id": "J001"},
            )
            self.assertEqual(result["prompt"], prompt)
            for section in (
                "## Worker Contract",
                "## Goal",
                "## Workflow",
                "## Requirements",
                "## Constraints",
                "## Completion Conditions",
                "## Context",
                "## Escalation",
                "## Report Expectation",
                "## Recovery Requirements",
            ):
                self.assertIn(section, result["prompt"])
            self.assertIn("Begin the domain work immediately.", result["prompt"])
            serialized = json.dumps(result).lower()
            self.assertNotIn("bootstrap", serialized)
            self.assertNotIn("acknowledg", serialized)

    def test_incomplete_or_unreported_advisory_work_does_not_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name, advisory_status, include_report in (
                ("running", "running", False),
                ("failed", "failed", False),
                ("unreported", "completed", False),
            ):
                with self.subTest(name=name):
                    root = base / name
                    origin = self.job_document("J001", status="waiting_for_job")
                    advisory = self.job_document(
                        "J002", status=advisory_status, creation_sequence=2
                    )
                    origin["waiting_on"] = ["J002"]
                    if include_report:
                        origin["related_reports"] = [advisory["report_path"]]
                    self.write_state(root, [origin, advisory])

                    self.assertEqual(self.run_next(root)["operation"], "wait")


if __name__ == "__main__":
    unittest.main()
