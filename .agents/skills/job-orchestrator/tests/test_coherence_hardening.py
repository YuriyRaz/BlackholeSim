from __future__ import annotations

import argparse
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jobctl
import workerctl
from orchestrator_core import Lease, OrchestratorError, content_hash, load_json, read_jsonl, write_json


class CoherenceHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def new_run(self) -> Path:
        return Path(jobctl.init_run(argparse.Namespace(
            goal="coherence", run_id=None, state_root=self.base,
            workspace=self.base, request="test", request_file=None,
            controller="test",
        ))["run_root"])

    def compile_one(self, run: Path) -> None:
        definition = self.base / "definition.json"
        write_json(definition, {"jobs": [{
            "id": "J001", "title": "One", "goal": "Do one thing",
            "role": "worker", "workflow": {"nodes": [{
                "id": "apply", "position": 1, "work_units": ["U1"],
            }]},
        }]})
        jobctl.compile_jobs(argparse.Namespace(
            run=run, definition=definition, controller="test",
        ))

    def legacy_run(self) -> Path:
        run = self.base / "legacy"
        (run / "protocol").mkdir(parents=True)
        (run / "jobs/J001").mkdir(parents=True)
        protocol = "legacy worker protocol v2\n"
        digest = content_hash(protocol.encode())
        write_json(run / "run.json", {
            "schema_version": 1, "run_id": "legacy", "status": "active",
            "goal": "resume legacy work", "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "workspace": str(self.base), "state_root": str(self.base),
            "protocol": {"manifest_path": "protocol/manifest.json",
                         "version": 2, "sha256": digest},
            "revision": 1, "active_job_id": None, "active_dispatch_id": None,
        })
        (run / "protocol/job-protocol.md").write_text(protocol, encoding="utf-8")
        write_json(run / "protocol/manifest.json", {
            "protocol_version": 2, "file": "job-protocol.md", "sha256": digest,
        })
        (run / "events.jsonl").touch()
        write_json(run / "queue.json", {"mode": "sequential", "entries": [{
            "job_id": "J001", "priority": 50, "sequence": 1,
            "depends_on": [], "status": "queued",
        }]})
        write_json(run / "jobs/index.json", {"jobs": [{"id": "J001"}]})
        write_json(run / "jobs/J001/job.json", {
            "id": "J001", "title": "Legacy", "goal": "Preserve me",
            "role": "worker", "job_type": "implement", "priority": 50,
            "status": "queued", "current_workflow_node_id": "apply",
            "report_path": "report.md", "checkpoint_path": "checkpoint.md",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z", "revision": 1,
            "session": None,
        })
        write_json(run / "jobs/J001/workflow.json", {
            "session_policy": "persistent", "nodes": [{
                "id": "apply", "run_in": "job_session",
                "status": "queued", "command": "apply legacy change",
            }],
        })
        write_json(run / "jobs/J001/steps.json", {"steps": []})
        write_json(run / "jobs/J001/contract.json", {
            "contract_version": 2, "revision": 1, "job_id": "J001",
            "role": "worker", "goal": "Preserve me",
            "protocol": {"path": "../../protocol/job-protocol.md",
                         "version": 2, "sha256": digest},
            "report_path": "report.md", "checkpoint_path": "checkpoint.md",
        })
        (run / "jobs/J001/report.md").touch()
        (run / "jobs/J001/checkpoint.md").touch()
        return run

    def test_generated_prompts_include_required_worker_identity(self) -> None:
        run = self.new_run()
        self.assertTrue(run.name.startswith("RUN-"))
        self.compile_one(run)
        prompt = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))["prompt"]
        for flag in (
            "--protocol-version", "--protocol-sha256", "--job-id",
            "--contract-revision", "--current-node",
        ):
            self.assertIn(flag, prompt)
        self.assertIn("--session-id", prompt)
        self.assertIn("<transport-session-id>", prompt)

    def test_transcript_style_definition_is_normalized_before_dispatch(self) -> None:
        run = self.new_run()
        definition = self.base / "transcript-definition.json"
        write_json(definition, {"jobs": [{
            "id": "J001",
            "title": "visual-effects-03 Implementation",
            "goal": "Verify, fix, sync, archive, and commit",
            "role": "Implementation",
            "workflow": {"nodes": [
                {
                    "id": "verify",
                    "title": "Verify visual-effects-03 implementation",
                    "position": 1,
                    "run_in": "job_session",
                    "work_units": [{
                        "id": "verify-change",
                        "description": "Run openspec-verify-change",
                        "command": "/openspec-verify-change",
                    }],
                    "checks": ["verification completes"],
                    "prohibited_later_actions": ["do not sync yet"],
                    "checkpoint_policy": "after_batch",
                    "side_effect_class": "read_only",
                    "recovery_check": "verify_change_exists",
                },
                {
                    "id": "fix-findings",
                    "title": "Fix verification findings",
                    "position": 2,
                    "run_in": "job_session",
                    "work_units": ["fix-issues"],
                    "checkpoint_policy": "after_batch",
                    "side_effect_class": "code_change",
                    "recovery_check": "fixes_applied",
                },
                {
                    "id": "commit-push",
                    "title": "Commit and push to main",
                    "position": 3,
                    "run_in": "job_session",
                    "work_units": ["commit"],
                    "checkpoint_policy": "after_batch",
                    "side_effect_class": "external_effect",
                    "recovery_check": "commit_pushed",
                },
            ]},
        }]})

        self.assertEqual(
            jobctl.compile_jobs(argparse.Namespace(
                run=run, definition=definition, controller="test",
            ))["compiled"],
            ["J001"],
        )
        state = jobctl.replay(run)
        nodes = state["workflows"]["J001"]["nodes"]
        self.assertEqual(nodes[0]["work_units"], ["verify-change"])
        self.assertEqual(nodes[0]["required_checks"], ["verification completes"])
        self.assertEqual(nodes[0]["prohibited_actions"], ["do not sync yet"])
        self.assertEqual(nodes[0]["checkpoint_policy"], ["after_batch"])
        self.assertEqual(nodes[1]["side_effect_class"], "workspace_write")
        self.assertEqual(nodes[2]["side_effect_class"], "repository")

        bootstrap = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        response_path = self.base / "ack-normalized.json"
        write_json(response_path, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="verify", session_id="session",
        )))
        jobctl.record(argparse.Namespace(
            run=run, action_id=bootstrap["action_id"],
            response=response_path, controller="test",
        ))
        dispatch = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        dispatch_doc = load_json(
            run / "jobs/J001/dispatches" / f"{dispatch['dispatch_id']}.json"
        )
        self.assertEqual(dispatch_doc["work_units"], ["verify-change"])
        self.assertEqual(dispatch_doc["checkpoint_policy"], ["after_batch"])

    def test_invalid_definition_is_rejected_before_journal_mutation(self) -> None:
        run = self.new_run()
        definition = self.base / "bad-definition.json"
        write_json(definition, {"jobs": [{
            "id": "J001",
            "title": "Bad",
            "goal": "Bad",
            "role": "Implementation",
            "workflow": {"nodes": [{
                "id": "apply",
                "position": 1,
                "work_units": [{"description": "missing stable id"}],
            }]},
        }]})
        before = read_jsonl(run / "events.jsonl")
        with self.assertRaisesRegex(OrchestratorError, "work_units"):
            jobctl.compile_jobs(argparse.Namespace(
                run=run, definition=definition, controller="test",
            ))
        self.assertEqual(read_jsonl(run / "events.jsonl"), before)
        self.assertTrue(jobctl.audit(argparse.Namespace(
            run=run, rebuild=False,
        ))["ok"])

    def test_repeated_compile_skips_existing_jobs_without_correlation_error(self) -> None:
        run = self.new_run()
        definition = self.base / "definition.json"
        write_json(definition, {"jobs": [{
            "id": "J001", "title": "One", "goal": "Do one thing",
            "role": "worker", "workflow": {"nodes": [{
                "id": "apply", "position": 1, "work_units": ["U1"],
            }]},
        }]})
        first = jobctl.compile_jobs(argparse.Namespace(
            run=run, definition=definition, controller="test",
        ))
        second = jobctl.compile_jobs(argparse.Namespace(
            run=run, definition=definition, controller="test",
        ))
        self.assertEqual(first["compiled"], ["J001"])
        self.assertEqual(second["compiled"], [])
        self.assertEqual(second["already_compiled"], ["J001"])

    def test_audit_detects_static_contract_content_mutation(self) -> None:
        run = self.new_run()
        self.compile_one(run)
        contract_path = run / "jobs/J001/contract.json"
        contract = load_json(contract_path)
        contract["goal"] = "silently changed"
        write_json(contract_path, contract)
        result = jobctl.audit(argparse.Namespace(run=run, rebuild=False))
        self.assertFalse(result["ok"])
        self.assertIn("J001 static contract hash mismatch", result["issues"])

    def test_child_request_lifecycle_waits_for_report_acknowledgement(self) -> None:
        run = self.new_run()
        self.compile_one(run)

        def record(action: dict, response: dict) -> None:
            path = self.base / f"{action['action_id']}.json"
            write_json(path, response)
            jobctl.record(argparse.Namespace(
                run=run, action_id=action["action_id"], response=path,
                controller="test",
            ))

        bootstrap = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        record(bootstrap, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="parent-session",
        )))
        send = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        parent_dispatch = run / "jobs/J001/dispatches" / f"{send['dispatch_id']}.json"
        workerctl.checkpoint(argparse.Namespace(
            dispatch=parent_dispatch, phase="blocked", completed_work_unit=[],
            decision=[], issue=["child evidence required"], artifact=[],
            next_action="request child",
        ))
        (run / "jobs/J001/report.md").write_text("blocked", encoding="utf-8")
        result = workerctl.finalize(argparse.Namespace(
            dispatch=parent_dispatch, status="blocked", summary="needs child",
            artifact=[], acceptance_evidence=[],
            blocking_issue=["child evidence required"],
            session_id="parent-session",
        ))
        result["result"]["proposed_jobs"] = [{
            "id": "CHILD", "goal": "Gather evidence", "title": "Child",
            "parent_dispatch_id": send["dispatch_id"],
            "workflow": {"nodes": [{
                "id": "investigate", "position": 1, "work_units": ["C1"],
            }]},
        }]
        write_json(Path(result["result_path"]), result["result"])
        record(send, result)
        events = [event["type"] for event in read_jsonl(run / "events.jsonl")]
        self.assertLess(events.index("child_job_requested"),
                        events.index("child_job_validated"))
        self.assertLess(events.index("child_job_validated"),
                        events.index("child_job_materialized"))

        child_bootstrap = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        self.assertEqual(child_bootstrap["job_id"], "CHILD")
        record(child_bootstrap, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/CHILD/contract.json",
            current_node="investigate", session_id="child-session",
        )))
        child_send = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        child_dispatch = (
            run / "jobs/CHILD/dispatches" / f"{child_send['dispatch_id']}.json"
        )
        workerctl.checkpoint(argparse.Namespace(
            dispatch=child_dispatch, phase="complete",
            completed_work_unit=["C1"], decision=[], issue=[], artifact=[],
            next_action="return result",
        ))
        (run / "jobs/CHILD/report.md").write_text("evidence", encoding="utf-8")
        child_result = workerctl.finalize(argparse.Namespace(
            dispatch=child_dispatch, status="completed", summary="done",
            artifact=[], acceptance_evidence=["evidence gathered"],
            blocking_issue=[], session_id="child-session",
        ))
        record(child_send, child_result)
        route = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        self.assertEqual(route["type"], "route_resolution")
        self.assertTrue(route["child_request_ids"])
        record(route, {"acknowledged": True})
        states = {
            request["status"]
            for request in jobctl.replay(run)["child_requests"].values()
        }
        self.assertEqual(states, {"acknowledged"})

    def test_eventless_v2_is_preserved_and_imported_before_migration(self) -> None:
        run = self.legacy_run()
        recovery = jobctl.recover(argparse.Namespace(
            run=run, evidence=None, dry_run=True, controller="test",
        ))
        self.assertEqual(recovery["classification"], "legacy_v2_unchanged")
        self.assertEqual((run / "events.jsonl").read_bytes(), b"")
        jobctl.migrate(argparse.Namespace(
            run=run, authorized_by="owner", reason="upgrade", controller="test",
        ))
        self.assertTrue((run / "jobs/J001/job.json").is_file())
        self.assertIn("J001", load_json(run / "jobs/index.json")["jobs"])
        self.assertEqual(load_json(run / "jobs/J001/contract.json")["contract_version"], 3)
        self.assertIn("job_compiled", [event["type"] for event in read_jsonl(
            run / "events.jsonl"
        )])

    def test_migration_journal_replays_after_static_install_crash(self) -> None:
        run = self.legacy_run()
        real_install = jobctl._install_migration_static
        with mock.patch.object(
            jobctl, "_install_migration_static",
            side_effect=RuntimeError("simulated crash"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                jobctl.migrate(argparse.Namespace(
                    run=run, authorized_by="owner", reason="upgrade",
                    controller="test",
                ))
        self.assertEqual(load_json(run / "protocol/manifest.json")["protocol_version"], 2)
        with mock.patch.object(jobctl, "_install_migration_static", real_install):
            result = jobctl.migrate(argparse.Namespace(
                run=run, authorized_by="owner", reason="upgrade",
                controller="test",
            ))
        self.assertTrue(result["resumed"])
        self.assertEqual(load_json(run / "protocol/manifest.json")["protocol_version"], 3)
        self.assertIn("J001", load_json(run / "jobs/index.json")["jobs"])

    def test_eventless_v2_partial_import_resumes_each_missing_job(self) -> None:
        run = self.legacy_run()
        shutil.copytree(run / "jobs/J001", run / "jobs/J002")
        job = load_json(run / "jobs/J002/job.json")
        job["id"] = "J002"
        job["title"] = "Second legacy job"
        write_json(run / "jobs/J002/job.json", job)
        contract = load_json(run / "jobs/J002/contract.json")
        contract["job_id"] = "J002"
        write_json(run / "jobs/J002/contract.json", contract)
        queue = load_json(run / "queue.json")
        queue["entries"].append({
            "job_id": "J002", "priority": 40, "sequence": 2,
            "depends_on": [], "status": "queued",
        })
        write_json(run / "queue.json", queue)
        write_json(run / "jobs/index.json", {
            "jobs": [{"id": "J001"}, {"id": "J002"}],
        })

        real_append = jobctl.append_event
        append_count = 0

        def interrupt_third_append(*args, **kwargs):
            nonlocal append_count
            append_count += 1
            if append_count == 3:
                raise OSError("simulated crash during legacy import")
            return real_append(*args, **kwargs)

        with mock.patch.object(jobctl, "append_event", side_effect=interrupt_third_append):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                jobctl.migrate(argparse.Namespace(
                    run=run, authorized_by="test", reason="upgrade",
                    controller="test",
                ))

        migrated = jobctl.migrate(argparse.Namespace(
            run=run, authorized_by="test", reason="upgrade",
            controller="test",
        ))
        self.assertTrue(migrated["migrated"])
        self.assertEqual(
            set(load_json(run / "jobs/index.json")["jobs"]),
            {"J001", "J002"},
        )

    def test_same_controller_cannot_steal_a_live_lease(self) -> None:
        path = self.base / "lease.json"
        owner = Lease(path, "controller", seconds=30)
        owner.acquire()
        with self.assertRaisesRegex(OrchestratorError, "lease held"):
            Lease(path, "controller", seconds=30).acquire()
        owner.release()

    def test_recorded_unsent_recovery_invalidates_send_before_rebootstrap(self) -> None:
        run = self.new_run()
        self.compile_one(run)
        bootstrap = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        response_path = self.base / "ack.json"
        write_json(response_path, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="session",
        )))
        jobctl.record(argparse.Namespace(
            run=run, action_id=bootstrap["action_id"], response=response_path,
            controller="test",
        ))
        send = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        recovered = jobctl.recover(argparse.Namespace(
            run=run, evidence=None, dry_run=False, controller="test",
        ))
        self.assertEqual(recovered["classification"], "recorded_unsent")
        replacement = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        self.assertEqual(replacement["type"], "spawn_and_bootstrap")
        self.assertEqual(
            jobctl.replay(run)["actions"][send["action_id"]]["status"], "resolved"
        )
        write_json(response_path, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="replacement-session",
        )))
        jobctl.record(argparse.Namespace(
            run=run, action_id=replacement["action_id"], response=response_path,
            controller="test",
        ))
        resumed = jobctl.next_action(argparse.Namespace(
            run=run, controller="test",
        ))
        self.assertEqual(resumed["type"], "send_dispatch")
        self.assertEqual(resumed["dispatch_id"], send["dispatch_id"])
        self.assertEqual(
            jobctl.replay(run)["dispatches"][send["dispatch_id"]]["session_id"],
            "replacement-session",
        )

    def test_sent_side_effect_recovery_rejects_unstructured_evidence(self) -> None:
        run = self.new_run()
        self.compile_one(run)
        bootstrap = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        response_path = self.base / "ack-recovery.json"
        write_json(response_path, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="session",
        )))
        jobctl.record(argparse.Namespace(
            run=run, action_id=bootstrap["action_id"], response=response_path,
            controller="test",
        ))
        send = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        transport = self.base / "sent.json"
        write_json(transport, {"transport_ack": {"sent": True}})
        jobctl.record(argparse.Namespace(
            run=run, action_id=send["action_id"], response=transport,
            controller="test",
        ))
        evidence = self.base / "bare-evidence.json"
        write_json(evidence, {"started": False, "session_available": False})
        with self.assertRaisesRegex(
            OrchestratorError, "matching recovery_check"
        ):
            jobctl.recover(argparse.Namespace(
                run=run, evidence=evidence, dry_run=True, controller="test",
            ))
        write_json(evidence, {
            "started": False,
            "session_available": False,
            "recovery_check": load_json(
                run / "jobs/J001/dispatches" / f"{send['dispatch_id']}.json"
            )["recovery_check"],
            "recovery_check_passed": False,
        })
        with self.assertRaisesRegex(OrchestratorError, "must pass"):
            jobctl.recover(argparse.Namespace(
                run=run, evidence=evidence, dry_run=True, controller="test",
            ))

    def test_invalid_checkpoint_does_not_replace_existing_artifacts(self) -> None:
        run = self.new_run()
        self.compile_one(run)
        bootstrap = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        response_path = self.base / "ack-checkpoint.json"
        write_json(response_path, workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="session",
        )))
        jobctl.record(argparse.Namespace(
            run=run, action_id=bootstrap["action_id"], response=response_path,
            controller="test",
        ))
        send = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        dispatch = run / "jobs/J001/dispatches" / f"{send['dispatch_id']}.json"
        checkpoint = run / "jobs/J001/checkpoint.md"
        checkpoint.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(OrchestratorError, "outside its dispatch"):
            workerctl.checkpoint(argparse.Namespace(
                dispatch=dispatch, phase="work",
                completed_work_unit=["NOT-A-WORK-UNIT"],
                decision=[], issue=[], artifact=[], next_action="continue",
            ))
        self.assertEqual(checkpoint.read_text(encoding="utf-8"), "original")
        self.assertFalse((run / "jobs/J001/progress.json").exists())

    def test_record_resumes_after_transition_before_action_resolution(self) -> None:
        run = self.new_run()
        self.compile_one(run)
        action = jobctl.next_action(argparse.Namespace(run=run, controller="test"))
        response = workerctl.acknowledge(argparse.Namespace(
            contract=run / "jobs/J001/contract.json",
            current_node="apply", session_id="session",
        ))
        response_path = self.base / "crash-ack.json"
        write_json(response_path, response)
        real_mutate = jobctl.mutate
        calls = 0

        def crash_before_resolution(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("simulated record crash")
            return real_mutate(*args, **kwargs)

        with mock.patch.object(jobctl, "mutate", side_effect=crash_before_resolution):
            with self.assertRaisesRegex(RuntimeError, "simulated record crash"):
                jobctl.record(argparse.Namespace(
                    run=run, action_id=action["action_id"],
                    response=response_path, controller="test",
                ))
        self.assertEqual(
            jobctl.replay(run)["actions"][action["action_id"]]["status"],
            "unresolved",
        )
        jobctl.record(argparse.Namespace(
            run=run, action_id=action["action_id"],
            response=response_path, controller="test",
        ))
        state = jobctl.replay(run)
        self.assertEqual(state["actions"][action["action_id"]]["status"], "resolved")
        self.assertEqual(state["sessions"]["J001"]["session_id"], "session")


if __name__ == "__main__":
    unittest.main()
