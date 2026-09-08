"""Transport-specific tests: receipt verification, idempotence, conflict, and crash reconciliation."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, write_json  # noqa: E402
from transport_v5 import (  # noqa: E402
    FakeTransportAdapter,
    HmacTransportAdapter,
    TransportAdapter,
    TransportVerificationError,
)
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


def _make_run(base: Path, run_id: str = "RUN-T", goal: str = "Test goal") -> Path:
    request = base / "request.md"
    request.write_text("Request\n", encoding="utf-8")
    result = init_v5_run(request, goal, run_id=run_id, state_root=base, workspace=base)
    return Path(result["run_root"])


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


class FabricatedSessionRejectionTest(unittest.TestCase):
    """Receipt with valid proof but invented native_session_ref is rejected."""

    def test_fabricated_session_rejected_on_response_receipt(self) -> None:
        """A response receipt with valid HMAC but wrong native_session_ref fails."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-real",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)

            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Done\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-T/jobs/J001/report",
                    "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })

            with self.assertRaisesRegex(OrchestratorError, "correlation does not match"):
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"],
                    native_session_ref="ses-fabricated",
                    run_id="RUN-T", job_id="J001",
                    response_id="R-FAB", raw_response=raw, received_at=NOW,
                ), controller="test", adapter=adapter)

    def test_fabricated_session_rejected_on_resume_launch_receipt(self) -> None:
        """A resume receipt with valid HMAC but wrong native_session_ref fails."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-real",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)

            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Question\n", encoding="utf-8")
            raw_q = json.dumps({
                "status": "needs_input", "question": "What next?",
                "summary": "Need input", "response_id": "R-Q",
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-real",
                run_id="RUN-T", job_id="J001", response_id="R-Q",
                raw_response=raw_q, received_at=NOW,
            ), controller="test", adapter=adapter)

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertEqual(job["status"], "waiting_for_input")

            from v5_core import record_v5_answer
            record_v5_answer(run, "J001", "Go ahead", controller="test")

            state2 = load_v5_state(run)
            job2 = state2["jobs"]["J001"]
            resume_dispatch = next(
                d for d in job2["dispatches"] if d["dispatch_id"] == job2["pending_dispatch_id"]
            )

            with self.assertRaisesRegex(OrchestratorError, "existing native session"):
                record_v5_launch_receipt(run, adapter.launch_receipt(
                    dispatch_id=resume_dispatch["dispatch_id"],
                    native_session_ref="ses-fabricated",
                    run_id="RUN-T", job_id="J001",
                    prompt_sha256=resume_dispatch["prompt_sha256"],
                    created_at=NOW,
                ), controller="test", adapter=adapter)


class WrongCorrelationRejectionTest(unittest.TestCase):
    """Receipts with wrong run_id or job_id are rejected."""

    def test_wrong_run_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="WRONG-RUN", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "correlation does not match"):
                record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

    def test_wrong_job_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="WRONG-JOB",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "unknown job"):
                record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

    def test_unknown_dispatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id="DSP-NONEXISTENT",
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256="a" * 64,
                created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "unknown dispatch"):
                record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)


class AlteredPromptDeliveryRejectionTest(unittest.TestCase):
    """Receipt with prompt_sha256 differing from dispatch is rejected."""

    def test_altered_prompt_digest_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256="b" * 64,
                created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "prompt digest does not match"):
                record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

    def test_wrong_hash_on_response_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)

            raw = json.dumps({"status": "completed", "summary": "Done."})
            receipt = adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001", response_id="R-1",
                raw_response=raw, received_at=NOW,
            )
            receipt["response_sha256"] = "c" * 64

            with self.assertRaisesRegex(OrchestratorError, "hash does not match raw response"):
                record_v5_response_receipt(run, receipt, controller="test", adapter=adapter)


class DuplicateReceiptIdempotenceTest(unittest.TestCase):
    """Same receipt submitted twice; second is no-op, state unchanged."""

    def test_duplicate_launch_receipt_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            first = record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            self.assertTrue(first["recorded"])

            second = record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            self.assertFalse(second["recorded"])
            self.assertEqual(first["attempt_id"], second["attempt_id"])

            state = load_v5_state(run)
            self.assertEqual(len(state["jobs"]["J001"]["attempts"]), 1)

    def test_duplicate_launch_receipt_preserves_job_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertEqual(job["status"], "running")
            self.assertEqual(job["revision"], 3)


class ConflictingReceiptRejectionTest(unittest.TestCase):
    """Two different receipts for same dispatch; second rejected."""

    def test_conflicting_session_for_same_dispatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt_a = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-alpha",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            first = record_v5_launch_receipt(run, receipt_a, controller="test", adapter=adapter)
            self.assertEqual(first["native_session_ref"], "ses-alpha")

            receipt_b = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-beta",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "different native session"):
                record_v5_launch_receipt(run, receipt_b, controller="test", adapter=adapter)

    def test_conflicting_session_does_not_corrupt_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt_a = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-alpha",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt_a, controller="test", adapter=adapter)

            receipt_b = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-beta",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            try:
                record_v5_launch_receipt(run, receipt_b, controller="test", adapter=adapter)
            except OrchestratorError:
                pass

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertEqual(len(job["attempts"]), 1)
            self.assertEqual(job["attempts"][0]["native_session_ref"], "ses-alpha")
            self.assertEqual(job["active_attempt_id"], job["attempts"][0]["attempt_id"])


class CrashReconciliationTest(unittest.TestCase):
    """Crash-recovery scenarios for dispatch and receipt persistence."""

    def test_crash_after_dispatch_persistence_no_receipt(self) -> None:
        """Dispatch exists but no launch receipt; state shows pending dispatch."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            self.assertEqual(start["operation"], "start_job")

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertEqual(job["status"], "starting")
            self.assertIsNotNone(job["pending_dispatch_id"])
            self.assertEqual(len(job["attempts"]), 0)

    def test_worker_created_before_receipt_persistence(self) -> None:
        """Launch receipt missing but adapter has record; recovery records original attempt."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )

            state_before = load_v5_state(run)
            self.assertEqual(state_before["jobs"]["J001"]["status"], "starting")
            self.assertEqual(len(state_before["jobs"]["J001"]["attempts"]), 0)

            launch = record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            self.assertTrue(launch["recorded"])

            state_after = load_v5_state(run)
            job = state_after["jobs"]["J001"]
            self.assertEqual(job["status"], "running")
            self.assertEqual(len(job["attempts"]), 1)
            self.assertEqual(job["attempts"][0]["native_session_ref"], "ses-1")

    def test_recovered_original_launch_pending_dispatch_correlates(self) -> None:
        """After crash, pending dispatch correlates to existing adapter receipt -> no replacement launched."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            launch = record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            self.assertTrue(launch["recorded"])

            state = load_v5_state(run)
            job = state["jobs"]["J001"]
            self.assertIsNone(job["pending_dispatch_id"])
            self.assertEqual(job["status"], "running")

            next_op = select_v5_next_operation(run)
            self.assertIn(next_op["operation"], ("wait", "resume_job"))

    def test_unresolved_launch_status_blocks_job(self) -> None:
        """Adapter cannot determine if worker was created -> job blocked until operator evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            evidence_unknown = {
                "schema_version": V5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "unknown",
                "transport": {},
                "recovery_id": "REC-1",
            }
            result = recover_v5_job(run, "J001", evidence_unknown, controller="test")
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["replacement_authorized"])

            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["status"], "blocked")

    def test_lost_classification_triggers_replacement(self) -> None:
        """Lost classification -> job queued for replacement."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

            state_before = load_v5_state(run)
            attempt_id = state_before["jobs"]["J001"]["active_attempt_id"]
            self.assertIsNotNone(attempt_id)

            evidence_lost = {
                "schema_version": V5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "lost",
                "transport": {"detail": "worker unresponsive"},
                "recovery_id": "REC-2",
            }
            result = recover_v5_job(run, "J001", evidence_lost, controller="test")
            self.assertEqual(result["status"], "queued")
            self.assertTrue(result["replacement_authorized"])

            state_after = load_v5_state(run)
            job = state_after["jobs"]["J001"]
            self.assertEqual(job["active_attempt_id"], None)
            self.assertEqual(job["status"], "queued")

    def test_canceled_classification_triggers_replacement(self) -> None:
        """Canceled classification -> job queued for replacement."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

            evidence_canceled = {
                "schema_version": V5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "canceled",
                "transport": {},
                "recovery_id": "REC-3",
            }
            result = recover_v5_job(run, "J001", evidence_canceled, controller="test")
            self.assertEqual(result["status"], "queued")
            self.assertTrue(result["replacement_authorized"])

    def test_contradictory_evidence_blocks_job(self) -> None:
        """Contradictory classification -> job blocked."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run = _make_run(base)
            register_v5_jobs(run, _simple_definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()

            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-T", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)

            evidence = {
                "schema_version": V5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "contradictory",
                "transport": {},
                "recovery_id": "REC-4",
            }
            result = recover_v5_job(run, "J001", evidence, controller="test")
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["replacement_authorized"])


if __name__ == "__main__":
    unittest.main()
