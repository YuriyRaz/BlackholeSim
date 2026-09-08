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
    artifact_ref,
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


class TrustedV5WorkflowTest(unittest.TestCase):
    def _run(self, base: Path, definition: dict) -> Path:
        request = base / "request.md"
        request.write_text("Request\n", encoding="utf-8")
        run = Path(init_v5_run(request, "Goal", run_id="RUN-WORKFLOW", state_root=base, workspace=base)["run_root"])
        register_v5_jobs(run, definition, controller="test")
        return run

    def _complete(self, run: Path, adapter: FakeTransportAdapter, job_id: str, *, session: str, condition_id: str, status: str = "completed", operation: dict | None = None) -> dict:
        if operation is None:
            operation = select_v5_next_operation(run)
        self.assertEqual(operation["job_id"], job_id)
        launch = record_v5_launch_receipt(run, adapter.launch_receipt(
            dispatch_id=operation["dispatch"]["dispatch_id"], native_session_ref=session,
            run_id="RUN-WORKFLOW", job_id=job_id,
            prompt_sha256=operation["dispatch"]["prompt_sha256"], created_at=NOW,
        ), controller="test", adapter=adapter)
        raw = json.dumps({
            "status": status,
            "summary": "Worker result.",
            "condition_results": [{"condition_id": condition_id, "status": "passed", "verified_by": job_id}],
        })
        return record_v5_response_receipt(run, adapter.response_receipt(
            attempt_id=launch["attempt_id"], native_session_ref=session,
            run_id="RUN-WORKFLOW", job_id=job_id, response_id=f"RESP-{job_id}",
            raw_response=raw, received_at=NOW,
        ), controller="test", adapter=adapter)

    def test_dependency_report_and_independent_verifier_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            definition = {
                "schema_version": 5,
                "jobs": [
                    {
                        "id": "J001", "title": "Implement", "goal": "Implement.",
                        "completion_conditions": [{
                            "id": "browser", "description": "Browser verification", "required": True,
                            "evidence_required": False, "verification": "independent", "verifier_job_id": "J002",
                        }],
                        "report_required": True, "side_effect_class": "repository",
                        "recovery_policy": {"check": "Inspect repository."},
                    },
                    {
                        "id": "J002", "title": "Verify", "goal": "Verify.", "depends_on": ["J001"],
                        "completion_conditions": [{
                            "id": "browser", "description": "Browser verification", "required": True,
                            "evidence_required": False, "verification": "self",
                        }],
                        "report_required": False, "side_effect_class": "none",
                    },
                ],
            }
            run = self._run(base, definition)
            adapter = FakeTransportAdapter()
            first = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=first["dispatch"]["dispatch_id"], native_session_ref="ses-1", run_id="RUN-WORKFLOW",
                job_id="J001", prompt_sha256=first["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Implementation report\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Claimed.",
                "artifacts": [{"ref": artifact_ref("RUN-WORKFLOW", "J001", "report"), "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest()}],
                "condition_results": [{"condition_id": "browser", "status": "passed", "verified_by": "J001"}],
            })
            claim = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1", run_id="RUN-WORKFLOW", job_id="J001",
                response_id="RESP-J001", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertEqual(claim["status"], "completion_claimed")
            verify = select_v5_next_operation(run)
            self.assertEqual(verify["job_id"], "J002")
            self.assertIn(artifact_ref("RUN-WORKFLOW", "J001", "report"), verify["prompt"])
            verified = self._complete(run, adapter, "J002", session="ses-2", condition_id="browser", operation=verify)
            self.assertEqual(verified["status"], "completed")
            self.assertEqual(load_v5_state(run)["jobs"]["J001"]["status"], "completed")
            self.assertEqual(select_v5_next_operation(run), {"operation": "run_complete", "run_status": "completed", "successful": True})

    def test_unsafe_artifact_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(OrchestratorError, "path-safe"):
            artifact_ref("RUN-1", "..", "report")

    def test_interruption_recovery_repair_and_unsuccessful_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            definition = {
                "schema_version": 5,
                "jobs": [
                    {
                        "id": "J001", "title": "Implement", "goal": "Implement.",
                        "completion_conditions": [{
                            "id": "browser", "description": "Browser verification", "required": True,
                            "evidence_required": False, "verification": "self",
                        }],
                        "report_required": True, "side_effect_class": "repository",
                        "recovery_policy": {"check": "Inspect repository."},
                    },
                ],
            }
            run = self._run(base, definition)
            adapter = FakeTransportAdapter()

            op = select_v5_next_operation(run)
            self.assertEqual(op["job_id"], "J001")
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=op["dispatch"]["dispatch_id"], native_session_ref="ses-cancel",
                run_id="RUN-WORKFLOW", job_id="J001",
                prompt_sha256=op["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertIn("attempt_id", launch)

            state_before = load_v5_state(run)
            self.assertEqual(state_before["jobs"]["J001"]["status"], "running")

            result = audit_v5_state(run)
            self.assertTrue(result["valid"])

            evidence = {
                "schema_version": 5,
                "job_id": "J001",
                "observed_at": NOW,
                "classification": "canceled",
                "transport": {"cancellation_requested": True},
                "recovery_id": "REC-001",
            }
            recovery = recover_v5_job(run, "J001", evidence, controller="test")
            self.assertTrue(recovery["replacement_authorized"])
            self.assertEqual(recovery["status"], "queued")

            state_after = load_v5_state(run)
            self.assertEqual(state_after["jobs"]["J001"]["status"], "queued")
            self.assertIsNone(state_after["jobs"]["J001"]["active_attempt_id"])

            op2 = select_v5_next_operation(run)
            self.assertEqual(op2["job_id"], "J001")
            launch2 = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=op2["dispatch"]["dispatch_id"], native_session_ref="ses-retry",
                run_id="RUN-WORKFLOW", job_id="J001",
                prompt_sha256=op2["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertIn("attempt_id", launch2)
            state_retry = load_v5_state(run)
            self.assertEqual(state_retry["jobs"]["J001"]["status"], "running")
            self.assertEqual(len(state_retry["jobs"]["J001"]["attempts"]), 2)

            raw_fail = json.dumps({
                "status": "failed", "summary": "Worker failed.",
                "condition_results": [{"condition_id": "browser", "status": "failed", "verified_by": "J001"}],
            })
            resp_fail = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch2["attempt_id"], native_session_ref="ses-retry",
                run_id="RUN-WORKFLOW", job_id="J001", response_id="RESP-FAIL",
                raw_response=raw_fail, received_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertEqual(resp_fail["status"], "failed")

            terminal = select_v5_next_operation(run)
            self.assertEqual(terminal["operation"], "run_complete")
            self.assertEqual(terminal["run_status"], "failed")
            self.assertFalse(terminal["successful"])

    def test_append_only_attempts_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            definition = {
                "schema_version": 5,
                "jobs": [
                    {
                        "id": "J001", "title": "Work", "goal": "Do work.",
                        "completion_conditions": [{
                            "id": "done", "description": "Done", "required": True,
                            "evidence_required": False, "verification": "self",
                        }],
                        "report_required": False, "side_effect_class": "none",
                        "recovery_policy": {"check": "Inspect."},
                    },
                ],
            }
            run = self._run(base, definition)
            adapter = FakeTransportAdapter()

            for attempt_num in range(3):
                op = select_v5_next_operation(run)
                launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                    dispatch_id=op["dispatch"]["dispatch_id"],
                    native_session_ref=f"ses-{attempt_num}",
                    run_id="RUN-WORKFLOW", job_id="J001",
                    prompt_sha256=op["dispatch"]["prompt_sha256"], created_at=NOW,
                ), controller="test", adapter=adapter)

                evidence = {
                    "schema_version": 5, "job_id": "J001", "observed_at": NOW,
                    "classification": "lost", "transport": {},
                    "recovery_id": f"REC-{attempt_num}",
                }
                recover_v5_job(run, "J001", evidence, controller="test")

            state = load_v5_state(run)
            self.assertEqual(len(state["jobs"]["J001"]["attempts"]), 3)
            self.assertEqual(state["jobs"]["J001"]["status"], "queued")

    def test_repair_forces_stuck_job_to_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            definition = {
                "schema_version": 5,
                "jobs": [
                    {
                        "id": "J001", "title": "Work", "goal": "Do work.",
                        "completion_conditions": [{
                            "id": "done", "description": "Done", "required": True,
                            "evidence_required": False, "verification": "self",
                        }],
                        "report_required": False, "side_effect_class": "none",
                        "recovery_policy": {"check": "Inspect."},
                    },
                ],
            }
            run = self._run(base, definition)
            adapter = FakeTransportAdapter()

            op = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=op["dispatch"]["dispatch_id"],
                native_session_ref="ses-stuck",
                run_id="RUN-WORKFLOW", job_id="J001",
                prompt_sha256=op["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)

            state_running = load_v5_state(run)
            self.assertEqual(state_running["jobs"]["J001"]["status"], "running")

            repair_result = repair_v5_job(run, "J001", "failed", "Transport unreachable", controller="test")
            self.assertTrue(repair_result["recorded"])
            self.assertEqual(repair_result["status"], "failed")

            terminal = select_v5_next_operation(run)
            self.assertEqual(terminal["operation"], "run_complete")
            self.assertEqual(terminal["run_status"], "failed")
            self.assertFalse(terminal["successful"])


if __name__ == "__main__":
    unittest.main()
