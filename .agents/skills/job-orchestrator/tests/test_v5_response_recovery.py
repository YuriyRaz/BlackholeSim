"""Response recovery tests: malformed, empty, root-authored rejection, cancellation, replacement history, non-idempotent effects."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError  # noqa: E402
from transport_v5 import FakeTransportAdapter  # noqa: E402
from v5_core import (  # noqa: E402
    V5,
    init_v5_run,
    load_v5_state,
    record_v5_launch_receipt,
    record_v5_response_receipt,
    recover_v5_job,
    register_v5_jobs,
    select_v5_next_operation,
)


NOW = "2026-07-24T12:00:00Z"


def _simple_definition() -> dict:
    return {
        "schema_version": 5,
        "jobs": [{
            "id": "J001",
            "title": "Work",
            "goal": "Do work.",
            "completion_conditions": [{
                "id": "tests",
                "description": "Tests pass",
                "required": True,
                "evidence_required": False,
                "verification": "self",
            }],
            "report_required": True,
            "side_effect_class": "none",
        }],
    }


def _non_idempotent_definition() -> dict:
    return {
        "schema_version": 5,
        "jobs": [{
            "id": "J001",
            "title": "Deploy",
            "goal": "Deploy to production.",
            "completion_conditions": [{
                "id": "deploy",
                "description": "Deployment succeeds",
                "required": True,
                "evidence_required": False,
                "verification": "self",
            }],
            "report_required": True,
            "side_effect_class": "external_non_idempotent",
            "recovery_policy": {"check": "Inspect deployment state."},
        }],
    }


def _make_run(base: Path, run_id: str = "RUN-T", goal: str = "Test goal") -> Path:
    request = base / "request.md"
    request.write_text("Request\n", encoding="utf-8")
    result = init_v5_run(request, goal, run_id=run_id, state_root=base, workspace=base)
    return Path(result["run_root"])


def _launch_job(run: Path, adapter: FakeTransportAdapter, job_id: str = "J001", run_id: str = "RUN-T") -> dict:
    start = select_v5_next_operation(run)
    receipt = adapter.launch_receipt(
        dispatch_id=start["dispatch"]["dispatch_id"],
        native_session_ref="ses-1",
        run_id=run_id,
        job_id=job_id,
        prompt_sha256=start["dispatch"]["prompt_sha256"],
        created_at=NOW,
    )
    return record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)


class MalformedResponseFormatRepairTest(unittest.TestCase):
    """Non-JSON response from a live session creates a resume_job with repair prompt."""

    def test_malformed_json_triggers_format_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            raw = "this is not json at all"
            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)

            self.assertEqual(result["operation"], "resume_job")
            self.assertEqual(result["job_id"], "J001")
            self.assertIn("reason", result)
            self.assertIn("malformed JSON", result["reason"])

    def test_repair_prompt_includes_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            raw = "{not valid json"
            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)

            self.assertIn("reason", result)
            state = load_v5_state(run)
            prompt = (run / state["jobs"]["J001"]["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("malformed JSON", prompt)
            self.assertIn("Transport Response Repair", prompt)


class EmptyResponseRetrievalTest(unittest.TestCase):
    """Empty response with live session creates a resume_job for same-session repair."""

    def test_empty_response_triggers_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response="", received_at=NOW,
                status="empty", session_liveness="live",
            ), controller="test", adapter=adapter)

            self.assertEqual(result["operation"], "resume_job")
            self.assertEqual(result["job_id"], "J001")


class RootAuthoredOutcomeRejectionTest(unittest.TestCase):
    """Outcome with invalid artifact digest is rejected; job status unchanged."""

    def test_invalid_artifact_digest_rejects_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Actual content\n", encoding="utf-8")
            bad_digest = "a" * 64
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-T/jobs/J001/report",
                    "content_sha256": bad_digest,
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            with self.assertRaisesRegex(OrchestratorError, "digest does not match"):
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"],
                    native_session_ref="ses-1",
                    run_id="RUN-T", job_id="J001",
                    response_id="R-1", raw_response=raw, received_at=NOW,
                ), controller="test", adapter=adapter)

    def test_rejected_outcome_does_not_change_job_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            state_before = load_v5_state(run)
            status_before = state_before["jobs"]["J001"]["status"]
            revision_before = state_before["jobs"]["J001"]["revision"]

            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Content\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-T/jobs/J001/report",
                    "content_sha256": "b" * 64,
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            try:
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"],
                    native_session_ref="ses-1",
                    run_id="RUN-T", job_id="J001",
                    response_id="R-1", raw_response=raw, received_at=NOW,
                ), controller="test", adapter=adapter)
            except OrchestratorError:
                pass

            state_after = load_v5_state(run)
            self.assertEqual(state_after["jobs"]["J001"]["status"], status_before)
            self.assertEqual(state_after["jobs"]["J001"]["revision"], revision_before)


class CancellationRecoveryTest(unittest.TestCase):
    """Canceled receipt moves job to recovering; next() returns wait."""

    def test_canceled_receipt_moves_to_recovering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response="", received_at=NOW,
                status="canceled",
            ), controller="test", adapter=adapter)

            self.assertEqual(result["status"], "recovering")
            self.assertTrue(result["recovery_required"])

            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["status"], "recovering")

    def test_next_returns_wait_when_job_is_recovering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response="", received_at=NOW,
                status="lost",
            ), controller="test", adapter=adapter)

            next_op = select_v5_next_operation(run)
            self.assertEqual(next_op["operation"], "wait")


class ReplacementAttemptHistoryTest(unittest.TestCase):
    """Recovery-authorized replacement appends a new attempt; normal scheduling does not."""

    def test_recovery_authorized_replacement_appends_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            state_before = load_v5_state(run)
            self.assertEqual(len(state_before["jobs"]["J001"]["attempts"]), 1)
            old_attempt_id = state_before["jobs"]["J001"]["attempts"][0]["attempt_id"]

            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response="", received_at=NOW,
                status="lost",
            ), controller="test", adapter=adapter)

            evidence = {
                "schema_version": V5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "lost",
                "transport": {},
                "recovery_id": "REC-1",
            }
            recover_v5_job(run, "J001", evidence, controller="test")

            next_op = select_v5_next_operation(run)
            self.assertEqual(next_op["operation"], "start_job")
            self.assertIn("dispatch", next_op)

            state_after = load_v5_state(run)
            self.assertEqual(len(state_after["jobs"]["J001"]["attempts"]), 1)
            self.assertEqual(state_after["jobs"]["J001"]["attempts"][0]["attempt_id"], old_attempt_id)

    def test_normal_scheduling_does_not_create_replacement_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()

            next_op = select_v5_next_operation(run)
            self.assertEqual(next_op["operation"], "start_job")

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertEqual(len(job["attempts"]), 0)
            self.assertEqual(len(job["dispatches"]), 1)
            self.assertEqual(job["dispatches"][0]["kind"], "start")
            self.assertIsNone(job["active_attempt_id"])


class InterruptedNonIdempotentEffectTest(unittest.TestCase):
    """Job with external_non_idempotent side effect requires recovery check before retry."""

    def test_non_idempotent_job_requires_recovery_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _non_idempotent_definition(), controller="test")
            adapter = FakeTransportAdapter()
            launch = _launch_job(run, adapter)

            state_before = load_v5_state(run)
            job_before = state_before["jobs"]["J001"]
            self.assertEqual(job_before["side_effect_class"], "external_non_idempotent")
            self.assertIsNotNone(job_before["recovery_policy"])

            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                response_id="R-1", raw_response="", received_at=NOW,
                status="canceled",
            ), controller="test", adapter=adapter)

            state_mid = load_v5_state(run)
            self.assertEqual(state_mid["jobs"]["J001"]["status"], "recovering")

            next_op = select_v5_next_operation(run)
            self.assertEqual(next_op["operation"], "wait")


if __name__ == "__main__":
    unittest.main()
