from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from jobctl import parser, record_outcome  # noqa: E402
from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    load_json,
    load_v4_state,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4OutcomeRecordingTest(unittest.TestCase):
    def job_document(self, *, report_required: bool = False) -> dict:
        return {
            "schema_version": 4,
            "id": "J001",
            "title": "Record a worker outcome",
            "status": "queued",
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": 1,
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": report_required,
            "report_path": "jobs/J001/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def write_state(self, root: Path, *, report_required: bool = False) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-OUTCOME",
            "goal": "Record worker outcomes",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        job = self.job_document(report_required=report_required)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / job["prompt_path"]).write_text("Complete the job.\n", encoding="utf-8")
        (root / job["report_path"]).write_text("", encoding="utf-8")

    def add_dependent(self, root: Path) -> None:
        run_path = root / "run.json"
        run = load_json(run_path)
        run["job_ids"].append("J002")
        write_v4_document(run_path, "run", run)
        dependent = self.job_document()
        dependent.update({
            "id": "J002",
            "title": "Run after J001",
            "prompt_path": "jobs/J002/prompt.md",
            "creation_sequence": 2,
            "depends_on": ["J001"],
            "report_path": "jobs/J002/report.md",
        })
        write_v4_document(root / "jobs" / "J002" / "job.json", "job", dependent)
        (root / dependent["prompt_path"]).write_text(
            "Continue after J001.\n", encoding="utf-8"
        )
        (root / dependent["report_path"]).write_text("", encoding="utf-8")

    def invoke(
        self,
        root: Path,
        document: dict,
        *,
        session_ref: str | None,
        evidence: dict | None = None,
    ) -> dict:
        outcome_path = root.parent / f"{document.get('status', 'invalid')}.json"
        outcome_path.write_text(json.dumps(document), encoding="utf-8")
        arguments = [
            "outcome",
            "--run",
            str(root),
            "--job",
            "J001",
            "--outcome",
            str(outcome_path),
        ]
        if session_ref is not None:
            arguments.extend(["--session-ref", session_ref])
        if evidence is not None:
            evidence_path = root.parent / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments.extend(["--evidence", str(evidence_path)])
        return record_outcome(parser().parse_args(arguments))

    def set_recovering_question(
        self, root: Path, *, waiting_on: list[str] | None = None
    ) -> None:
        path = root / "jobs" / "J001" / "job.json"
        job = load_json(path)
        question = "Which policy should be used?"
        job.update({
            "status": "recovering",
            "session_ref": "transport-session-1",
            "waiting_on": waiting_on or [],
            "pending_question": {"text": question},
            "outcome": {
                "status": "needs_input",
                "summary": "A policy decision is required.",
                "question": question,
            },
        })
        write_json(path, job)

    def test_records_and_normalizes_all_three_worker_outcomes(self) -> None:
        cases = (
            (
                {"status": "completed", "summary": "  Job complete.  "},
                "completed",
            ),
            (
                {
                    "status": "needs_input",
                    "summary": "  A policy decision is required.  ",
                    "question": "  Which policy should be used?  ",
                },
                "waiting_for_input",
            ),
            (
                {"status": "failed", "summary": "  The required tool failed.  "},
                "failed",
            ),
        )
        for document, expected_status in cases:
            with self.subTest(outcome=document["status"]), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                self.write_state(root)

                result = self.invoke(root, document, session_ref="transport-session-1")
                recorded = load_v4_state(root)["jobs"]["J001"]

                self.assertTrue(result["recorded"])
                self.assertEqual(recorded["status"], expected_status)
                self.assertEqual(recorded["session_ref"], "transport-session-1")
                self.assertEqual(recorded["revision"], 2)
                self.assertEqual(recorded["outcome"]["summary"], document["summary"].strip())
                if document["status"] == "needs_input":
                    self.assertEqual(
                        recorded["pending_question"],
                        {
                            "text": "Which policy should be used?",
                            "context": "A policy decision is required.",
                        },
                    )
                    self.assertEqual(
                        recorded["outcome"]["question"],
                        "Which policy should be used?",
                    )
                else:
                    self.assertIsNone(recorded["pending_question"])

    def test_needs_input_preserves_precise_question_and_available_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            report_path = root / "jobs" / "J001" / "report.md"
            report_path.write_text("Parser complete; policy choice remains.\n", encoding="utf-8")

            result = self.invoke(
                root,
                {
                    "status": "needs_input",
                    "summary": "  Parser and focused tests are complete.  ",
                    "context": "  Both policies are valid; user authority is required.  ",
                    "question": "  Should generated files use strict or permissive mode?  ",
                    "report_path": "jobs/J001/report.md",
                },
                session_ref="transport-session-1",
            )
            state = load_v4_state(root)
            recorded = state["jobs"]["J001"]

            self.assertEqual(result["status"], "waiting_for_input")
            self.assertEqual(result["run_status"], "active")
            self.assertEqual(recorded["status"], "waiting_for_input")
            self.assertNotEqual(recorded["status"], "failed")
            self.assertEqual(
                recorded["pending_question"],
                {
                    "text": "Should generated files use strict or permissive mode?",
                    "context": "Both policies are valid; user authority is required.",
                },
            )
            self.assertEqual(
                recorded["outcome"],
                {
                    "status": "needs_input",
                    "summary": "Parser and focused tests are complete.",
                    "context": "Both policies are valid; user authority is required.",
                    "question": "Should generated files use strict or permissive mode?",
                    "report_path": "jobs/J001/report.md",
                },
            )
            self.assertEqual(
                report_path.read_text(encoding="utf-8"),
                "Parser complete; policy choice remains.\n",
            )

    def test_identical_repeat_is_noop_and_conflicting_outcome_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            completed = {"status": "completed", "summary": "Job complete."}
            self.invoke(root, completed, session_ref="transport-session-1")
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            repeated = self.invoke(root, completed, session_ref=None)
            self.assertFalse(repeated["recorded"])
            self.assertEqual(job_path.read_bytes(), before)

            with self.assertRaisesRegex(OrchestratorError, "different worker outcome"):
                self.invoke(
                    root,
                    {"status": "completed", "summary": "A different claim."},
                    session_ref=None,
                )
            self.assertEqual(job_path.read_bytes(), before)

    def test_completion_immediately_makes_satisfied_dependent_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            self.add_dependent(root)

            result = self.invoke(
                root,
                {"status": "completed", "summary": "Job complete."},
                session_ref="transport-session-1",
            )

            self.assertEqual(result["ready_job_ids"], ["J002"])
            self.assertEqual(load_v4_state(root)["ready_job_ids"], ["J002"])

    def test_non_success_worker_outcomes_do_not_unlock_dependent(self) -> None:
        outcomes = (
            {
                "status": "needs_input",
                "summary": "A decision is required.",
                "question": "Which policy should be used?",
            },
            {"status": "failed", "summary": "The job could not complete."},
        )
        for outcome in outcomes:
            with self.subTest(status=outcome["status"]), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                self.write_state(root)
                self.add_dependent(root)

                result = self.invoke(
                    root, outcome, session_ref="transport-session-1"
                )

                self.assertEqual(result["ready_job_ids"], [])
                self.assertNotIn("J002", load_v4_state(root)["ready_job_ids"])

    def test_rejects_deprecated_and_readiness_fields_without_mutating_state(self) -> None:
        forbidden = (
            "protocol_hash",
            "protocol_sha256",
            "contract_revision",
            "nonce",
            "dispatch_id",
            "work_units",
            "completed_work_units",
            "ready_for_next_step",
        )
        for field in forbidden:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "run"
                self.write_state(root)
                job_path = root / "jobs" / "J001" / "job.json"
                before = job_path.read_bytes()
                value = [] if "work_units" in field else True
                document = {
                    "status": "completed",
                    "summary": "Job complete.",
                    field: value,
                }

                with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                    self.invoke(root, document, session_ref="transport-session-1")
                self.assertEqual(job_path.read_bytes(), before)

    def test_invalid_required_report_does_not_partially_record_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report_required=True)
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            with self.assertRaisesRegex(OrchestratorError, "accessible non-empty report"):
                self.invoke(
                    root,
                    {
                        "status": "completed",
                        "summary": "Job complete.",
                        "report_path": "jobs/J001/report.md",
                    },
                    session_ref="transport-session-1",
                )

            self.assertEqual(job_path.read_bytes(), before)
            recorded = load_v4_state(root)["jobs"]["J001"]
            self.assertIsNone(recorded["session_ref"])
            self.assertIsNone(recorded["outcome"])

    def test_rejects_incoherent_completed_outcome_without_mutating_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            with self.assertRaisesRegex(OrchestratorError, "must not contain a question"):
                self.invoke(
                    root,
                    {
                        "status": "completed",
                        "summary": "Job complete.",
                        "question": "Is anything else required?",
                    },
                    session_ref="transport-session-1",
                )

            self.assertEqual(job_path.read_bytes(), before)

    def test_rejects_completion_while_a_question_remains_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            self.set_recovering_question(root)
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            with self.assertRaisesRegex(OrchestratorError, "no pending question"):
                self.invoke(
                    root,
                    {"status": "completed", "summary": "Job complete."},
                    session_ref=None,
                )

            self.assertEqual(job_path.read_bytes(), before)

    def test_rejects_completion_while_a_required_related_job_is_nonterminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            run_path = root / "run.json"
            run = load_json(run_path)
            run["job_ids"].append("J002")
            write_v4_document(run_path, "run", run)
            related = self.job_document()
            related.update({
                "id": "J002",
                "title": "Required consultation",
                "prompt_path": "jobs/J002/prompt.md",
                "creation_sequence": 2,
                "report_path": "jobs/J002/report.md",
            })
            write_v4_document(root / "jobs" / "J002" / "job.json", "job", related)
            self.set_recovering_question(root, waiting_on=["J002"])
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            with self.assertRaisesRegex(OrchestratorError, "terminal related jobs: J002"):
                self.invoke(
                    root,
                    {"status": "completed", "summary": "Job complete."},
                    session_ref=None,
                )

            self.assertEqual(job_path.read_bytes(), before)

    def test_transport_evidence_must_not_show_an_active_turn(self) -> None:
        def evidence(status: str) -> dict:
            return {
                "schema_version": 4,
                "job_id": "J001",
                "session_ref": "transport-session-1",
                "observed_at": NOW,
                "transport": {
                    "observation": "direct",
                    "status": status,
                },
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "active" / "run"
            self.write_state(root)
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()

            with self.assertRaisesRegex(OrchestratorError, "active turn"):
                self.invoke(
                    root,
                    {"status": "completed", "summary": "Job complete."},
                    session_ref="transport-session-1",
                    evidence=evidence("active"),
                )
            self.assertEqual(job_path.read_bytes(), before)

            returned_root = Path(temporary) / "returned" / "run"
            self.write_state(returned_root)
            result = self.invoke(
                returned_root,
                {"status": "completed", "summary": "Job complete."},
                session_ref="transport-session-1",
                evidence=evidence("returned"),
            )
            self.assertTrue(result["recorded"])
            self.assertEqual(result["status"], "completed")

    def test_transport_evidence_is_validated_for_every_outcome_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            job_path = root / "jobs" / "J001" / "job.json"
            before = job_path.read_bytes()
            malformed_evidence = {
                "schema_version": 4,
                "job_id": "J001",
                "session_ref": "transport-session-1",
                "observed_at": NOW,
                "transport": {
                    "observation": "unknown",
                    "status": "lost",
                },
            }

            with self.assertRaisesRegex(
                OrchestratorError, "must use status 'unknown'"
            ):
                self.invoke(
                    root,
                    {
                        "status": "needs_input",
                        "summary": "A decision is required.",
                        "question": "Which option should be used?",
                    },
                    session_ref="transport-session-1",
                    evidence=malformed_evidence,
                )

            self.assertEqual(job_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
