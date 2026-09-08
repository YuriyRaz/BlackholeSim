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
    audit_v5_state,
    init_v5_run,
    load_v5_state,
    record_v5_launch_receipt,
    record_v5_response_receipt,
    recover_v5_job,
    register_v5_jobs,
    repair_v5_job,
    select_v5_next_operation,
)


NOW = "2026-07-24T12:00:00Z"


class V5RegressionTest(unittest.TestCase):
    def definition(self, *, report_required: bool = True) -> dict:
        return {
            "schema_version": 5,
            "jobs": [{
                "id": "J001", "title": "Work", "goal": "Work.",
                "completion_conditions": [{
                    "id": "tests", "description": "Tests pass", "required": True,
                    "evidence_required": False, "verification": "self",
                }],
                "report_required": report_required, "side_effect_class": "repository",
                "recovery_policy": {"check": "Inspect repository."},
            }],
        }

    def setup_run(self, base: Path, definition: dict | None = None) -> tuple[Path, FakeTransportAdapter, dict]:
        request = base / "request.md"
        request.write_text("Request\n", encoding="utf-8")
        run = Path(init_v5_run(request, "Goal", run_id="RUN-REGRESSION", state_root=base, workspace=base)["run_root"])
        register_v5_jobs(run, definition or self.definition(), controller="test")
        adapter = FakeTransportAdapter()
        operation = select_v5_next_operation(run)
        return run, adapter, operation

    def launch(self, run: Path, adapter: FakeTransportAdapter, operation: dict, *, session: str = "ses-1") -> dict:
        return record_v5_launch_receipt(run, adapter.launch_receipt(
            dispatch_id=operation["dispatch"]["dispatch_id"], native_session_ref=session,
            run_id="RUN-REGRESSION", job_id="J001",
            prompt_sha256=operation["dispatch"]["prompt_sha256"], created_at=NOW,
        ), controller="test", adapter=adapter)

    def test_receipt_conflicts_and_duplicate_are_handled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run, adapter, operation = self.setup_run(Path(temporary))
            bad = adapter.launch_receipt(
                dispatch_id=operation["dispatch"]["dispatch_id"], native_session_ref="ses-1",
                run_id="RUN-other", job_id="J001", prompt_sha256=operation["dispatch"]["prompt_sha256"], created_at=NOW,
            )
            with self.assertRaisesRegex(OrchestratorError, "correlation"):
                record_v5_launch_receipt(run, bad, controller="test", adapter=adapter)
            good = adapter.launch_receipt(
                dispatch_id=operation["dispatch"]["dispatch_id"], native_session_ref="ses-1",
                run_id="RUN-REGRESSION", job_id="J001", prompt_sha256=operation["dispatch"]["prompt_sha256"], created_at=NOW,
            )
            first = record_v5_launch_receipt(run, good, controller="test", adapter=adapter)
            duplicate = record_v5_launch_receipt(run, good, controller="test", adapter=adapter)
            self.assertFalse(duplicate["recorded"])
            self.assertEqual(first["attempt_id"], duplicate["attempt_id"])

    def test_pending_dispatch_unknown_status_blocks_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run, adapter, operation = self.setup_run(Path(temporary))
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["status"], "starting")
            self.assertEqual(state["jobs"]["J001"]["pending_dispatch_id"], operation["dispatch"]["dispatch_id"])
            recovered = recover_v5_job(run, "J001", {
                "schema_version": 5, "job_id": "J001", "observed_at": NOW,
                "classification": "unknown", "transport": {"status": "unavailable"}, "recovery_id": "REC-unknown",
            }, controller="test")
            self.assertEqual(recovered["status"], "blocked")
            self.assertEqual(select_v5_next_operation(run), {"operation": "wait"})

    def test_malformed_empty_and_replacement_attempts_require_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run, adapter, operation = self.setup_run(Path(temporary))
            launch = self.launch(run, adapter, operation)
            malformed = adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1", run_id="RUN-REGRESSION",
                job_id="J001", response_id="R-bad", raw_response="not json", received_at=NOW,
            )
            self.assertEqual(record_v5_response_receipt(run, malformed, controller="test", adapter=adapter)["operation"], "resume_job")
            empty = adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1", run_id="RUN-REGRESSION",
                job_id="J001", response_id="R-empty", raw_response="", received_at=NOW,
                status="empty", session_liveness="unknown",
            )
            self.assertTrue(record_v5_response_receipt(run, empty, controller="test", adapter=adapter)["recovery_required"])
            recovered = recover_v5_job(run, "J001", {
                "schema_version": 5, "job_id": "J001", "observed_at": NOW,
                "classification": "lost", "transport": {"status": "lost"}, "recovery_id": "REC-1",
            }, controller="test")
            self.assertTrue(recovered["replacement_authorized"])
            replacement = select_v5_next_operation(run)
            self.assertNotEqual(replacement["dispatch"]["dispatch_id"], operation["dispatch"]["dispatch_id"])

    def test_missing_conditions_block_and_terminal_dispositions_are_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run, adapter, operation = self.setup_run(Path(temporary), self.definition(report_required=False))
            launch = self.launch(run, adapter, operation)
            raw = json.dumps({"status": "completed", "summary": "Claim without conditions."})
            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1", run_id="RUN-REGRESSION",
                job_id="J001", response_id="R-missing", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertEqual(result["status"], "blocked")
            repair_v5_job(run, "J001", "failed", "required evidence was unavailable", controller="test")
            terminal = select_v5_next_operation(run)
            self.assertEqual(terminal, {"operation": "run_complete", "run_status": "failed", "successful": False})

    def test_audit_detects_tampered_attested_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run, adapter, operation = self.setup_run(Path(temporary))
            launch = self.launch(run, adapter, operation)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Report\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{"ref": "run://RUN-REGRESSION/jobs/J001/report", "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest()}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1", run_id="RUN-REGRESSION",
                job_id="J001", response_id="R-good", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            report.write_text("Tampered\n", encoding="utf-8")
            self.assertFalse(audit_v5_state(run)["valid"])


if __name__ == "__main__":
    unittest.main()
