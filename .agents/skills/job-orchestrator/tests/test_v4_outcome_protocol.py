from __future__ import annotations

import json
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
    normalize_v4_outcome,
    validate_record,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class OutcomeProtocolVerificationTest(unittest.TestCase):
    def _job_document(self, *, report_required: bool = False) -> dict:
        return {
            "schema_version": 4,
            "id": "J001",
            "title": "Test job",
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

    def _write_state(
        self, root: Path, *, report_required: bool = False
    ) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-OUTCOME-PROTOCOL",
            "goal": "Test outcome protocol",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        job = self._job_document(report_required=report_required)
        write_v4_document(
            root / "jobs" / "J001" / "job.json", "job", job
        )
        (root / job["prompt_path"]).write_text("Complete the job.\n", encoding="utf-8")
        (root / job["report_path"]).write_text("Report content.\n", encoding="utf-8")

    def test_completed_outcome_schema_requires_status_and_summary(self) -> None:
        valid = {"status": "completed", "summary": "Job complete."}
        validate_record("outcome", valid)

        missing_summary = {"status": "completed"}
        with self.assertRaisesRegex(OrchestratorError, "summary"):
            validate_record("outcome", missing_summary)

        empty_summary = {"status": "completed", "summary": ""}
        with self.assertRaisesRegex(OrchestratorError, "summary"):
            validate_record("outcome", empty_summary)

    def test_completed_outcome_allows_question_field_at_schema_level(self) -> None:
        with_question = {
            "status": "completed",
            "summary": "Job complete.",
            "question": "Is anything else required?",
        }
        validate_record("outcome", with_question)

    def test_completed_outcome_allows_optional_report_path(self) -> None:
        with_report = {
            "status": "completed",
            "summary": "Job complete.",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("outcome", with_report)

        without_report = {"status": "completed", "summary": "Job complete."}
        validate_record("outcome", without_report)

    def test_completed_outcome_allows_optional_context(self) -> None:
        with_context = {
            "status": "completed",
            "summary": "Job complete.",
            "context": "Additional context.",
        }
        validate_record("outcome", with_context)

    def test_needs_input_outcome_schema_requires_status_summary_and_question(
        self,
    ) -> None:
        valid = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy should be used?",
        }
        validate_record("outcome", valid)

        missing_question = {
            "status": "needs_input",
            "summary": "A decision is required.",
        }
        with self.assertRaisesRegex(OrchestratorError, "question"):
            validate_record("outcome", missing_question)

        empty_question = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "",
        }
        with self.assertRaisesRegex(OrchestratorError, "question"):
            validate_record("outcome", empty_question)

    def test_needs_input_outcome_allows_report_path_at_schema_level(self) -> None:
        with_report = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy?",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("outcome", with_report)

    def test_needs_input_outcome_allows_optional_context(self) -> None:
        with_context = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy?",
            "context": "Both policies are valid.",
        }
        validate_record("outcome", with_context)

    def test_failed_outcome_schema_requires_status_and_summary(self) -> None:
        valid = {"status": "failed", "summary": "The required tool failed."}
        validate_record("outcome", valid)

        missing_summary = {"status": "failed"}
        with self.assertRaisesRegex(OrchestratorError, "summary"):
            validate_record("outcome", missing_summary)

        empty_summary = {"status": "failed", "summary": ""}
        with self.assertRaisesRegex(OrchestratorError, "summary"):
            validate_record("outcome", empty_summary)

    def test_failed_outcome_allows_question_at_schema_level(self) -> None:
        with_question = {
            "status": "failed",
            "summary": "The required tool failed.",
            "question": "What happened?",
        }
        validate_record("outcome", with_question)

    def test_failed_outcome_allows_report_path_at_schema_level(self) -> None:
        with_report = {
            "status": "failed",
            "summary": "The required tool failed.",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("outcome", with_report)

    def test_failed_outcome_allows_optional_context(self) -> None:
        with_context = {
            "status": "failed",
            "summary": "The required tool failed.",
            "context": "Tool timeout after 30 seconds.",
        }
        validate_record("outcome", with_context)

    def test_rejects_invalid_status_value(self) -> None:
        invalid = {"status": "running", "summary": "Job is running."}
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("outcome", invalid)

        invalid = {"status": "canceled", "summary": "Job was canceled."}
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("outcome", invalid)

        invalid = {"status": "queued", "summary": "Job is queued."}
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("outcome", invalid)

    def test_rejects_empty_status(self) -> None:
        invalid = {"status": "", "summary": "Job complete."}
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("outcome", invalid)

    def test_rejects_missing_status(self) -> None:
        invalid = {"summary": "Job complete."}
        with self.assertRaisesRegex(OrchestratorError, "status"):
            validate_record("outcome", invalid)

    def test_rejects_additional_properties(self) -> None:
        cases = (
            {"status": "completed", "summary": "Done.", "extra_field": "value"},
            {
                "status": "needs_input",
                "summary": "Decision required.",
                "question": "Which?",
                "extra_field": "value",
            },
            {"status": "failed", "summary": "Failed.", "extra_field": "value"},
        )
        for outcome in cases:
            with self.subTest(status=outcome["status"]):
                with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                    validate_record("outcome", outcome)

    def test_rejects_deprecated_fields(self) -> None:
        deprecated_fields = (
            "protocol_hash",
            "protocol_sha256",
            "contract_revision",
            "nonce",
            "dispatch_id",
            "work_units",
            "completed_work_units",
            "ready_for_next_step",
        )
        for field in deprecated_fields:
            with self.subTest(field=field):
                value = [] if "work_units" in field else True
                invalid = {
                    "status": "completed",
                    "summary": "Done.",
                    field: value,
                }
                with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                    validate_record("outcome", invalid)

    def test_completed_outcome_normalized_text_fields(self) -> None:
        outcome = {
            "status": "completed",
            "summary": "  Job complete.  ",
            "report_path": "  jobs/J001/report.md  ",
        }
        normalized = normalize_v4_outcome(outcome)
        self.assertEqual(normalized["summary"], "Job complete.")
        self.assertEqual(normalized["report_path"], "jobs/J001/report.md")

    def test_needs_input_outcome_normalized_text_fields(self) -> None:
        outcome = {
            "status": "needs_input",
            "summary": "  A decision is required.  ",
            "question": "  Which policy should be used?  ",
            "context": "  Both policies are valid.  ",
        }
        normalized = normalize_v4_outcome(outcome)
        self.assertEqual(normalized["summary"], "A decision is required.")
        self.assertEqual(normalized["question"], "Which policy should be used?")
        self.assertEqual(normalized["context"], "Both policies are valid.")

    def test_failed_outcome_normalized_text_fields(self) -> None:
        outcome = {
            "status": "failed",
            "summary": "  The required tool failed.  ",
            "context": "  Tool timeout.  ",
        }
        normalized = normalize_v4_outcome(outcome)
        self.assertEqual(normalized["summary"], "The required tool failed.")
        self.assertEqual(normalized["context"], "Tool timeout.")

    def test_completed_outcome_rejects_control_plane_statuses(self) -> None:
        for status in ("recovering", "waiting_for_input", "waiting_for_job"):
            with self.subTest(status=status):
                invalid = {"status": status, "summary": "Job complete."}
                with self.assertRaisesRegex(OrchestratorError, "one of"):
                    validate_record("outcome", invalid)

    def test_needs_input_outcome_rejects_control_plane_statuses(self) -> None:
        for status in ("recovering", "running", "queued"):
            with self.subTest(status=status):
                invalid = {
                    "status": status,
                    "summary": "Decision required.",
                    "question": "Which?",
                }
                with self.assertRaisesRegex(OrchestratorError, "one of"):
                    validate_record("outcome", invalid)

    def test_failed_outcome_rejects_control_plane_statuses(self) -> None:
        for status in ("recovering", "running", "queued"):
            with self.subTest(status=status):
                invalid = {"status": status, "summary": "Failed."}
                with self.assertRaisesRegex(OrchestratorError, "one of"):
                    validate_record("outcome", invalid)

    def test_completed_outcome_in_job_with_report_required_needs_report_path(
        self,
    ) -> None:
        job = self._job_document(report_required=True)
        job["status"] = "completed"
        job["outcome"] = {"status": "completed", "summary": "Job complete."}
        with self.assertRaisesRegex(OrchestratorError, "report_path"):
            validate_record("job", job)

        job["outcome"]["report_path"] = job["report_path"]
        validate_record("job", job)

    def test_completed_outcome_in_job_without_report_required_no_report_needed(
        self,
    ) -> None:
        job = self._job_document(report_required=False)
        job["status"] = "completed"
        job["outcome"] = {"status": "completed", "summary": "Job complete."}
        validate_record("job", job)

    def test_needs_input_outcome_in_job_does_not_require_report_path(self) -> None:
        job = self._job_document(report_required=True)
        job["status"] = "waiting_for_input"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy?",
        }
        validate_record("job", job)

    def test_failed_outcome_in_job_does_not_require_report_path(self) -> None:
        job = self._job_document(report_required=True)
        job["status"] = "failed"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "failed",
            "summary": "The required tool failed.",
        }
        validate_record("job", job)

    def test_needs_input_outcome_requires_question_presence_in_job(self) -> None:
        job = self._job_document()
        job["status"] = "waiting_for_input"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "needs_input",
            "summary": "A decision is required.",
        }
        with self.assertRaisesRegex(OrchestratorError, "question"):
            validate_record("job", job)

    def test_outcome_status_enum_is_exactly_three_values(self) -> None:
        for status in ("completed", "needs_input", "failed"):
            if status == "needs_input":
                validate_record(
                    "outcome",
                    {
                        "status": status,
                        "summary": "Test.",
                        "question": "Question?",
                    },
                )
            else:
                validate_record(
                    "outcome", {"status": status, "summary": "Test."}
                )

    def test_needs_input_outcome_context_is_optional(self) -> None:
        without_context = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy?",
        }
        validate_record("outcome", without_context)

    def test_failed_outcome_context_is_optional(self) -> None:
        without_context = {"status": "failed", "summary": "The required tool failed."}
        validate_record("outcome", without_context)

    def test_completed_outcome_report_path_is_optional_when_report_not_required(
        self,
    ) -> None:
        job = self._job_document(report_required=False)
        job["status"] = "completed"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "completed",
            "summary": "Job complete.",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("job", job)

    def test_needs_input_outcome_preserves_question_text(self) -> None:
        outcome = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which compatibility policy should be used?",
            "context": "Two compatible policies remain.",
        }
        normalized = normalize_v4_outcome(outcome)
        self.assertEqual(
            normalized["question"], "Which compatibility policy should be used?"
        )
        self.assertEqual(normalized["context"], "Two compatible policies remain.")

    def test_completed_outcome_minimal_valid(self) -> None:
        minimal = {"status": "completed", "summary": "Done."}
        validate_record("outcome", minimal)
        normalized = normalize_v4_outcome(minimal)
        self.assertEqual(normalized, {"status": "completed", "summary": "Done."})

    def test_failed_outcome_minimal_valid(self) -> None:
        minimal = {"status": "failed", "summary": "Failed."}
        validate_record("outcome", minimal)
        normalized = normalize_v4_outcome(minimal)
        self.assertEqual(normalized, {"status": "failed", "summary": "Failed."})

    def test_needs_input_outcome_minimal_valid(self) -> None:
        minimal = {
            "status": "needs_input",
            "summary": "Decision required.",
            "question": "Which option?",
        }
        validate_record("outcome", minimal)
        normalized = normalize_v4_outcome(minimal)
        self.assertEqual(
            normalized,
            {
                "status": "needs_input",
                "summary": "Decision required.",
                "question": "Which option?",
            },
        )

    def test_needs_input_outcome_report_path_not_required_for_completion(self) -> None:
        job = self._job_document(report_required=True)
        job["status"] = "waiting_for_input"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "needs_input",
            "summary": "A decision is required.",
            "question": "Which policy?",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("job", job)

    def test_failed_outcome_report_path_not_required_for_failure(self) -> None:
        job = self._job_document(report_required=True)
        job["status"] = "failed"
        job["session_ref"] = "transport-session-1"
        job["outcome"] = {
            "status": "failed",
            "summary": "The required tool failed.",
            "report_path": "jobs/J001/report.md",
        }
        validate_record("job", job)

    def test_completed_outcome_report_path_must_match_job_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self._write_state(root, report_required=True)
            job = self._job_document(report_required=True)
            job["status"] = "completed"
            job["session_ref"] = "transport-session-1"
            job["outcome"] = {
                "status": "completed",
                "summary": "Job complete.",
                "report_path": "jobs/J002/report.md",
            }
            with self.assertRaisesRegex(
                OrchestratorError, "outcome report_path must match"
            ):
                write_v4_document(
                    root / "jobs" / "J001" / "job.json", "job", job
                )

    def test_completed_outcome_requires_question_absence_in_job_coherence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self._write_state(root)
            job = self._job_document()
            job["status"] = "running"
            job["session_ref"] = "transport-session-1"
            job["pending_question"] = None
            write_v4_document(
                root / "jobs" / "J001" / "job.json", "job", job,
                transition_path=["starting", "running"],
            )
            job["status"] = "completed"
            job["outcome"] = {
                "status": "completed",
                "summary": "Job complete.",
                "question": "Is this valid?",
            }
            with self.assertRaisesRegex(
                OrchestratorError, "must not contain a question"
            ):
                write_v4_document(
                    root / "jobs" / "J001" / "job.json", "job", job
                )


if __name__ == "__main__":
    unittest.main()
