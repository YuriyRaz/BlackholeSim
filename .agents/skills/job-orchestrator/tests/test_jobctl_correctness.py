from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jobctl
import workerctl
from orchestrator_core import OrchestratorError, load_json, replay, write_json


class JobctlCorrectnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.run = Path(jobctl.init_run(argparse.Namespace(
            goal="correctness", run_id="correctness", state_root=self.base,
            workspace=self.base, request="test", request_file=None,
            controller="test",
        ))["run_root"])
        definition = self.base / "definition.json"
        write_json(definition, {"jobs": [{
            "id": "PARENT", "title": "Parent", "goal": "Do one unit",
            "role": "implementer", "workspace": str(self.base),
            "allowed_edit_roots": [str(self.base)], "capabilities": ["edit"],
            "workflow": {"nodes": [{
                "id": "apply", "position": 1, "work_units": ["U1"],
                "acceptance_criteria": ["verified"], "required_checks": ["tests"],
                "prohibited_actions": ["later nodes"],
                "checkpoint_policy": ["before_result"],
                "side_effect_class": "workspace_write",
                "recovery_check": "inspect workspace",
            }]},
        }]})
        jobctl.compile_jobs(argparse.Namespace(
            run=self.run, definition=definition, controller="test"
        ))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def next(self) -> dict:
        return jobctl.next_action(argparse.Namespace(
            run=self.run, controller="test"
        ))

    def record(self, action: dict, response: dict) -> dict:
        path = self.base / f"{action['action_id']}-response.json"
        write_json(path, response)
        return jobctl.record(argparse.Namespace(
            run=self.run, action_id=action["action_id"], response=path,
            controller="test",
        ))

    def bootstrap(self, session_id: str = "session-1") -> None:
        action = self.next()
        response = workerctl.acknowledge(argparse.Namespace(
            contract=self.run / "jobs/PARENT/contract.json",
            current_node="apply", session_id=session_id,
        ))
        self.record(action, response)

    def dispatch(self) -> tuple[dict, Path]:
        action = self.next()
        return action, (
            self.run / "jobs/PARENT/dispatches"
            / f"{action['dispatch_id']}.json"
        )

    def finalize(self, action: dict, dispatch: Path, status: str = "completed",
                 issue: str | None = None) -> dict:
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch, phase=status, completed_work_unit=["U1"],
            decision=[], issue=[issue] if issue else [], artifact=[],
            next_action="return result", session_id="session-1",
        ))
        (self.run / "jobs/PARENT/report.md").write_text(
            "verified", encoding="utf-8"
        )
        return workerctl.finalize(argparse.Namespace(
            dispatch=dispatch, status=status, summary=status, artifact=[],
            acceptance_evidence=[] if status == "blocked" else ["tests pass"],
            blocking_issue=[issue] if issue else [], session_id="session-1",
        ))

    def test_acknowledgement_rejects_every_stale_binding(self) -> None:
        action = self.next()
        valid = workerctl.acknowledge(argparse.Namespace(
            contract=self.run / "jobs/PARENT/contract.json",
            current_node="apply", session_id="session-1",
        ))
        fields = {
            "protocol_version": 2, "protocol_sha256": "wrong",
            "job_id": "OTHER", "contract_revision": 99,
            "current_workflow_node_id": "later", "session_id": "",
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                response = {
                    "protocol_ack": dict(valid["protocol_ack"]),
                    "session_id": valid["session_id"],
                }
                if field == "session_id":
                    response[field] = value
                    response["protocol_ack"].pop("session_id", None)
                else:
                    response["protocol_ack"][field] = value
                with self.assertRaises(OrchestratorError):
                    self.record(action, response)

    def test_result_revalidation_and_terminal_transition_are_idempotent(self) -> None:
        self.bootstrap()
        action, dispatch = self.dispatch()
        response = self.finalize(action, dispatch)
        checkpoint = self.run / "jobs/PARENT/checkpoint.md"
        checkpoint.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(OrchestratorError, "hash mismatch"):
            self.record(action, response)
        self.finalize(action, dispatch)
        response = load_json(
            self.run / "jobs/PARENT/results"
            / f"{action['dispatch_id']}.json"
        )
        self.record(action, {
            "result": response,
            "result_path": str(
                self.run / "jobs/PARENT/results"
                / f"{action['dispatch_id']}.json"
            ),
        })
        terminal = self.next()
        self.assertEqual(terminal["type"], "run_complete")
        self.record(terminal, {"acknowledged": True})
        events = len(load_json_lines(self.run / "events.jsonl"))
        stable = self.next()
        self.assertEqual(stable["action_id"], terminal["action_id"])
        self.assertEqual(stable["status"], "resolved")
        self.assertEqual(len(load_json_lines(self.run / "events.jsonl")), events)

    def test_wait_does_not_refresh_worker_progress(self) -> None:
        self.bootstrap()
        send, _ = self.dispatch()
        self.record(send, {"transport_ack": {"sent": True}})
        before = replay(self.run)["dispatches"][send["dispatch_id"]].get(
            "last_progress_at"
        )
        wait = self.next()
        self.assertEqual(wait["type"], "wait")
        self.record(wait, {})
        after = replay(self.run)["dispatches"][send["dispatch_id"]].get(
            "last_progress_at"
        )
        self.assertEqual(after, before)

    def test_unanswered_status_expires_without_duplicate_or_progress_refresh(self) -> None:
        self.bootstrap()
        send, _ = self.dispatch()
        self.record(send, {"transport_ack": {"sent": True}})
        setup_path = self.run / "setup.json"
        setup = load_json(setup_path)
        setup["policies"]["liveness"]["stale_after_seconds"] = 0
        setup["policies"]["liveness"]["status_timeout_seconds"] = 0
        write_json(setup_path, setup)
        status = self.next()
        self.assertEqual(status["type"], "request_status")
        expired = self.next()
        self.assertEqual(expired["action_id"], status["action_id"])
        self.assertTrue(expired["expired"])
        self.assertIsNone(
            replay(self.run)["dispatches"][send["dispatch_id"]]["last_progress_at"]
        )
        recovery = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=None, dry_run=True, controller="test"
        ))
        self.assertEqual(recovery["classification"], "unanswered_status")

    def test_recovery_preserves_interrupted_dispatch_and_bootstraps_replacement(self) -> None:
        self.bootstrap()
        send, _ = self.dispatch()
        self.record(send, {"transport_ack": {"sent": True}})
        evidence = self.base / "evidence.json"
        write_json(evidence, {
            "started": False, "session_available": False,
            "recovery_check": "inspect workspace",
            "recovery_check_passed": True,
        })
        recovered = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=False, controller="test"
        ))
        self.assertEqual(recovered["classification"], "sent_unstarted")
        state = replay(self.run)
        self.assertEqual(
            state["dispatches"][send["dispatch_id"]]["status"], "interrupted"
        )
        self.assertNotIn("PARENT", state["sessions"])
        replacement = self.next()
        self.assertEqual(replacement["type"], "spawn_and_bootstrap")
        self.assertIn("checkpoint", replacement["prompt"].lower())

    def test_completed_unrecorded_gets_dedicated_action(self) -> None:
        self.bootstrap()
        send, _ = self.dispatch()
        self.record(send, {"transport_ack": {"sent": True}})
        evidence = self.base / "completed.json"
        write_json(evidence, {"result": True})
        recovered = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=False, controller="test"
        ))
        action = recovered["required_action"]
        self.assertEqual(action["type"], "reconcile_result")
        self.assertEqual(self.next()["action_id"], action["action_id"])

    def test_audit_rebuilds_each_projected_snapshot_without_contract_mutation(self) -> None:
        self.bootstrap()
        action, _ = self.dispatch()
        contract = self.run / "jobs/PARENT/contract.json"
        original_contract = contract.read_bytes()
        paths = [
            self.run / "run.json", self.run / "queue.json",
            self.run / "jobs/index.json",
            self.run / "jobs/PARENT/job.json",
            self.run / "jobs/PARENT/workflow.json",
            self.run / "jobs/PARENT/steps.json",
            self.run / "actions" / f"{action['action_id']}.json",
            self.run / "jobs/PARENT/dispatches" / f"{action['dispatch_id']}.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                path.write_text("{}", encoding="utf-8")
                result = jobctl.audit(argparse.Namespace(
                    run=self.run, rebuild=True
                ))
                self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(contract.read_bytes(), original_contract)

    def test_child_job_is_materialized_and_parent_waits_for_report_ack(self) -> None:
        self.bootstrap()
        action, dispatch = self.dispatch()
        response = self.finalize(action, dispatch, "blocked", "needs child analysis")
        response["result"]["proposed_jobs"] = [{
            "id": "CHILD", "title": "Analyze", "goal": "Analyze dependency",
            "role": "analyst", "workflow": {"nodes": [{
                "id": "analyze", "position": 1, "work_units": ["C1"],
                "acceptance_criteria": ["analysis ready"],
                "required_checks": ["review"], "prohibited_actions": ["parent work"],
                "checkpoint_policy": ["before_result"],
                "side_effect_class": "read_only", "recovery_check": "inspect report",
            }]},
        }]
        write_json(Path(response["result_path"]), response["result"])
        self.record(action, response)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["CHILD"]["parent_job_id"], "PARENT")
        self.assertEqual(state["jobs"]["PARENT"]["status"], "blocked")
        self.assertEqual(self.next()["job_id"], "CHILD")

    def test_migration_invalidates_ack_and_preserves_active_dispatch(self) -> None:
        self.bootstrap()
        send, _ = self.dispatch()
        manifest_path = self.run / "protocol/manifest.json"
        manifest = load_json(manifest_path)
        manifest["protocol_version"] = 2
        write_json(manifest_path, manifest)
        migrated = jobctl.migrate(argparse.Namespace(
            run=self.run, authorized_by="owner", reason="upgrade",
            controller="test",
        ))
        self.assertTrue(migrated["sessions_require_bootstrap"])
        state = replay(self.run)
        self.assertNotIn("PARENT", state["sessions"])
        self.assertEqual(
            state["dispatches"][send["dispatch_id"]]["status"], "interrupted"
        )
        self.assertEqual(self.next()["type"], "spawn_and_bootstrap")


def load_json_lines(path: Path) -> list[dict]:
    import json
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    unittest.main()
