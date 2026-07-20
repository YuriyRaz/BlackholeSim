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
    OrchestratorError,
    load_v4_state,
    record_v4_answer,
    select_v4_next_operation,
    write_v4_document,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"
NOW = "2026-07-14T12:00:00Z"


class Version4AnswerRecordingTest(unittest.TestCase):
    def write_state(self, root: Path, *, status: str = "waiting_for_input") -> Path:
        root.mkdir(parents=True)
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-ANSWER",
            "goal": "Continue a conversational job",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        question = "Should generated files use strict or permissive mode?"
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Apply the selected policy",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": "transport-session-1",
            "priority": 10,
            "creation_sequence": 1,
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "answers": [],
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
                "text": question,
                "context": "Both modes are technically valid.",
            }
            job["outcome"] = {
                "status": "needs_input",
                "summary": "A policy decision is required.",
                "question": question,
        }
        write_v4_document(root / "run.json", "run", run)
        (root / "setup.json").write_text(json.dumps({
            "schema_version": 4,
            "request_path": "request.md",
            "workspace": str(root),
            "execution_mode": "sequential",
            "jobs": [{
                "id": "J001",
                "title": job["title"],
                "goal": "Apply the selected policy without changing the job scope.",
                "completion_conditions": ["The selected policy is applied."],
                "report_required": False,
            }],
        }), encoding="utf-8")
        path = root / "jobs" / "J001" / "job.json"
        write_v4_document(path, "job", job)
        (root / job["prompt_path"]).write_text(
            "Original complete prompt that must not be redefined.\n", encoding="utf-8"
        )
        (root / job["report_path"]).write_text("", encoding="utf-8")
        return path

    def test_authoritative_answer_atomically_returns_focused_same_session_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            path = self.write_state(root)
            before = load_v4_state(root)["jobs"]["J001"]

            result = record_v4_answer(
                root,
                "J001",
                "  Use strict mode.  ",
                source="authoritative",
                controller="answer-test",
            )
            recorded = load_v4_state(root)["jobs"]["J001"]

            self.assertEqual(result["operation"], "resume_job")
            self.assertEqual(result["session_ref"], before["session_ref"])
            self.assertEqual(result["status"], "running")
            self.assertTrue(result["recorded"])
            self.assertEqual(recorded["status"], "running")
            self.assertEqual(recorded["session_ref"], before["session_ref"])
            self.assertIsNone(recorded["pending_question"])
            self.assertIsNone(recorded["outcome"])
            self.assertEqual(recorded["revision"], before["revision"] + 1)
            self.assertEqual(recorded["answers"], [result["answer"]])
            self.assertEqual(result["answer"]["source"], "authoritative")
            self.assertEqual(result["answer"]["text"], "Use strict mode.")
            self.assertIn(before["pending_question"]["text"], result["prompt"])
            self.assertIn(
                "## Original Job Goal\n"
                "Apply the selected policy without changing the job scope.",
                result["prompt"],
            )
            self.assertIn("## Authoritative Answer\nUse strict mode.", result["prompt"])
            self.assertIn("Continue the original job in this same session", result["prompt"])
            self.assertIn("Do not begin unrelated work.", result["prompt"])
            self.assertNotIn("Original complete prompt", result["prompt"])
            self.assertEqual(
                select_v4_next_operation(load_v4_state(root), run_root=root),
                {"operation": "wait"},
            )
            self.assertTrue(path.is_file())

    def test_user_answer_cli_emits_one_resume_payload_and_records_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)

            process = subprocess.run(
                [
                    sys.executable,
                    str(JOBCTL),
                    "answer",
                    "--run",
                    str(root),
                    "--job",
                    "J001",
                    "--answer",
                    "Use permissive mode for this run.",
                    "--source",
                    "user",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            result = json.loads(process.stdout)
            self.assertEqual(result["operation"], "resume_job")
            self.assertEqual(result["session_ref"], "transport-session-1")
            self.assertEqual(result["answer"]["source"], "user")
            self.assertIn(
                "## User Answer\nUse permissive mode for this run.", result["prompt"]
            )
            recorded = load_v4_state(root)["jobs"]["J001"]
            self.assertEqual(recorded["answers"], [result["answer"]])

    def test_invalid_or_inapplicable_answer_does_not_mutate_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            path = self.write_state(root)
            before = path.read_bytes()

            for answer, source, message in (
                ("   ", "user", "non-empty"),
                ("Use strict mode.", "worker", "answer source"),
            ):
                with self.subTest(answer=answer, source=source):
                    with self.assertRaisesRegex(OrchestratorError, message):
                        record_v4_answer(
                            root,
                            "J001",
                            answer,
                            source=source,
                            controller="answer-test",
                        )
                    self.assertEqual(path.read_bytes(), before)

            running_root = Path(temporary) / "running"
            running_path = self.write_state(running_root, status="running")
            running_before = running_path.read_bytes()
            with self.assertRaisesRegex(OrchestratorError, "cannot accept an answer"):
                record_v4_answer(
                    running_root,
                    "J001",
                    "Use strict mode.",
                    source="authoritative",
                    controller="answer-test",
                )
            self.assertEqual(running_path.read_bytes(), running_before)


if __name__ == "__main__":
    unittest.main()
