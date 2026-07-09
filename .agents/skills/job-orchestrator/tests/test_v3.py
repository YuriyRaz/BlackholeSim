from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jobctl
import workerctl
from orchestrator_core import (
    OrchestratorError, append_event, load_json, make_event, replay, validate_dispatch,
    write_json,
)


class V3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.run = Path(jobctl.init_run(argparse.Namespace(
            goal="test", run_id="test-run", state_root=self.base,
            workspace=self.base, request="test request", request_file=None,
            controller="test",
        ))["run_root"])
        definition = {
            "jobs": [{
                "id": "J001", "title": "Implement", "goal": "Implement two units",
                "role": "Implementation", "priority": 50,
                "workspace": str(self.base),
                "allowed_edit_roots": [str(self.base)],
                "capabilities": ["edit"],
                "workflow": {"nodes": [{
                    "id": "apply", "position": 1, "run_in": "job_session",
                    "work_units": ["U1", "U2"],
                    "acceptance_criteria": ["tests pass"],
                    "required_checks": ["unit tests"],
                    "prohibited_actions": ["later nodes"],
                    "checkpoint_policy": ["after_discovery"],
                    "side_effect_class": "workspace_write",
                    "recovery_check": "inspect workspace",
                }]}
            }]
        }
        self.definition = self.base / "definition.json"
        write_json(self.definition, definition)
        jobctl.compile_jobs(argparse.Namespace(
            run=self.run, definition=self.definition, controller="test"
        ))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def next(self):
        return jobctl.next_action(argparse.Namespace(run=self.run, controller="test"))

    def record(self, action, value):
        path = self.base / f"{action['action_id']}.json"
        write_json(path, value)
        return jobctl.record(argparse.Namespace(
            run=self.run, action_id=action["action_id"], response=path, controller="test"
        ))

    def bootstrap(self):
        action = self.next()
        self.assertEqual(action["type"], "spawn_and_bootstrap")
        ack = workerctl.acknowledge(argparse.Namespace(
            contract=self.run / "jobs/J001/contract.json", current_node="apply"
        ))
        ack["session_id"] = "session-1"
        self.record(action, ack)

    def test_next_and_record_are_idempotent(self):
        action = self.next()
        self.assertEqual(action["action_id"], self.next()["action_id"])
        ack = workerctl.acknowledge(argparse.Namespace(
            contract=self.run / "jobs/J001/contract.json", current_node="apply"
        ))
        ack["session_id"] = "session-1"
        self.record(action, ack)
        self.assertTrue(self.record(action, ack)["duplicate"])

    def test_duplicate_event_and_stale_revision(self):
        event = make_event(self.run, "run_status", "same", {"status": "active"})
        self.assertTrue(append_event(self.run, event))
        self.assertFalse(append_event(self.run, event))
        stale = {**event, "event_id": "EV-other", "correlation_id": "other"}
        with self.assertRaisesRegex(OrchestratorError, "stale revision"):
            append_event(self.run, stale)

    def test_prompt_separation_and_exactly_one_dispatch(self):
        bootstrap = self.next()
        self.assertNotIn("work_units", bootstrap["prompt"])
        self.assertIn("job subagent", bootstrap["prompt"])
        self.assertIn("root must not execute", bootstrap["prompt"])
        self.bootstrap_record_existing(bootstrap)
        action = self.next()
        self.assertEqual(action["type"], "send_dispatch")
        self.assertIn("job subagent", action["prompt"])
        self.assertIn("root must not execute", action["prompt"])
        self.assertEqual(action["prompt"].count(".json"), 1)
        state = replay(self.run)
        self.assertEqual(len(state["dispatches"]), 1)
        self.assertEqual(action["action_id"], self.next()["action_id"])

    def bootstrap_record_existing(self, action):
        ack = workerctl.acknowledge(argparse.Namespace(
            contract=self.run / "jobs/J001/contract.json", current_node="apply"
        ))
        ack["session_id"] = "session-1"
        self.record(action, ack)

    def test_worker_checkpoint_finalize_and_partial_node(self):
        self.bootstrap()
        action = self.next()
        dispatch_path = self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        self.assertTrue(workerctl.inspect(argparse.Namespace(
            dispatch=dispatch_path, nonce=None
        ))["valid"])
        progress = workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path, phase="batch_complete",
            completed_work_unit=["U1"], decision=[], issue=[], artifact=[],
            next_action="return partial result",
        ))
        (self.run / "jobs/J001/report.md").write_text("U1 complete", encoding="utf-8")
        final = workerctl.finalize(argparse.Namespace(
            dispatch=dispatch_path, status="partial", summary="one unit done",
            artifact=[], acceptance_evidence=["U1 checked"], blocking_issue=[],
        ))
        self.record(action, final)
        state = replay(self.run)
        node = state["workflows"]["J001"]["nodes"][0]
        self.assertEqual(node["status"], "ready")
        self.assertEqual(node["completed_work_units"], ["U1"])

    def test_forward_run_multiple_batches_completion_and_audit(self):
        self.bootstrap()
        first = self.next()
        first_path = self.run / "jobs/J001/dispatches" / f"{first['dispatch_id']}.json"
        workerctl.checkpoint(argparse.Namespace(
            dispatch=first_path, phase="partial", completed_work_unit=["U1"],
            decision=[], issue=[], artifact=[], next_action="finalize partial",
        ))
        (self.run / "jobs/J001/report.md").write_text("U1 complete", encoding="utf-8")
        partial = workerctl.finalize(argparse.Namespace(
            dispatch=first_path, status="partial", summary="U1 complete",
            artifact=[], acceptance_evidence=["U1 verified"], blocking_issue=[],
        ))
        self.record(first, partial)
        second = self.next()
        self.assertNotEqual(first["action_id"], second["action_id"])
        second_path = self.run / "jobs/J001/dispatches" / f"{second['dispatch_id']}.json"
        self.assertEqual(load_json(second_path)["work_units"], ["U2"])
        workerctl.checkpoint(argparse.Namespace(
            dispatch=second_path, phase="complete", completed_work_unit=["U2"],
            decision=[], issue=[], artifact=[], next_action="finalize",
        ))
        (self.run / "jobs/J001/report.md").write_text("U1 and U2 complete", encoding="utf-8")
        done = workerctl.finalize(argparse.Namespace(
            dispatch=second_path, status="completed", summary="all done",
            artifact=[], acceptance_evidence=["suite passed"], blocking_issue=[],
        ))
        self.record(second, done)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["J001"]["status"], "completed")
        self.assertEqual(self.next()["type"], "run_complete")
        self.assertTrue(jobctl.audit(argparse.Namespace(
            run=self.run, rebuild=False
        ))["ok"])

    def test_worker_rejects_outside_artifact(self):
        self.bootstrap()
        action = self.next()
        dispatch_path = self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path, phase="done", completed_work_unit=["U1", "U2"],
            decision=[], issue=[], artifact=[], next_action="finalize",
        ))
        (self.run / "jobs/J001/report.md").write_text("done", encoding="utf-8")
        outside = self.base / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(OrchestratorError, "outside worker-owned"):
            workerctl.finalize(argparse.Namespace(
                dispatch=dispatch_path, status="completed", summary="done",
                artifact=[str(outside)], acceptance_evidence=["tests"],
                blocking_issue=[],
            ))

    def test_bounds_require_explicit_override(self):
        dispatch = {
            "schema_version": 3, "dispatch_id": "D", "job_id": "J",
            "workflow_node_id": "N", "nonce": "x", "contract_revision": 1,
            "protocol_sha256": "0" * 64, "work_units": list("abc"),
            "acceptance_criteria": ["a"], "required_checks": ["c"],
            "prohibited_actions": ["p"], "checkpoint_policy": ["after"],
            "side_effect_class": "workspace_write", "recovery_check": "check",
            "status": "recorded",
        }
        policy = {"dispatch_bounds": {"max_work_units": 2, "max_edit_roots": 4,
                                     "max_estimated_minutes": 90,
                                     "require_override_when_exceeded": True}}
        with self.assertRaisesRegex(OrchestratorError, "explicit override"):
            validate_dispatch(dispatch, policy)
        dispatch["unbounded_override"] = {
            "reason": "atomic operation", "authorized_by": "user",
            "recovery_policy": "inspect all outputs",
        }
        validate_dispatch(dispatch, policy)

    def test_recovery_never_blindly_retries_external_effect(self):
        self.bootstrap()
        action = self.next()
        evidence = self.base / "evidence.json"
        write_json(evidence, {
            "external_effect": True, "started": True,
            "recovery_check": "inspect workspace",
            "recovery_check_passed": True,
        })
        result = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=True, controller="test"
        ))
        self.assertEqual(result["classification"], "recorded_unsent")
        dispatch_path = self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        dispatch = load_json(dispatch_path)
        dispatch["transport"] = {"sent": True}
        event = make_event(self.run, "dispatch_updated", "sent", {
            "dispatch_id": dispatch["dispatch_id"], "changes": {"transport": {"sent": True}}
        })
        append_event(self.run, event)
        result = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=True, controller="test"
        ))
        self.assertEqual(result["classification"], "externally_effective_unacknowledged")

    def test_audit_rebuilds_interrupted_snapshot(self):
        event = make_event(self.run, "run_status", "interrupted", {"status": "recovering"})
        append_event(self.run, event)
        result = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertFalse(result["ok"])
        rebuilt = jobctl.audit(argparse.Namespace(run=self.run, rebuild=True))
        self.assertTrue(rebuilt["ok"])
        self.assertEqual(load_json(self.run / "run.json")["status"], "recovering")

    def test_state_integrity_gate_clean_resume_uses_normal_next_loop(self):
        self.bootstrap()
        result = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertTrue(result["ok"])
        self.assertEqual(result["findings"][0]["classification"], "clean")
        self.assertFalse(result["blocks_normal_resume"])
        self.assertEqual(self.next()["type"], "send_dispatch")

    def test_audit_classifies_and_rebuilds_snapshot_drift_and_stale_indexes(self):
        self.bootstrap()
        write_json(self.run / "jobs/index.json", {"jobs": []})
        write_json(self.run / "queue.json", {"mode": "sequential", "entries": []})
        job = load_json(self.run / "jobs/J001/job.json")
        job["status"] = "completed"
        write_json(self.run / "jobs/J001/job.json", job)
        result = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        classes = {item["classification"] for item in result["findings"]}
        self.assertIn("stale_index_or_queue", classes)
        self.assertIn("derived_snapshot_drift", classes)
        rebuilt = jobctl.audit(argparse.Namespace(run=self.run, rebuild=True))
        self.assertNotIn("stale_index_or_queue", {
            item["classification"] for item in rebuilt["findings"]
        })
        self.assertEqual(load_json(self.run / "jobs/index.json")["jobs"], ["J001"])

    def test_audit_blocks_active_idle_contradiction(self):
        action = {
            "schema_version": 3,
            "action_id": "ACT-idle",
            "type": "ask_user",
            "run_id": "test-run",
            "job_id": "J001",
            "status": "unresolved",
            "correlation_id": "J001:apply",
            "created_at": jobctl.utc_now(),
            "prompt": "diagnose",
        }
        append_event(self.run, make_event(
            self.run, "action_created", action["action_id"], {"action": action}
        ))
        run = load_json(self.run / "run.json")
        run.update(status="active", active_job_id=None, active_dispatch_id=None)
        write_json(self.run / "run.json", run)
        write_json(self.run / "queue.json", {"mode": "sequential", "entries": []})
        result = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertTrue(result["active_idle_contradictions"])
        self.assertTrue(result["blocks_normal_resume"])
        self.assertIn("journal_corrupt_or_insufficient", {
            item["classification"] for item in result["findings"]
        })

    def test_recover_reconciles_completed_result_not_applied(self):
        self.bootstrap()
        action = self.next()
        dispatch_path = self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path, phase="complete",
            completed_work_unit=["U1", "U2"], decision=[], issue=[],
            artifact=[], next_action="finalize",
        ))
        (self.run / "jobs/J001/report.md").write_text("done", encoding="utf-8")
        final = workerctl.finalize(argparse.Namespace(
            dispatch=dispatch_path, status="completed", summary="done",
            artifact=[], acceptance_evidence=["tests"], blocking_issue=[],
        ))
        audit = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertIn("completed_result_not_applied", {
            item["classification"] for item in audit["findings"]
        })
        evidence = self.base / "recovery-evidence.json"
        write_json(evidence, {"response": final})
        dry_run = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=True, controller="test"
        ))
        self.assertEqual(dry_run["finding"], "completed_result_not_applied")
        self.assertEqual(dry_run["safe_next_action"], "apply validated worker result")
        recovered = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=evidence, dry_run=False, controller="test"
        ))
        self.assertEqual(recovered["required_action"], "continue normal jobctl next loop")
        self.assertEqual(replay(self.run)["jobs"]["J001"]["status"], "completed")

    def test_progress_without_validated_result_is_evidence_only(self):
        self.bootstrap()
        action = self.next()
        dispatch_path = self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path, phase="complete",
            completed_work_unit=["U1", "U2"], decision=[], issue=[],
            artifact=[], next_action="finalize",
        ))
        audit = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertIn("interrupted_dispatch_sent_no_result", {
            item["classification"] for item in audit["findings"]
        })
        self.assertNotEqual(replay(self.run)["jobs"]["J001"]["status"], "completed")

    def test_side_effect_recovery_check_blocks_unsafe_retry(self):
        self.bootstrap()
        action = self.next()
        self.record(action, {"transport_ack": {"sent": True}})
        audit = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertTrue(audit["side_effect_blockers"])
        self.assertIn("external_effect_unknown", {
            item["classification"] for item in audit["findings"]
        })
        evidence = self.base / "unsafe-side-effect.json"
        write_json(evidence, {"started": False, "session_available": False})
        with self.assertRaisesRegex(OrchestratorError, "matching recovery_check"):
            jobctl.recover(argparse.Namespace(
                run=self.run, evidence=evidence, dry_run=True, controller="test"
            ))

    def test_protocol_hash_mismatch_blocks_automatic_recovery(self):
        protocol = self.run / "protocol/job-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8") + "\nmutation\n",
            encoding="utf-8",
        )
        result = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertFalse(result["protocol_hash_status"]["matches"])
        self.assertFalse(result["protocol_hash_status"]["safe_for_automatic_recovery"])
        self.assertIn("journal_corrupt_or_insufficient", {
            item["classification"] for item in result["findings"]
        })

    def test_v2_run_requires_explicit_migration(self):
        manifest_path = self.run / "protocol/manifest.json"
        manifest = load_json(manifest_path)
        manifest["protocol_version"] = 2
        write_json(manifest_path, manifest)
        run_before = load_json(self.run / "run.json")
        self.assertEqual(load_json(manifest_path)["protocol_version"], 2)
        with self.assertRaisesRegex(OrchestratorError, "requires"):
            jobctl.migrate(argparse.Namespace(
                run=self.run, authorized_by="", reason="", controller="test"
            ))
        self.assertEqual(load_json(manifest_path)["protocol_version"], 2)
        result = jobctl.migrate(argparse.Namespace(
            run=self.run, authorized_by="test-user", reason="test migration",
            controller="test",
        ))
        self.assertTrue(result["sessions_require_bootstrap"])
        self.assertEqual(load_json(manifest_path)["protocol_version"], 3)
        self.assertEqual(run_before["run_id"], load_json(self.run / "run.json")["run_id"])


if __name__ == "__main__":
    unittest.main()
