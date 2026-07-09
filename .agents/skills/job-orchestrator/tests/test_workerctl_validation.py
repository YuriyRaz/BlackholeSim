from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jobctl
import workerctl
from orchestrator_core import OrchestratorError, load_json, write_json


class WorkerValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.run = Path(jobctl.init_run(argparse.Namespace(
            goal="worker validation", run_id="worker-validation",
            state_root=self.base, workspace=self.base,
            request="validate workers", request_file=None, controller="test",
        ))["run_root"])
        definition = {
            "jobs": [{
                "id": "J001", "title": "Implement", "goal": "Implement one unit",
                "role": "Implementation", "priority": 50,
                "workspace": str(self.base),
                "allowed_edit_roots": [str(self.base)],
                "capabilities": ["edit"],
                "workflow": {"nodes": [{
                    "id": "apply", "position": 1, "run_in": "job_session",
                    "work_units": ["U1"], "acceptance_criteria": ["tests pass"],
                    "required_checks": ["unit tests"],
                    "prohibited_actions": ["later nodes"],
                    "checkpoint_policy": ["after_discovery", "before_blocker"],
                    "side_effect_class": "workspace_write",
                    "recovery_check": "inspect workspace",
                }]},
            }],
        }
        definition_path = self.base / "definition.json"
        write_json(definition_path, definition)
        jobctl.compile_jobs(argparse.Namespace(
            run=self.run, definition=definition_path, controller="test",
        ))
        self.contract_path = self.run / "jobs/J001/contract.json"
        self.contract = load_json(self.contract_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ack_args(self, **changes):
        values = {
            "contract": self.contract_path,
            "protocol_version": 3,
            "protocol_sha256": self.contract["protocol"]["sha256"],
            "job_id": "J001",
            "contract_revision": 1,
            "current_node": "apply",
            "session_id": "session-1",
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def bootstrap(self):
        action = jobctl.next_action(argparse.Namespace(
            run=self.run, controller="test",
        ))
        ack = workerctl.acknowledge(self.ack_args())
        response_path = self.base / "ack.json"
        write_json(response_path, ack)
        jobctl.record(argparse.Namespace(
            run=self.run, action_id=action["action_id"],
            response=response_path, controller="test",
        ))
        dispatch_action = jobctl.next_action(argparse.Namespace(
            run=self.run, controller="test",
        ))
        return (
            dispatch_action,
            self.run / "jobs/J001/dispatches" / f"{dispatch_action['dispatch_id']}.json",
        )

    def test_acknowledgement_binds_every_bootstrap_identity(self):
        ack = workerctl.acknowledge(self.ack_args())
        self.assertEqual(ack["session_id"], "session-1")
        self.assertEqual(ack["protocol_ack"]["current_workflow_node_id"], "apply")
        self.assertEqual(ack["protocol_ack"]["session_id"], "session-1")
        for field, bad in (
            ("protocol_version", 2),
            ("protocol_sha256", "0" * 64),
            ("job_id", "J999"),
            ("contract_revision", 2),
            ("current_node", "verify"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(OrchestratorError, "acknowledgement mismatch"):
                    workerctl.acknowledge(self.ack_args(**{field: bad}))
        with self.assertRaisesRegex(OrchestratorError, "session_id"):
            workerctl.acknowledge(self.ack_args(session_id=" "))

    def test_inspect_rejects_nonce_session_and_current_node_mismatches(self):
        _, dispatch_path = self.bootstrap()
        valid = {
            "dispatch": dispatch_path, "nonce": load_json(dispatch_path)["nonce"],
            "session_id": "session-1", "current_node": "apply",
        }
        self.assertTrue(workerctl.inspect(argparse.Namespace(**valid))["valid"])
        for field, bad, message in (
            ("nonce", "wrong", "nonce"),
            ("session_id", "session-2", "session identity"),
            ("current_node", "verify", "workflow node"),
        ):
            with self.subTest(field=field):
                args = {**valid, field: bad}
                with self.assertRaisesRegex(OrchestratorError, message):
                    workerctl.inspect(argparse.Namespace(**args))

    def prepare_result(self, dispatch_path: Path, *, issue=None):
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path, phase="complete",
            completed_work_unit=["U1"], decision=[],
            issue=[issue] if issue else [], artifact=[],
            next_action="finalize",
        ))
        report = self.run / "jobs/J001/report.md"
        report.write_text("U1 complete; unit tests passed.", encoding="utf-8")
        artifact = self.run / "jobs/J001/results/evidence.txt"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("test evidence", encoding="utf-8")
        return artifact

    def test_finalize_emits_hashed_evidence_and_no_readiness_claim(self):
        _, dispatch_path = self.bootstrap()
        artifact = self.prepare_result(dispatch_path)
        output = workerctl.finalize(argparse.Namespace(
            dispatch=dispatch_path, status="completed", summary="done",
            artifact=[str(artifact)], acceptance_evidence=["unit tests passed"],
            blocking_issue=[], session_id="session-1",
        ))
        result = output["result"]
        self.assertNotIn("ready_for_next_step", result)
        evidence = {item["purpose"]: item for item in result["artifacts"]}
        for purpose in ("worker report", "current checkpoint", "machine-readable progress"):
            self.assertEqual(len(evidence[purpose]["sha256"]), 64)
        self.assertEqual(evidence["supporting artifact"]["path"], "results/evidence.txt")
        self.assertEqual(len(evidence["supporting artifact"]["sha256"]), 64)

    def test_finalize_rejects_incomplete_or_fabricated_evidence(self):
        _, dispatch_path = self.bootstrap()
        artifact = self.prepare_result(dispatch_path)
        common = {
            "dispatch": dispatch_path, "status": "completed", "summary": "done",
            "artifact": [str(artifact)], "acceptance_evidence": ["tests"],
            "blocking_issue": [], "session_id": "session-1",
        }
        progress_path = self.run / "jobs/J001/progress.json"
        progress = load_json(progress_path)
        progress["nonce"] = "fabricated"
        write_json(progress_path, progress)
        with self.assertRaisesRegex(OrchestratorError, "progress is not bound"):
            workerctl.finalize(argparse.Namespace(**common))

    def test_blocked_requires_precise_issue_in_current_checkpoint(self):
        _, dispatch_path = self.bootstrap()
        self.prepare_result(dispatch_path)
        with self.assertRaisesRegex(OrchestratorError, "precise blocking issue"):
            workerctl.finalize(argparse.Namespace(
                dispatch=dispatch_path, status="blocked", summary="blocked",
                artifact=[], acceptance_evidence=[], blocking_issue=[],
                session_id="session-1",
            ))
        with self.assertRaisesRegex(OrchestratorError, "current checkpoint"):
            workerctl.finalize(argparse.Namespace(
                dispatch=dispatch_path, status="blocked", summary="blocked",
                artifact=[], acceptance_evidence=[],
                blocking_issue=["Missing API authorization"],
                session_id="session-1",
            ))
        issue = "Missing API authorization"
        self.prepare_result(dispatch_path, issue=issue)
        result = workerctl.finalize(argparse.Namespace(
            dispatch=dispatch_path, status="blocked", summary="blocked",
            artifact=[], acceptance_evidence=[], blocking_issue=[issue],
            session_id="session-1",
        ))["result"]
        self.assertEqual(result["blocking_issues"], [issue])


if __name__ == "__main__":
    unittest.main()
