"""Real jobctl tests for authenticated typed response and expansion intake."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from graph_v6 import GraphState, compute_graph_digest  # noqa: E402
from orchestrator_core import (  # noqa: E402
    canonical_bytes,
    content_hash,
    load_trusted_run,
    receipt_auth_tag,
    write_json,
)


class ResponseIntakeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        request = self.root / "request.md"
        request.write_text("intake test\n", encoding="utf-8")
        initialized = self.cli(
            "init", "--request-file", str(request), "--goal", "intake",
            "--run-id", "intake-run", "--state-root", str(self.root),
            "--workspace", str(self.root), "--test-harness",
        )
        self.run_root = Path(initialized["run_root"])
        self.binding = initialized["adapter_binding"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *args: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "jobctl.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def write(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def sign(self, receipt: dict) -> dict:
        receipt["auth_tag"] = receipt_auth_tag(self.binding, receipt)
        return receipt

    def register(self, role: str) -> None:
        root_job = load_trusted_run(self.run_root)[0]["job_ids"][0]
        definition = {
            "schema_version": 6,
            "jobs": [{
                "job_id": "JOB-PRODUCER",
                "title": "Producer",
                "role": role,
                "purpose_key": "produce",
            }],
            "edges": [{
                "source_job_id": root_job,
                "target_job_id": "JOB-PRODUCER",
                "edge_type": "execution",
            }],
        }
        self.cli(
            "register", "--run", str(self.run_root),
            "--definition", str(self.write("definition.json", definition)),
        )

    def launch(self) -> tuple[dict, str]:
        operation = self.cli("next", "--run", str(self.run_root))
        prepared = self.cli(
            "prepare-dispatch", "--run", str(self.run_root),
            "--job", "JOB-PRODUCER",
            "--expected-revision", str(operation["expected_revision"]),
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--dependency-evidence-digest", operation["dependency_evidence_digest"],
        )
        dispatch = prepared["dispatch"]
        launch = self.sign({
            "receipt_type": "launch",
            "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"],
            "session_ref": "session-producer",
        })
        self.cli(
            "launch-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write("launch.json", launch)),
        )
        attempt = json.loads(
            (self.run_root / "control" / "attempts" / f"{dispatch['dispatch_id']}.json").read_text()
        )
        return dispatch, attempt["attempt_id"]

    def plan(self, attempt_id: str, response_id: str = "RESP-ONE") -> dict:
        graph = load_trusted_run(self.run_root)[2]
        authority = graph._authorities[graph._jobs["JOB-PRODUCER"]["authority_id"]]
        return {
            "schema_version": 6,
            "plan_id": "PLAN-ONE",
            "campaign_id": graph.envelope["campaign_id"],
            "cycle_id": "CYC-ONE",
            "source_job_id": "JOB-PRODUCER",
            "source_attempt_id": attempt_id,
            "source_response_id": response_id,
            "authority_id": authority["authority_id"],
            "authority_scope_digest": content_hash(authority["scope"]),
            "base_graph_revision": graph.graph_revision,
            "base_graph_digest": graph.graph_digest,
            "expansion_kind": "direct_repair",
            "target_jobs": [{
                "local_job_id": "LOCAL-REPAIR",
                "role": "repair_worker",
                "purpose_key": "repair",
                "title": "Repair",
                "context_snapshot_id": "CTX-REPAIR",
                "activation_id": "ACT-REPAIR",
                "authority_id": "AUTH-REPAIR",
                "side_effect_class": "none",
                "prompt_input_digest": "a" * 64,
            }],
            "edges": [{
                "source_job_id": "JOB-PRODUCER",
                "target_job_id": "LOCAL-REPAIR",
                "edge_type": "success",
            }],
            "batches": [],
            "verifier_assignments": [],
            "repair_gates": [],
            "created_at": "2026-08-03T00:00:00Z",
        }

    def receipt(
        self, dispatch: dict, attempt_id: str, plan: dict, response_id: str = "RESP-ONE"
    ) -> dict:
        return self.sign({
            "receipt_type": "response",
            "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"],
            "session_ref": "session-producer",
            "response_id": response_id,
            "job_id": "JOB-PRODUCER",
            "attempt_id": attempt_id,
            "status": "completed",
            "summary": "typed response",
            "expansion_plan": plan,
        })

    def send(self, receipt: dict, expected: int = 0) -> dict:
        return self.cli(
            "response-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write(f"{receipt['response_id']}.json", receipt)),
            expected=expected,
        )

    def assert_evidence_only(self, result: dict, response_id: str = "RESP-ONE") -> None:
        self.assertFalse(result["authoritative"])
        evidence = self.run_root / "receipts" / "response" / f"{response_id}.json"
        self.assertTrue(evidence.exists())
        retained = self.run_root / "transactions" / "retained"
        staging = self.run_root / "transactions" / "staging"
        self.assertFalse(retained.exists() and any(retained.iterdir()))
        self.assertFalse(staging.exists() and any(staging.iterdir()))


class ExpansionAuthorityIntakeTest(ResponseIntakeCase):
    def test_empty_adapter_binding_cannot_authenticate_response_facts(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        receipt = self.receipt(dispatch, attempt, self.plan(attempt))
        setup_path = self.run_root / "setup.json"
        setup = json.loads(setup_path.read_text())
        setup["adapter_binding"] = {}
        write_json(setup_path, setup)
        rejected = self.send(receipt, expected=2)
        self.assertIn("no adapter binding", rejected["error"])
        evidence = self.run_root / "receipts" / "response" / "RESP-ONE.json"
        self.assertFalse(evidence.exists())

    def test_unauthorized_implementer_is_immutable_evidence_only(self) -> None:
        self.register("implementation_worker")
        dispatch, attempt = self.launch()
        result = self.send(self.receipt(dispatch, attempt, self.plan(attempt)))
        self.assertIn("not permitted", result["correction"])
        self.assert_evidence_only(result)

    def test_authorized_planner_retains_exact_bytes_and_full_provenance(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        plan = self.plan(attempt)
        receipt = self.receipt(dispatch, attempt, plan)
        result = self.send(receipt)
        print(result); self.assertTrue(result["authoritative"])
        expansion = result["expansion"]
        expansion_id = expansion["expansion_id"]
        exact_path = self.run_root / "transactions" / "retained" / f"{expansion_id}.plan.json"
        self.assertEqual(exact_path.read_bytes(), canonical_bytes(plan))
        provenance = expansion["provenance"]
        self.assertEqual(provenance["producer_job_id"], "JOB-PRODUCER")
        self.assertEqual(provenance["producer_attempt_id"], attempt)
        self.assertEqual(provenance["response_id"], "RESP-ONE")
        self.assertEqual(provenance["response_receipt_digest"], content_hash(receipt))
        self.assertEqual(provenance["source_artifact_digest"], content_hash(plan))
        self.assertEqual(provenance["validation_result"], "accepted")
        self.assertEqual(provenance["authority_scope_digest"], content_hash(provenance["authority_scope"]))

    def test_stale_authority_response_creates_no_retained_expansion(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        stale_plan = self.plan(attempt)
        graph_path = self.run_root / "graph" / "graph.json"
        graph = GraphState.load(graph_path)
        graph.active_planning_authority_id = None
        graph.graph_digest = compute_graph_digest(graph)
        graph.save(graph_path)
        run_path = self.run_root / "run.json"
        run = json.loads(run_path.read_text())
        run["graph_digest"] = graph.graph_digest
        write_json(run_path, run)
        result = self.send(self.receipt(dispatch, attempt, stale_plan))
        self.assertIn("not the current planning authority", result["correction"])
        self.assert_evidence_only(result)

    def test_canceled_run_response_is_nonauthoritative_evidence(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        plan = self.plan(attempt)
        self.cli("cancel", "--run", str(self.run_root), "--reason", "stop")
        result = self.send(self.receipt(dispatch, attempt, plan))
        self.assertEqual(result["operation"], "evidence_recorded")
        self.assert_evidence_only(result)

    def test_delegated_authority_must_narrow_every_dimension(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        graph_path = self.run_root / "graph" / "graph.json"
        graph = GraphState.load(graph_path)
        authority = graph._authorities[graph.active_planning_authority_id]
        authority["scope"]["max_child_jobs"] = 1
        graph.graph_digest = compute_graph_digest(graph)
        graph.save(graph_path)
        run_path = self.run_root / "run.json"
        run = json.loads(run_path.read_text())
        run["graph_digest"] = graph.graph_digest
        write_json(run_path, run)
        plan = self.plan(attempt)
        plan["target_jobs"] = [dict(plan["target_jobs"][0]), {
            **plan["target_jobs"][0],
            "local_job_id": "LOCAL-ESCALATED",
            "authority_id": "AUTH-ESCALATED",
        }]
        plan["target_jobs"][0].update({
            "role": "hypothesis_investigator",
            "side_effect_class": "external_non_idempotent",
            "authority_depth": 3,
            "authority_scope": {"max_child_jobs": 2},
            "limits": {"max_cost": 1},
        })
        result = self.send(self.receipt(dispatch, attempt, plan))
        correction = result["correction"]
        for expected in (
            "2 child jobs", "child role", "child side effect", "delegated depth",
            "child max_child_jobs", "child limit",
        ):
            self.assertIn(expected, correction)
        self.assert_evidence_only(result)


class ExpansionReplayAndTamperTest(ResponseIntakeCase):
    def test_exact_replay_is_idempotent_and_conflicting_response_id_is_rejected(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        receipt = self.receipt(dispatch, attempt, self.plan(attempt))
        first = self.send(receipt)
        second = self.send(receipt)
        self.assertEqual(first["expansion"]["expansion_id"], second["expansion"]["expansion_id"])
        self.assertTrue(second["idempotent_replay"])
        records = [
            path for path in (self.run_root / "transactions" / "retained").glob("EXP-*.json")
            if not path.name.endswith(".plan.json")
        ]
        self.assertEqual(len(records), 1)

        conflicting = dict(receipt)
        conflicting.pop("auth_tag")
        conflicting["summary"] = "different signed bytes"
        self.sign(conflicting)
        rejected = self.send(conflicting, expected=2)
        self.assertIn("conflicting response identity reuse", rejected["error"])
        evidence = self.run_root / "receipts" / "response" / "RESP-ONE.json"
        self.assertEqual(evidence.read_bytes(), canonical_bytes(receipt))

    def test_commit_ignores_mutable_staging_copy_and_uses_retained_bytes(self) -> None:
        self.register("work_planner_architect")
        dispatch, attempt = self.launch()
        accepted = self.send(self.receipt(dispatch, attempt, self.plan(attempt)))
        expansion_id = accepted["expansion"]["expansion_id"]
        operation = self.cli("next", "--run", str(self.run_root))
        staged = self.run_root / "transactions" / "staging" / f"{expansion_id}.staged.json"
        tampered = json.loads(staged.read_bytes())
        tampered["target_jobs"][0]["title"] = "Tampered"
        staged.write_bytes(canonical_bytes(tampered))
        committed = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", expansion_id,
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--plan-digest", operation["plan_digest"],
        )
        self.assertEqual(committed["status"], "committed")
        graph = load_trusted_run(self.run_root)[2]
        global_id = committed["canonical_job_mapping"][0]["global_job_id"]
        self.assertEqual(graph._jobs[global_id]["title"], "Repair")


class VerificationWarningCaptureTest(ResponseIntakeCase):
    """Verification and acceptance failures surface as warnings, never silently.

    Both failures are raised inside ``record_response_receipt`` while applying a
    verifier's condition result. They must be captured on the condition result
    and propagated into the handler's persisted return value.
    """

    ASSIGNMENT_ID = "VASSIGNWARN"
    CYCLE_ID = "CYCWARN"

    def install_assignment(self, target_job_id: str, verifier_job_id: str) -> None:
        """Append a verifier assignment directly to the graph and persist it."""
        from graph_v6 import add_verifier_assignment, compute_graph_digest

        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        add_verifier_assignment(gs, {
            "schema_version": 6,
            "assignment_id": self.ASSIGNMENT_ID,
            "target_job_id": target_job_id,
            "target_gate_revision": 1,
            "verifier_job_id": verifier_job_id,
            "run_id": run["run_id"],
            "cycle_id": self.CYCLE_ID,
            "status": "assigned",
            "assigned_at": "2026-01-01T00:00:00Z",
        })
        gs.graph_digest = compute_graph_digest(gs)
        gs.save(self.run_root / "graph" / "graph.json")

    def verifier_response(
        self,
        dispatch: dict,
        attempt_id: str,
        response_id: str,
        target_job_id: str,
    ) -> dict:
        """Build a signed verifier response carrying a passing condition result."""
        run = load_trusted_run(self.run_root)[0]
        return self.sign({
            "schema_version": 6,
            "receipt_type": "response",
            "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"],
            "attempt_id": attempt_id,
            "response_id": response_id,
            "job_id": "JOB-PRODUCER",
            "session_ref": dispatch.get("session_ref", "session-producer"),
            "status": "completed",
            "summary": "verifier verdict",
            "condition_results": [{
                "schema_version": 6,
                "condition_id": "CONDWARN",
                "target_job_id": target_job_id,
                "target_gate_revision": 1,
                "run_id": run["run_id"],
                "cycle_id": self.CYCLE_ID,
                "status": "passed",
                "producer_job_id": "JOB-PRODUCER",
                "recorded_at": "2026-01-01T00:00:00Z",
                "assignment_id": self.ASSIGNMENT_ID,
            }],
        })

    def test_verification_warning_captured(self):
        """apply_verification_result failure is reported as verification_warning.

        A verifier assigned to itself trips the self-approval guard inside
        ``apply_verification_result``.
        """
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        self.install_assignment("JOB-PRODUCER", "JOB-PRODUCER")

        result = self.send(
            self.verifier_response(
                dispatch, attempt_id, "RESP-VERIFY-WARN", "JOB-PRODUCER"
            )
        )

        self.assertTrue(result["authoritative"])
        self.assertIn("verification_warning", result)
        self.assertIn("self-approval rejected", result["verification_warning"])
        # The failure must not be reported as a successful acceptance.
        self.assertNotIn("acceptance_warning", result)

        # The warning is durable, not only present in the in-process return value.
        persisted = json.loads(
            (
                self.run_root / "control" / "response-results" / "RESP-VERIFY-WARN.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            persisted["verification_warning"], result["verification_warning"]
        )

    def test_acceptance_warning_captured(self):
        """accept_target failure is reported as acceptance_warning.

        Verification succeeds because the verifier and target differ, then
        ``accept_target`` fails because the target has no repair-gate history.
        """
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        target_job_id = load_trusted_run(self.run_root)[0]["job_ids"][0]
        self.install_assignment(target_job_id, "JOB-PRODUCER")

        result = self.send(
            self.verifier_response(
                dispatch, attempt_id, "RESP-ACCEPT-WARN", target_job_id
            )
        )

        self.assertTrue(result["authoritative"])
        # Verification itself must have succeeded to reach the acceptance step.
        self.assertNotIn("verification_warning", result)
        self.assertIn("acceptance_warning", result)
        self.assertIn("no repair history", result["acceptance_warning"])

        persisted = json.loads(
            (
                self.run_root / "control" / "response-results" / "RESP-ACCEPT-WARN.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            persisted["acceptance_warning"], result["acceptance_warning"]
        )


class VerifierTrustBoundaryTest(VerificationWarningCaptureTest):
    """Server-authored verification/acceptance decisions (D15, D16).

    Reuses the assignment-install and verifier-response helpers. The submitter
    identity is always ``JOB-PRODUCER`` (bound by dispatch and the receipt HMAC);
    only the stored assignment's ``verifier_job_id`` and the client verdict vary.
    """

    def verifier_response_singular(
        self,
        dispatch: dict,
        attempt_id: str,
        response_id: str,
        target_job_id: str,
        wire_status: str,
        client_verdict: str,
    ) -> dict:
        """A signed verifier response using the SINGULAR condition_result form.

        The singular form bypasses ``_normalize_verifier_wire_results`` so it is
        the path where a client verdict could otherwise be trusted.
        """
        run = load_trusted_run(self.run_root)[0]
        record_status = {
            "passed": "met", "failed": "unmet", "not_run": "pending",
            "unavailable": "error", "unknown": "error",
        }.get(wire_status, "error")
        return self.sign({
            "schema_version": 6,
            "receipt_type": "response",
            "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"],
            "attempt_id": attempt_id,
            "response_id": response_id,
            "job_id": "JOB-PRODUCER",
            "session_ref": dispatch.get("session_ref", "session-producer"),
            "status": "completed",
            "summary": "verifier verdict",
            "condition_result": {
                "schema_version": 6,
                "condition_id": "CONDWARN",
                "target_job_id": target_job_id,
                "target_gate_revision": 1,
                "run_id": run["run_id"],
                "cycle_id": self.CYCLE_ID,
                "status": record_status,
                "wire_status": wire_status,
                "verdict": client_verdict,
                "producer_job_id": "JOB-PRODUCER",
                "recorded_at": "2026-01-01T00:00:00Z",
                "assignment_id": self.ASSIGNMENT_ID,
            },
        })

    def _target_verification_passed(self, target_job_id: str) -> bool:
        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        job = gs._jobs.get(target_job_id, {})
        return bool(job.get("verification_passed"))

    def install_second_verifier(self, job_id: str) -> None:
        """Add a real, graph-registered verifier job (not the submitter).

        Without this the cross-verifier test would pass for the wrong reason:
        an unknown ``verifier_job_id`` trips ``reject_unauthorized_verifier``.
        Registering a genuine verifier makes the D15 ownership check the sole
        thing that can block the submission.
        """
        from graph_v6 import compute_graph_digest

        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        template = dict(gs._jobs["JOB-PRODUCER"])
        template["job_id"] = job_id
        template["title"] = "Other verifier"
        template["role"] = "verifier"
        gs._jobs[job_id] = template
        gs.graph_digest = compute_graph_digest(gs)
        gs.save(self.run_root / "graph" / "graph.json")

    def test_cross_verifier_submission_is_rejected(self):
        """D15: a verifier cannot drive acceptance of an assignment it does not own.

        The stored assignment names a real, graph-registered ``JOB-OTHER-VERIFIER``
        as its verifier, but the authenticated submitter is ``JOB-PRODUCER``. The
        ownership mismatch must block verification and acceptance and leave the
        target untouched. The other verifier is a genuine verifier-role job, so the
        only thing that can block the submission is the ownership check itself.
        """
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        target_job_id = load_trusted_run(self.run_root)[0]["job_ids"][0]
        self.install_second_verifier("JOB-OTHER-VERIFIER")
        self.install_assignment(target_job_id, "JOB-OTHER-VERIFIER")

        result = self.send(
            self.verifier_response(
                dispatch, attempt_id, "RESP-XVERIF", target_job_id
            )
        )

        self.assertFalse(
            self._target_verification_passed(target_job_id),
            "cross-verifier submission must not mark the target verification_passed",
        )
        self.assertNotIn("acceptance_warning", result)
        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        assignment = gs._verifier_assignments[self.ASSIGNMENT_ID]
        self.assertEqual(
            assignment["status"], "assigned",
            "the unowned assignment must not be mutated to completed",
        )

    def test_client_verdict_cannot_override_failing_status(self):
        """D16: a failing status with a client verdict of 'pass' does not accept.

        The verifier owns the assignment (so ownership passes), the target differs
        (so self-approval passes), but the server-derived verdict from the failing
        wire status must govern, not the client's 'pass'.
        """
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        target_job_id = load_trusted_run(self.run_root)[0]["job_ids"][0]
        self.install_assignment(target_job_id, "JOB-PRODUCER")

        result = self.send(
            self.verifier_response_singular(
                dispatch, attempt_id, "RESP-VERDICT", target_job_id,
                wire_status="failed", client_verdict="pass",
            )
        )

        self.assertFalse(
            self._target_verification_passed(target_job_id),
            "a failing status must not accept the target even if verdict=='pass'",
        )
        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        assignment = gs._verifier_assignments[self.ASSIGNMENT_ID]
        self.assertNotEqual(
            assignment.get("verdict"), "pass",
            "the applied verdict must be server-derived from the failing status",
        )

    def test_owned_assignment_passing_verdict_accepts_target(self):
        """Happy path: an owned assignment with a passing verdict accepts the target."""
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        target_job_id = load_trusted_run(self.run_root)[0]["job_ids"][0]
        self.install_assignment(target_job_id, "JOB-PRODUCER")

        result = self.send(
            self.verifier_response(
                dispatch, attempt_id, "RESP-OWNED", target_job_id
            )
        )

        self.assertTrue(result["authoritative"])
        self.assertNotIn("verification_warning", result)
        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        assignment = gs._verifier_assignments[self.ASSIGNMENT_ID]
        self.assertEqual(assignment["status"], "completed")
        self.assertEqual(assignment["verdict"], "pass")

    def test_missing_assignment_id_cannot_verify_a_target(self):
        """D15 (else-branch): a passing result with NO assignment_id must not
        mark a client-named target verified.

        ``assignment_id`` is a client-supplied schema field, so a verifier could
        formerly omit it and land in the no-assignment branch that set
        ``verification_passed`` on any client-named target with no ownership
        check. The handler must refuse to accept a target without an owned
        assignment.
        """
        self.register("verifier")
        dispatch, attempt_id = self.launch()
        target_job_id = load_trusted_run(self.run_root)[0]["job_ids"][0]
        # No assignment installed; the response omits assignment_id entirely.
        response = self.verifier_response_singular(
            dispatch, attempt_id, "RESP-NOASSIGN", target_job_id,
            wire_status="passed", client_verdict="pass",
        )
        del response["condition_result"]["assignment_id"]
        response = self.sign({k: v for k, v in response.items() if k != "auth_tag"})

        result = self.send(response)

        self.assertFalse(
            self._target_verification_passed(target_job_id),
            "a result with no owned assignment must not mark the target verified",
        )


class VerdictDerivationGuardTest(unittest.TestCase):
    """Pin the server-side verdict maps and the exception-class identity."""

    def test_only_met_maps_to_pass(self):
        """Only the 'met' record status may derive a 'pass' verdict.

        The accept gate is ``verdict == 'pass'``. If any other record status
        mapped to 'pass', acceptance would silently broaden versus the intended
        contract, so this pins the map.
        """
        import jobctl

        passing = [
            status for status, verdict in jobctl._RECORD_STATUS_TO_VERDICT.items()
            if verdict == "pass"
        ]
        self.assertEqual(passing, ["met"])
        # Wire vocabulary: only 'passed' derives 'pass'.
        wire_passing = [
            wire for wire, verdict in jobctl._WIRE_TO_VERDICT.items()
            if verdict == "pass"
        ]
        self.assertEqual(wire_passing, ["passed"])

    def test_orchestrator_error_is_shared_singleton(self):
        """orchestrator.py must use the same OrchestratorError object as core.

        The duplicate-class fix only works if every ``raise``/``except`` site
        resolves the identical class object; otherwise cross-module
        ``except OrchestratorError`` silently misses.
        """
        import orchestrator
        import orchestrator_core
        self.assertIs(
            orchestrator.OrchestratorError, orchestrator_core.OrchestratorError
        )


if __name__ == "__main__":
    unittest.main()
