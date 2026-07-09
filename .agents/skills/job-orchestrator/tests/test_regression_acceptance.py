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
    Lease,
    OrchestratorError,
    append_event,
    content_hash,
    load_json,
    make_event,
    replay,
    write_json,
)


class ControlPlaneAcceptanceTest(unittest.TestCase):
    """End-to-end regression coverage through the two public control-plane APIs."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.run = Path(jobctl.init_run(argparse.Namespace(
            goal="acceptance regression",
            run_id="acceptance",
            state_root=self.base,
            workspace=self.base,
            request="exercise public control-plane behavior",
            request_file=None,
            controller="controller-a",
        ))["run_root"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def node(
        node_id: str,
        position: int,
        units: list[str],
        *,
        side_effect_class: str = "workspace_write",
        unbounded_override: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": node_id,
            "position": position,
            "run_in": "job_session",
            "work_units": units,
            "acceptance_criteria": [f"{node_id} accepted"],
            "required_checks": [f"{node_id} checks pass"],
            "prohibited_actions": ["do not begin any later workflow node"],
            "checkpoint_policy": ["after_discovery", "after_each_batch", "before_blocker"],
            "side_effect_class": side_effect_class,
            "recovery_check": "inspect checkpoint and workspace before retry",
            "unbounded_override": unbounded_override,
        }

    def compile(self, nodes: list[dict] | None = None) -> None:
        definition = {
            "jobs": [{
                "id": "J001",
                "title": "Primary job",
                "goal": "Complete bounded work",
                "role": "Implementation",
                "priority": 50,
                "workspace": str(self.base),
                "allowed_edit_roots": [str(self.base)],
                "capabilities": ["edit"],
                "workflow": {
                    "nodes": nodes or [self.node("apply", 1, ["U1"])],
                },
            }],
        }
        path = self.base / "definition.json"
        write_json(path, definition)
        jobctl.compile_jobs(argparse.Namespace(
            run=self.run, definition=path, controller="controller-a",
        ))

    def next(self, controller: str = "controller-a") -> dict:
        return jobctl.next_action(argparse.Namespace(
            run=self.run, controller=controller,
        ))

    def record(self, action: dict, response: dict, controller: str = "controller-a") -> dict:
        path = self.base / f"response-{action['action_id']}.json"
        write_json(path, response)
        return jobctl.record(argparse.Namespace(
            run=self.run,
            action_id=action["action_id"],
            response=path,
            controller=controller,
        ))

    def acknowledgement(self, *, session_id: str = "session-1") -> dict:
        contract_path = self.run / "jobs/J001/contract.json"
        contract = load_json(contract_path)
        return workerctl.acknowledge(argparse.Namespace(
            contract=contract_path,
            protocol_version=3,
            protocol_sha256=contract["protocol"]["sha256"],
            job_id="J001",
            contract_revision=contract["revision"],
            current_node="apply",
            session_id=session_id,
        ))

    def bootstrap(self) -> dict:
        action = self.next()
        self.assertEqual(action["type"], "spawn_and_bootstrap")
        self.record(action, self.acknowledgement())
        dispatch_action = self.next()
        self.assertEqual(dispatch_action["type"], "send_dispatch")
        return dispatch_action

    def dispatch_path(self, action: dict) -> Path:
        return (
            self.run / "jobs/J001/dispatches" / f"{action['dispatch_id']}.json"
        )

    def finalize(
        self,
        action: dict,
        *,
        status: str = "completed",
        completed: list[str] | None = None,
        issues: list[str] | None = None,
    ) -> dict:
        dispatch_path = self.dispatch_path(action)
        dispatch = load_json(dispatch_path)
        completed = dispatch["work_units"] if completed is None else completed
        issues = issues or []
        workerctl.checkpoint(argparse.Namespace(
            dispatch=dispatch_path,
            phase="blocked" if status == "blocked" else "complete",
            completed_work_unit=completed,
            decision=[],
            issue=issues,
            artifact=[],
            next_action="return validated result",
        ))
        (self.run / "jobs/J001/report.md").write_text(
            "Acceptance evidence recorded.", encoding="utf-8"
        )
        return workerctl.finalize(argparse.Namespace(
            dispatch=dispatch_path,
            status=status,
            summary=f"{status} result",
            artifact=[],
            acceptance_evidence=[] if status == "blocked" else ["checks passed"],
            blocking_issue=issues,
            session_id="session-1",
        ))

    def test_rejects_every_wrong_acknowledgement_binding_without_advancing(self) -> None:
        self.compile()
        action = self.next()
        valid = self.acknowledgement()
        cases = {
            "wrong node": ("current_workflow_node_id", "later"),
            "wrong version": ("protocol_version", 2),
            "wrong revision": ("contract_revision", 99),
            "wrong hash": ("protocol_sha256", "0" * 64),
        }
        for label, (field, bad_value) in cases.items():
            with self.subTest(label=label):
                bad = json.loads(json.dumps(valid))
                bad["protocol_ack"][field] = bad_value
                with self.assertRaises(OrchestratorError):
                    self.record(action, bad)
                self.assertEqual(self.next()["action_id"], action["action_id"])

        mismatched_session = json.loads(json.dumps(valid))
        mismatched_session["session_id"] = "session-2"
        mismatched_session["protocol_ack"]["session_id"] = "session-1"
        with self.assertRaisesRegex(OrchestratorError, "session"):
            self.record(action, mismatched_session)
        self.assertNotIn("J001", replay(self.run)["sessions"])

    def test_fabricated_and_incomplete_results_never_advance_the_job(self) -> None:
        self.compile()
        action = self.bootstrap()
        response = self.finalize(action)
        response["result"]["nonce"] = "fabricated"
        with self.assertRaisesRegex(OrchestratorError, "binding"):
            self.record(action, response)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["J001"]["current_workflow_node_id"], "apply")
        self.assertNotEqual(state["jobs"]["J001"]["status"], "completed")

        response = self.finalize(action)
        (self.run / "jobs/J001/report.md").unlink()
        with self.assertRaisesRegex(OrchestratorError, "report"):
            self.record(action, response)
        self.assertNotEqual(replay(self.run)["jobs"]["J001"]["status"], "completed")

    def test_impossible_unknown_session_state_is_rejected_on_replay(self) -> None:
        self.compile()
        acknowledgement = self.acknowledgement()["protocol_ack"]
        acknowledgement["job_id"] = "UNKNOWN"
        event = make_event(
            self.run,
            "session_acknowledged",
            "impossible-session",
            acknowledgement,
        )
        append_event(self.run, event)
        with self.assertRaisesRegex(OrchestratorError, "unknown job"):
            replay(self.run)

    def test_completed_result_with_blocking_evidence_cannot_advance(self) -> None:
        self.compile()
        action = self.bootstrap()
        response = self.finalize(action)
        response["result"]["blocking_issues"] = ["Missing deployment authority"]
        write_json(Path(response["result_path"]), response["result"])
        with self.assertRaisesRegex(OrchestratorError, "blocking"):
            self.record(action, response)
        self.assertEqual(
            replay(self.run)["workflows"]["J001"]["nodes"][0]["status"], "ready"
        )

    def test_every_derived_snapshot_is_reported_and_rebuilt_deterministically(self) -> None:
        self.compile()
        self.bootstrap()
        derived = [
            self.run / "run.json",
            self.run / "queue.json",
            self.run / "jobs/index.json",
            self.run / "jobs/J001/job.json",
            self.run / "jobs/J001/workflow.json",
            self.run / "jobs/J001/steps.json",
            *sorted((self.run / "actions").glob("*.json")),
            *sorted((self.run / "jobs/J001/dispatches").glob("*.json")),
        ]
        originals = {path: path.read_bytes() for path in derived}
        contract = self.run / "jobs/J001/contract.json"
        contract_before = contract.read_bytes()
        for path in derived:
            with self.subTest(snapshot=str(path.relative_to(self.run))):
                for original_path, original_bytes in originals.items():
                    original_path.write_bytes(original_bytes)
                write_json(path, {"corrupted": True})
                first = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
                second = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
                self.assertFalse(first["ok"])
                self.assertEqual(first["issues"], second["issues"])
                relative = str(path.relative_to(self.run))
                self.assertTrue(any(relative in issue for issue in first["issues"]))
                rebuilt = jobctl.audit(argparse.Namespace(run=self.run, rebuild=True))
                self.assertTrue(rebuilt["ok"], rebuilt["issues"])
                self.assertEqual(load_json(path), json.loads(originals[path]))
                self.assertEqual(contract.read_bytes(), contract_before)

    def test_malformed_snapshot_is_auditable_and_rebuildable(self) -> None:
        self.compile()
        snapshot = self.run / "jobs/J001/workflow.json"
        snapshot.write_text("{interrupted", encoding="utf-8")
        report = jobctl.audit(argparse.Namespace(run=self.run, rebuild=False))
        self.assertFalse(report["ok"])
        self.assertTrue(any("workflow.json" in issue for issue in report["issues"]))
        rebuilt = jobctl.audit(argparse.Namespace(run=self.run, rebuild=True))
        self.assertTrue(rebuilt["ok"], rebuilt["issues"])

    def test_blocked_batch_preserves_current_node_and_precise_checkpoint(self) -> None:
        self.compile([
            self.node("apply", 1, ["U1", "U2"]),
            self.node("verify", 2, ["V1"]),
        ])
        action = self.bootstrap()
        issue = "Need an API credential from the user"
        response = self.finalize(
            action, status="blocked", completed=["U1"], issues=[issue]
        )
        self.record(action, response)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["J001"]["status"], "blocked")
        self.assertEqual(state["jobs"]["J001"]["current_workflow_node_id"], "apply")
        self.assertEqual(state["workflows"]["J001"]["nodes"][1]["status"], "pending")

    def test_partial_batch_cannot_execute_or_advance_to_a_later_node(self) -> None:
        units = [f"U{number}" for number in range(1, 10)]
        self.compile([
            self.node("apply", 1, units),
            self.node("verify", 2, ["V1"]),
        ])
        first = self.bootstrap()
        first_dispatch = load_json(self.dispatch_path(first))
        self.assertNotIn("V1", first_dispatch["work_units"])
        response = self.finalize(
            first, status="partial", completed=first_dispatch["work_units"]
        )
        self.record(first, response)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["J001"]["current_workflow_node_id"], "apply")
        self.assertEqual(state["workflows"]["J001"]["nodes"][1]["status"], "pending")
        second = self.next()
        self.assertEqual(load_json(self.dispatch_path(second))["work_units"], ["U9"])

    def test_explicit_unbounded_override_authorizes_the_whole_scope(self) -> None:
        units = [f"U{number}" for number in range(1, 10)]
        override = {
            "reason": "The operation is atomic",
            "authorized_by": "acceptance-test",
            "recovery_policy": "inspect every output before retry",
        }
        self.compile([self.node(
            "apply", 1, units, unbounded_override=override
        )])
        action = self.bootstrap()
        dispatch = load_json(self.dispatch_path(action))
        self.assertEqual(dispatch["work_units"], units)
        self.assertEqual(dispatch["unbounded_override"], override)

    def test_terminal_completion_is_recorded_once_and_next_is_stable(self) -> None:
        self.compile()
        action = self.bootstrap()
        self.record(action, self.finalize(action))
        terminal = self.next()
        self.assertEqual(terminal["type"], "run_complete")
        self.record(terminal, {"acknowledged": True})
        event_count = len((self.run / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines())
        duplicate = self.record(terminal, {"acknowledged": True})
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaisesRegex(OrchestratorError, "different response"):
            self.record(terminal, {"acknowledged": False})
        again = self.next()
        self.assertEqual(again["action_id"], terminal["action_id"])
        self.assertEqual(again["status"], "resolved")
        self.assertEqual(
            len((self.run / "events.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()),
            event_count,
        )

    def test_all_recovery_classifications_are_evidence_driven(self) -> None:
        base = {
            "transport": {},
            "side_effect_class": "workspace_write",
        }
        cases = [
            ("recorded_unsent", {}, {}),
            (
                "completed_unrecorded",
                {"transport": {"sent": True}},
                {"result": {"status": "completed"}},
            ),
            (
                "externally_effective_unacknowledged",
                {"transport": {"sent": True}},
                {"external_effect": True},
            ),
            (
                "running_resumable",
                {"transport": {"sent": True}},
                {"session_available": True, "checkpoint_valid": True, "started": True},
            ),
            (
                "safe_retry",
                {"transport": {"sent": True}, "side_effect_class": "read_only"},
                {"started": False},
            ),
            ("sent_unstarted", {"transport": {"sent": True}}, {"started": False}),
            ("unsafe_retry", {"transport": {"sent": True}}, {"started": True}),
        ]
        for expected, dispatch_changes, evidence in cases:
            with self.subTest(expected=expected):
                dispatch = {**base, **dispatch_changes}
                self.assertEqual(jobctl.classify(dispatch, evidence), expected)

    def test_unanswered_status_expires_without_refreshing_worker_progress(self) -> None:
        self.compile()
        setup = load_json(self.run / "setup.json")
        setup["policies"]["liveness"].update(
            stale_after_seconds=0, status_timeout_seconds=0
        )
        write_json(self.run / "setup.json", setup)
        dispatch_action = self.bootstrap()
        self.record(dispatch_action, {
            "transport_ack": {"sent": True, "sent_at": "2026-01-01T00:00:00Z"}
        })
        request = self.next()
        self.assertEqual(request["type"], "request_status")
        expired = self.next()
        self.assertEqual(expired["action_id"], request["action_id"])
        self.assertTrue(expired["expired"])
        recovery = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=None, dry_run=True, controller="controller-a"
        ))
        self.assertEqual(recovery["classification"], "unanswered_status")

    def test_session_loss_requires_replacement_bootstrap_before_domain_work(self) -> None:
        self.compile([self.node(
            "apply", 1, ["R1"], side_effect_class="read_only"
        )])
        dispatch_action = self.bootstrap()
        self.record(dispatch_action, {
            "transport_ack": {"sent": True, "sent_at": "2026-01-01T00:00:00Z"}
        })
        evidence = self.base / "lost-session.json"
        write_json(evidence, {
            "session_available": False,
            "started": False,
            "checkpoint_valid": False,
            "unstarted_proof": "transport reports the read-only command never started",
        })
        recovered = jobctl.recover(argparse.Namespace(
            run=self.run,
            evidence=evidence,
            dry_run=False,
            controller="controller-a",
        ))
        self.assertEqual(recovered["classification"], "safe_retry")
        self.assertEqual(recovered["required_action"], "bootstrap replacement session")
        replacement = self.next()
        self.assertEqual(replacement["type"], "spawn_and_bootstrap")
        self.assertNotEqual(replacement.get("session_id"), "session-1")
        mismatch = self.acknowledgement(session_id="session-2")
        mismatch["protocol_ack"]["contract_revision"] += 1
        with self.assertRaisesRegex(OrchestratorError, "revision"):
            self.record(replacement, mismatch)
        self.assertEqual(self.next()["action_id"], replacement["action_id"])

    def test_stale_checkpoint_never_makes_side_effecting_work_safe_to_retry(self) -> None:
        dispatch = {
            "transport": {"sent": True},
            "side_effect_class": "workspace_write",
        }
        evidence = {
            "session_available": True,
            "checkpoint_valid": False,
            "started": True,
            "external_effect": False,
        }
        self.assertEqual(jobctl.classify(dispatch, evidence), "unsafe_retry")

    def test_lease_contention_and_explicit_handoff(self) -> None:
        path = self.run / "acceptance.lock"
        owner = Lease(path, "controller-a", seconds=30)
        owner.acquire()
        contender = Lease(path, "controller-b", seconds=30)
        with self.assertRaisesRegex(OrchestratorError, "lease held"):
            contender.acquire()
        owner.handoff("controller-b")
        contender.acquire(handoff_from="controller-a")
        self.assertEqual(load_json(path)["controller_id"], "controller-b")
        with self.assertRaisesRegex(OrchestratorError, "another controller"):
            owner.renew()
        contender.release()

    def test_child_job_is_tracked_and_parent_waits_for_its_report(self) -> None:
        self.compile()
        action = self.bootstrap()
        issue = "A bounded child investigation is required"
        response = self.finalize(
            action, status="blocked", completed=[], issues=[issue]
        )
        response["result"]["proposed_jobs"] = [{
            "id": "CHILD-1",
            "title": "Investigate",
            "goal": "Produce bounded evidence",
            "parent_dispatch_id": action["dispatch_id"],
            "workflow": {
                "nodes": [self.node("investigate", 1, ["C1"])],
            },
        }]
        write_json(Path(response["result_path"]), response["result"])
        self.record(action, response)
        state = replay(self.run)
        self.assertEqual(state["jobs"]["CHILD-1"]["parent_job_id"], "J001")
        self.assertEqual(state["jobs"]["J001"]["status"], "blocked")
        child_action = self.next()
        self.assertEqual(child_action["type"], "spawn_and_bootstrap")
        self.assertEqual(child_action["job_id"], "CHILD-1")

    def test_version_two_fixture_is_unchanged_until_authorized_migration(self) -> None:
        self.compile()
        fixture = load_json(Path(__file__).with_name("fixtures") / "v2_run.json")
        manifest_path = self.run / "protocol/manifest.json"
        protocol_path = self.run / "protocol/job-protocol.md"
        contract_path = self.run / "jobs/J001/contract.json"
        manifest = load_json(manifest_path)
        v2_protocol = fixture["protocol_text"]
        protocol_path.write_text(v2_protocol, encoding="utf-8")
        v2_hash = content_hash(v2_protocol.encode("utf-8"))
        manifest.update(protocol_version=fixture["protocol_version"], sha256=v2_hash)
        write_json(manifest_path, manifest)
        contract = load_json(contract_path)
        contract.update(contract_version=fixture["contract_version"])
        contract["protocol"].update(
            version=fixture["protocol_version"], sha256=v2_hash
        )
        write_json(contract_path, contract)
        before = {
            "manifest": manifest_path.read_bytes(),
            "protocol": protocol_path.read_bytes(),
            "contract": contract_path.read_bytes(),
            "events": (self.run / "events.jsonl").read_bytes(),
        }

        recovery = jobctl.recover(argparse.Namespace(
            run=self.run, evidence=None, dry_run=True, controller="controller-a"
        ))
        self.assertEqual(recovery["classification"], "no_interrupted_dispatch")
        self.assertEqual(manifest_path.read_bytes(), before["manifest"])
        self.assertEqual(protocol_path.read_bytes(), before["protocol"])
        self.assertEqual(contract_path.read_bytes(), before["contract"])
        self.assertEqual((self.run / "events.jsonl").read_bytes(), before["events"])

        migrated = jobctl.migrate(argparse.Namespace(
            run=self.run,
            authorized_by="acceptance-test",
            reason="exercise explicit migration",
            controller="controller-a",
        ))
        self.assertTrue(migrated["sessions_require_bootstrap"])
        self.assertEqual(load_json(manifest_path)["protocol_version"], 3)
        self.assertEqual(load_json(contract_path)["contract_version"], 3)
        self.assertEqual(load_json(contract_path)["revision"], contract["revision"] + 1)


if __name__ == "__main__":
    unittest.main()
