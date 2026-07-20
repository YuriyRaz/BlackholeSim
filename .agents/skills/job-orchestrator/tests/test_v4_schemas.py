from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    JOB_STATUSES,
    JOB_STATUS_TRANSITIONS,
    OrchestratorError,
    SCHEMA_REGISTRY,
    load_schema,
    validate_job_transition,
    validate_record,
)


NOW = "2026-07-14T12:00:00Z"


class Version4SchemaTest(unittest.TestCase):
    def outcome(self) -> dict:
        return {"status": "completed", "summary": "Job complete."}

    def job(self) -> dict:
        return {
            "schema_version": 4,
            "id": "J001",
            "title": "Apply the change",
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
            "report_required": True,
            "report_path": "jobs/J001/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def evidence(self) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "session-42",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "returned",
                "transcript_ref": "transport://session-42",
                "transcript_content": "Authoritative transport transcript.",
                "response": self.outcome(),
            },
            "external_system": [{
                "system": "release-service",
                "observation": "direct",
                "effect_state": "confirmed",
                "summary": "Release 2.4.0 exists.",
                "reference": "release://2.4.0",
            }],
            "recovery_check": {
                "check": "Query whether release 2.4.0 exists.",
                "result": "positive",
                "summary": "The configured check found the release.",
                "reference": "release://2.4.0",
            },
            "workspace": {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "Requested files are present.",
            },
            "report": {
                "observation": "direct",
                "path": "jobs/J001/report.md",
            },
            "checkpoint": None,
            "facts": [
                {
                    "source": "transport_response",
                    "subject": "job.outcome",
                    "value": "completed",
                },
                {
                    "source": "external_system",
                    "subject": "release:2.4.0",
                    "value": "present",
                    "summary": "The release exists in the provider.",
                },
                {
                    "source": "repository_filesystem",
                    "subject": "artifact:manifest",
                    "value": "present",
                },
                {
                    "source": "report",
                    "subject": "artifact:manifest",
                    "value": "present",
                },
            ],
            "recovery_findings": ["The workspace is safe to inspect."],
        }

    def test_v4_schema_kinds_are_registered_and_loadable(self) -> None:
        expected = {
            "job", "job-definition", "outcome", "pending-question",
            "recovery-evidence", "recovery-policy", "run", "setup",
        }
        self.assertEqual(SCHEMA_REGISTRY[4], expected)
        for kind in expected:
            with self.subTest(kind=kind):
                self.assertEqual(load_schema(kind, 4)["type"], "object")

    def test_valid_v4_records_and_components(self) -> None:
        records = {
            "run": {
                "schema_version": 4,
                "protocol_version": 4,
                "run_id": "RUN-1",
                "goal": "Complete the request",
                "status": "active",
                "job_ids": ["J001"],
                "created_at": NOW,
                "updated_at": NOW,
                "revision": 1,
            },
            "setup": {
                "schema_version": 4,
                "request_path": "request.md",
                "workspace": "C:/workspace",
                "execution_mode": "sequential",
                "jobs": [],
            },
            "job-definition": {
                "schema_version": 4,
                "jobs": [{
                    "id": "J001",
                    "title": "Apply the change",
                    "goal": "Implement the requested behavior",
                    "workflow": "Implement, verify, and report.",
                    "requirements": ["Keep the change scoped."],
                    "constraints": ["Do not publish."],
                    "completion_conditions": ["Focused tests pass."],
                    "context": ["Use the current workspace."],
                    "escalation": "Return needs_input for blocking decisions.",
                    "report_required": True,
                    "priority": 10,
                    "depends_on": [],
                    "parent_job_id": None,
                    "related_reports": [],
                    "recovery_policy": {
                        "effect": "external_non_idempotent",
                        "check": "Query whether the release exists.",
                        "idempotency_key": "release-2.4.0",
                    },
                }],
            },
            "job": self.job(),
            "recovery-evidence": self.evidence(),
            "pending-question": {
                "text": "Which compatibility policy should be used?",
                "context": "Two valid policies remain.",
            },
            "outcome": self.outcome(),
            "recovery-policy": {
                "effect": "external_non_idempotent",
                "check": "Query whether release 2.4.0 exists.",
            },
        }
        for kind, record in records.items():
            with self.subTest(kind=kind):
                validate_record(kind, record)

    def test_every_v4_schema_rejects_unknown_fields(self) -> None:
        records = {
            "run": {
                "schema_version": 4, "protocol_version": 4,
                "run_id": "RUN-1", "goal": "Goal", "status": "active",
                "job_ids": [], "created_at": NOW, "updated_at": NOW,
                "revision": 1,
            },
            "setup": {
                "schema_version": 4, "request_path": "request.md",
                "workspace": "C:/workspace", "execution_mode": "sequential",
                "jobs": [],
            },
            "job-definition": {
                "schema_version": 4,
                "jobs": [{
                    "id": "J001", "title": "Title", "goal": "Goal",
                    "completion_conditions": ["Done"],
                    "report_required": False,
                }],
            },
            "job": self.job(),
            "pending-question": {"text": "What value is required?"},
            "outcome": self.outcome(),
            "recovery-policy": {
                "effect": "repository", "check": "Inspect repository state.",
            },
            "recovery-evidence": {
                "schema_version": 4, "job_id": "J001", "observed_at": NOW,
            },
        }
        for kind, record in records.items():
            malformed = {**record, "unexpected": True}
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                    validate_record(kind, malformed)

    def test_nested_job_fields_are_strict(self) -> None:
        for field, value in (
            ("pending_question", {"text": "Choose one", "unexpected": True}),
            ("outcome", {
                **self.outcome(),
                "report_path": "jobs/J001/report.md",
                "unexpected": True,
            }),
            ("recovery_policy", {
                "effect": "repository",
                "check": "Inspect repository state.",
                "unexpected": True,
            }),
        ):
            malformed = self.job()
            malformed[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                    validate_record("job", malformed)

    def test_nested_definition_and_evidence_are_strict(self) -> None:
        definition = {
            "schema_version": 4,
            "jobs": [{
                "id": "J001", "title": "Title", "goal": "Goal",
                "completion_conditions": ["Done"],
                "report_required": False,
                "unexpected": True,
            }],
        }
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("job-definition", definition)

        malformed = copy.deepcopy(self.evidence())
        malformed["transport"]["response"]["unexpected"] = True
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("recovery-evidence", malformed)

        malformed = copy.deepcopy(self.evidence())
        malformed["recovery_check"]["unexpected"] = True
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("recovery-evidence", malformed)

    def test_recovery_check_result_explicitly_supports_undecidable_query(self) -> None:
        for result in ("positive", "negative", "unknown"):
            evidence = self.evidence()
            evidence["recovery_check"]["result"] = result
            validate_record("recovery-evidence", evidence)

        evidence = self.evidence()
        del evidence["recovery_check"]["result"]
        with self.assertRaisesRegex(OrchestratorError, "result"):
            validate_record("recovery-evidence", evidence)

        evidence = self.evidence()
        evidence["recovery_check"]["result"] = "ambiguous"
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("recovery-evidence", evidence)

    def test_outcome_schema_does_not_accept_control_plane_statuses(self) -> None:
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record(
                "outcome",
                {"status": "recovering", "summary": "Transport was lost."},
            )

    def test_outcome_status_conditional_requirements(self) -> None:
        valid = (
            {"status": "completed", "summary": "Job complete."},
            {
                "status": "needs_input",
                "summary": "Work is blocked on a policy decision.",
                "context": "Two compatible policies remain.",
                "question": "Which compatibility policy should be used?",
            },
            {"status": "failed", "summary": "The required tool is unavailable."},
        )
        for outcome in valid:
            with self.subTest(status=outcome["status"]):
                validate_record("outcome", outcome)

        invalid = (
            ({"status": "completed"}, "summary"),
            ({"status": "completed", "summary": ""}, "summary"),
            (
                {"status": "needs_input", "summary": "A decision is required."},
                "question",
            ),
            (
                {
                    "status": "needs_input",
                    "summary": "A decision is required.",
                    "question": "",
                },
                "question",
            ),
            ({"status": "failed"}, "summary"),
            ({"status": "failed", "summary": ""}, "summary"),
        )
        for outcome, missing_field in invalid:
            with self.subTest(status=outcome["status"]):
                with self.assertRaisesRegex(OrchestratorError, missing_field):
                    validate_record("outcome", outcome)

    def test_completed_outcome_requires_report_only_when_job_requires_it(self) -> None:
        job = self.job()
        job["status"] = "completed"
        job["outcome"] = self.outcome()
        with self.assertRaisesRegex(OrchestratorError, "report_path"):
            validate_record("job", job)

        job["outcome"]["report_path"] = job["report_path"]
        validate_record("job", job)

        job["report_required"] = False
        job["outcome"] = self.outcome()
        validate_record("job", job)

    def test_noncompleted_outcomes_do_not_require_a_report(self) -> None:
        job = self.job()
        job["status"] = "waiting_for_input"
        job["outcome"] = {
            "status": "needs_input",
            "summary": "Work is blocked on a policy decision.",
            "question": "Which compatibility policy should be used?",
        }
        validate_record("job", job)

        job["status"] = "failed"
        job["outcome"] = {
            "status": "failed",
            "summary": "The required tool is unavailable.",
        }
        validate_record("job", job)

    def test_recovery_response_uses_outcome_question_requirement(self) -> None:
        evidence = self.evidence()
        evidence["transport"]["response"] = {
            "status": "needs_input",
            "summary": "A decision is required.",
        }
        with self.assertRaisesRegex(OrchestratorError, "question"):
            validate_record("recovery-evidence", evidence)

    def test_recovery_fact_claims_are_strict(self) -> None:
        evidence = self.evidence()
        evidence["facts"][0]["unexpected"] = True
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("recovery-evidence", evidence)

        evidence = self.evidence()
        evidence["facts"][0]["source"] = "persisted_job_status"
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("recovery-evidence", evidence)

    def test_job_statuses_match_the_v4_schema_and_transition_table(self) -> None:
        expected = {
            "queued", "starting", "running", "waiting_for_input",
            "waiting_for_job", "recovering", "completed", "failed", "canceled",
        }
        status_schema = load_schema("job", 4)["properties"]["status"]
        self.assertEqual(JOB_STATUSES, expected)
        self.assertEqual(set(JOB_STATUS_TRANSITIONS), expected)
        self.assertEqual(set(status_schema["enum"]), expected)

    def test_job_transition_validation_uses_explicit_table(self) -> None:
        for current, next_status in (
            ("queued", "starting"),
            ("running", "failed"),
            ("waiting_for_input", "waiting_for_job"),
            ("waiting_for_job", "running"),
            ("recovering", "completed"),
            ("queued", "canceled"),
        ):
            with self.subTest(current=current, next_status=next_status):
                self.assertIn(next_status, JOB_STATUS_TRANSITIONS[current])
                validate_job_transition(current, next_status)

        for current, next_status in (
            ("queued", "completed"),
            ("completed", "running"),
            ("running", "unknown"),
        ):
            with self.subTest(current=current, next_status=next_status):
                with self.assertRaises(OrchestratorError):
                    validate_job_transition(current, next_status)


if __name__ == "__main__":
    unittest.main()
