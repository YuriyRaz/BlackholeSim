"""Cycle 1 control-plane regressions through the real jobctl process."""

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

from orchestrator_core import content_hash, load_trusted_run, receipt_auth_tag  # noqa: E402


class ControlPlaneCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = self.root / "request.md"
        self.request.write_text("trusted request\n", encoding="utf-8")
        result = self.cli(
            "init", "--request-file", str(self.request), "--goal", "cycle one",
            "--run-id", "cycle-one", "--state-root", str(self.root),
            "--workspace", str(self.root), "--test-harness",
        )
        self.run_root = Path(result["run_root"])
        self.binding = result["adapter_binding"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *arguments: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "jobctl.py"), *arguments],
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

    def register(self, role: str = "implementation_worker", job_id: str = "JOB-ONE", batches: list | None = None) -> None:
        root_job_id = json.loads((self.run_root / "run.json").read_text())["job_ids"][0]
        definition = {
            "schema_version": 6,
            "jobs": [{
                "job_id": job_id,
                "title": "Cycle job",
                "role": role,
                "purpose_key": "cycle-job",
                "prompt": "Perform the cycle job.",
            }],
            "edges": [{
                "source_job_id": root_job_id,
                "target_job_id": job_id,
                "edge_type": "execution",
            }],
            "batches": batches or [],
        }
        self.cli(
            "register", "--run", str(self.run_root),
            "--definition", str(self.write("definition.json", definition)),
        )

    def register_definition(self, definition: dict) -> None:
        self.cli(
            "register", "--run", str(self.run_root),
            "--definition", str(self.write("definition.json", definition)),
        )

    def prepare_and_launch(self, job_id: str = "JOB-ONE") -> tuple[dict, str]:
        operation = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(operation["operation"], "prepare_dispatch")
        prepared = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", job_id,
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
            "session_ref": f"session-{job_id.lower()}",
        })
        self.cli(
            "launch-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write("launch.json", launch)),
        )
        attempt = json.loads(
            (self.run_root / "control" / "attempts" / f"{dispatch['dispatch_id']}.json").read_text()
        )
        return dispatch, attempt["attempt_id"]

    def response(self, dispatch: dict, attempt_id: str, **fields: object) -> dict:
        receipt = {
            "receipt_type": "response",
            "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"],
            "session_ref": f"session-{dispatch['job_id'].lower()}",
            "response_id": fields.pop("response_id", "RESP-ONE"),
            "job_id": dispatch["job_id"],
            "attempt_id": attempt_id,
            "status": fields.pop("status", "completed"),
            "summary": "response summary",
            **fields,
        }
        self.sign(receipt)
        return self.cli(
            "response-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write(f"{receipt['response_id']}.json", receipt)),
        )


class ProtocolBoundaryTest(ControlPlaneCase):
    def test_audit_reads_the_schema_valid_control_plane(self) -> None:
        self.register()
        result = self.cli("audit", "--run", str(self.run_root))
        self.assertTrue(result["trusted"])
        self.assertEqual(result["version"], 6)
        self.assertEqual(result["graph"]["digest"], load_trusted_run(self.run_root)[0]["graph_digest"])

    def test_records_validate_and_old_run_is_rejected(self) -> None:
        run, setup, graph, adapter = load_trusted_run(self.run_root)
        self.assertEqual(run["schema_version"], 6)
        self.assertEqual(setup["execution_mode"], "hybrid")
        self.assertEqual(graph.graph_digest, run["graph_digest"])
        self.assertEqual(adapter["adapter_id"], "deterministic-test")

        old = self.root / "old"
        old.mkdir()
        (old / "run.json").write_text(json.dumps({"schema_version": 5}), encoding="utf-8")
        result = self.cli("next", "--run", str(old), expected=2)
        self.assertIn("incompatible run", result["error"])

    def test_registration_is_initial_only_and_next_is_pure(self) -> None:
        self.register()
        graph_path = self.run_root / "graph" / "graph.json"
        before = graph_path.read_bytes()
        first = self.cli("next", "--run", str(self.run_root))
        second = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(first, second)
        self.assertEqual(before, graph_path.read_bytes())
        rejected = self.cli(
            "register", "--run", str(self.run_root),
            "--definition", str(self.root / "definition.json"), expected=2,
        )
        self.assertIn("registration is closed", rejected["error"])


class SchedulingDispatchIntegrationTest(ControlPlaneCase):
    def test_next_deterministically_selects_one_of_multiple_eligible_jobs(self) -> None:
        root_job_id = json.loads((self.run_root / "run.json").read_text())["job_ids"][0]
        self.register_definition({
            "schema_version": 6,
            "jobs": [
                {"job_id": "JOB-Z", "role": "worker", "purpose_key": "z"},
                {"job_id": "JOB-A", "role": "worker", "purpose_key": "a"},
            ],
            "edges": [
                {"source_job_id": root_job_id, "target_job_id": "JOB-Z", "edge_type": "execution"},
                {"source_job_id": root_job_id, "target_job_id": "JOB-A", "edge_type": "execution"},
            ],
        })
        first = self.cli("next", "--run", str(self.run_root))
        second = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(first, second)
        self.assertEqual(first["operation"], "prepare_dispatch")
        self.assertEqual(first["job_id"], "JOB-A")

    def test_next_selects_concrete_job_and_prepare_enforces_all_cas(self) -> None:
        self.register(role="worker", job_id="JOB-ONE")
        graph_path = self.run_root / "graph" / "graph.json"
        job_path = self.run_root / "jobs" / "JOB-ONE" / "job.json"
        before_graph = graph_path.read_bytes()
        before_job = job_path.read_bytes()

        first = self.cli("next", "--run", str(self.run_root))
        second = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(first, second)
        self.assertEqual(first["job_id"], "JOB-ONE")
        self.assertEqual(before_graph, graph_path.read_bytes())
        self.assertEqual(before_job, job_path.read_bytes())

        common = (
            "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(first["expected_revision"]),
            "--expected-graph-revision", str(first["expected_graph_revision"]),
            "--expected-graph-digest", first["expected_graph_digest"],
            "--dependency-evidence-digest", first["dependency_evidence_digest"],
        )
        missing = self.cli(
            "prepare-dispatch", *common[:3], "JOB-MISSING", *common[4:], expected=2,
        )
        self.assertIn("does not exist", missing["error"])

        stale_graph = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(first["expected_revision"]),
            "--expected-graph-revision", str(first["expected_graph_revision"] + 1),
            "--expected-graph-digest", first["expected_graph_digest"],
            "--dependency-evidence-digest", first["dependency_evidence_digest"],
            expected=2,
        )
        self.assertIn("graph revision mismatch", stale_graph["error"])

        stale_digest = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(first["expected_revision"]),
            "--expected-graph-revision", str(first["expected_graph_revision"]),
            "--expected-graph-digest", "0" * 64,
            "--dependency-evidence-digest", first["dependency_evidence_digest"],
            expected=2,
        )
        self.assertIn("digest mismatch", stale_digest["error"])

        stale_job = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(first["expected_revision"] + 1),
            "--expected-job-revision", str(first["expected_revision"] + 1),
            "--expected-graph-revision", str(first["expected_graph_revision"]),
            "--expected-graph-digest", first["expected_graph_digest"],
            "--dependency-evidence-digest", first["dependency_evidence_digest"],
            expected=2,
        )
        self.assertIn("stale job compare-and-swap", stale_job["error"])
        self.assertEqual(before_job, job_path.read_bytes())

        self.cli("prepare-dispatch", *common)
        replay = self.cli("prepare-dispatch", *common, expected=2)
        self.assertIn("stale job compare-and-swap", replay["error"])

    def test_typed_batch_edge_blocks_until_batch_is_complete(self) -> None:
        from graph_v6 import GraphState, compute_graph_digest

        root_job_id = json.loads((self.run_root / "run.json").read_text())["job_ids"][0]
        self.register_definition({
            "schema_version": 6,
            "jobs": [
                {"job_id": "JOB-A", "role": "worker", "purpose_key": "a"},
                {"job_id": "JOB-B", "role": "worker", "purpose_key": "b"},
            ],
            "edges": [
                {"source_job_id": root_job_id, "target_job_id": "JOB-A", "edge_type": "execution"},
                {"source_job_id": "JOB-A", "target_job_id": "JOB-B", "edge_type": "batch"},
            ],
            "batches": [{"batch_id": "BATCH-A", "status": "open", "job_ids": ["JOB-A"]}],
        })
        dispatch, attempt = self.prepare_and_launch("JOB-A")
        self.response(dispatch, attempt)

        blocked = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(blocked["operation"], "wait")
        self.assertEqual(blocked["reason"], "dependency_or_batch_barrier")
        run = json.loads((self.run_root / "run.json").read_text())
        ineligible = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-B",
            "--expected-revision", "0",
            "--expected-graph-revision", str(run["graph_revision"]),
            "--expected-graph-digest", run["graph_digest"],
            "--dependency-evidence-digest", "0" * 64,
            expected=2,
        )
        self.assertIn("not eligible", ineligible["error"])

        graph_path = self.run_root / "graph" / "graph.json"
        graph = GraphState.load(graph_path)
        graph._batches["BATCH-A"]["status"] = "complete"
        graph.graph_digest = compute_graph_digest(graph)
        graph.save(graph_path)
        run_path = self.run_root / "run.json"
        run = json.loads(run_path.read_text())
        run["graph_digest"] = graph.graph_digest
        run_path.write_text(json.dumps(run), encoding="utf-8")

        ready = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(ready["operation"], "prepare_dispatch")
        self.assertEqual(ready["job_id"], "JOB-B")

    def test_graph_planning_and_terminal_barriers_reject_dispatch(self) -> None:
        from graph_v6 import GraphState

        self.register(role="worker")
        selected = self.cli("next", "--run", str(self.run_root))
        graph_path = self.run_root / "graph" / "graph.json"
        graph = GraphState.load(graph_path)
        graph.status = "planning"
        graph.save(graph_path)

        planning = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(planning["operation"], "wait")
        self.assertEqual(planning["reason"], "graph_planning")
        rejected = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(selected["expected_revision"]),
            "--expected-graph-revision", str(selected["expected_graph_revision"]),
            "--expected-graph-digest", selected["expected_graph_digest"],
            "--dependency-evidence-digest", selected["dependency_evidence_digest"],
            expected=2,
        )
        self.assertIn("not eligible", rejected["error"])

        for status in ("pending", "committing", "canceling"):
            graph.status = status
            graph.save(graph_path)
            waiting = self.cli("next", "--run", str(self.run_root))
            self.assertEqual(waiting["operation"], "wait")
            self.assertEqual(waiting["reason"], f"graph_{status}")

        graph.status = "recovery_required"
        graph.save(graph_path)
        recovery = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(recovery["operation"], "recover")

        graph.status = "sealed"
        graph.save(graph_path)
        terminal = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(terminal["operation"], "wait")
        self.assertEqual(terminal["reason"], "terminal_barrier")


class ReceiptAndConversationTest(ControlPlaneCase):
    def test_receipts_are_authenticated_and_answer_resumes_same_session(self) -> None:
        self.register()
        operation = self.cli("next", "--run", str(self.run_root))
        prepared = self.cli(
            "prepare-dispatch", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--expected-revision", str(operation["expected_revision"]),
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--dependency-evidence-digest", operation["dependency_evidence_digest"],
        )
        dispatch = prepared["dispatch"]
        forged = {
            "receipt_type": "launch", "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"], "session_ref": "session-job-one",
            "auth_tag": "0" * 64,
        }
        rejected = self.cli(
            "launch-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write("forged.json", forged)), expected=2,
        )
        self.assertIn("authentication failed", rejected["error"])
        receipts_dir = self.run_root / "receipts" / "launch"
        self.assertFalse(receipts_dir.exists() and any(receipts_dir.iterdir()))

        launch = self.sign({
            "receipt_type": "launch", "adapter_id": self.binding["adapter_id"],
            "dispatch_id": dispatch["dispatch_id"], "session_ref": "session-job-one",
        })
        self.cli(
            "launch-receipt", "--run", str(self.run_root),
            "--receipt", str(self.write("launch.json", launch)),
        )
        attempt = json.loads(
            (self.run_root / "control" / "attempts" / f"{dispatch['dispatch_id']}.json").read_text()
        )["attempt_id"]
        result = self.response(
            dispatch, attempt, status="needs_input", question="Choose the target?",
        )
        self.assertEqual(result["operation"], "ask_user")
        repeated = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(repeated["operation"], "ask_user")
        self.assertEqual(repeated["job_id"], "JOB-ONE")
        self.assertEqual(repeated["session_ref"], "session-job-one")
        answer = self.cli(
            "answer", "--run", str(self.run_root), "--job", "JOB-ONE",
            "--answer", "Use target A",
        )
        self.assertEqual(answer["operation"], "resume_job")
        self.assertEqual(answer["session_ref"], "session-job-one")
        job = json.loads((self.run_root / "jobs" / "JOB-ONE" / "job.json").read_text())
        self.assertEqual(job["status"], "running")


    def test_graph_consistent_after_response_receipt(self):
        """The consolidated save persists every verification-path mutation.

        Drives the verification/acceptance branch of ``record_response_receipt``
        (the branch whose three separate saves were consolidated into one) and
        then reloads the graph from disk. If the single consolidated save were
        missing or misplaced, the verification mutation would not be durable
        even though the in-memory handler reported it.
        """
        from graph_v6 import add_verifier_assignment, compute_graph_digest

        self.register("verifier")
        dispatch, attempt_id = self.prepare_and_launch()

        run, _setup, gs, _adapter = load_trusted_run(self.run_root)
        target_job_id = run["job_ids"][0]
        assignment_id = "VASSIGNSAVE"
        add_verifier_assignment(gs, {
            "schema_version": 6,
            "assignment_id": assignment_id,
            "target_job_id": target_job_id,
            "target_gate_revision": 1,
            "verifier_job_id": "JOB-ONE",
            "run_id": run["run_id"],
            "cycle_id": "CYCSAVE",
            "status": "assigned",
            "assigned_at": "2026-01-01T00:00:00Z",
        })
        gs.graph_digest = compute_graph_digest(gs)
        gs.save(self.run_root / "graph" / "graph.json")
        # Keep run.json in step with the injected assignment, otherwise the
        # scheduler's run/graph digest agreement check would reject the run for
        # a reason unrelated to what this test covers.
        run["graph_digest"] = gs.graph_digest
        (self.run_root / "run.json").write_text(
            json.dumps(run, indent=2), encoding="utf-8"
        )

        result = self.response(
            dispatch,
            attempt_id,
            status="completed",
            condition_results=[{
                "schema_version": 6,
                "condition_id": "CONDSAVE",
                "target_job_id": target_job_id,
                "target_gate_revision": 1,
                "run_id": run["run_id"],
                "cycle_id": "CYCSAVE",
                "status": "passed",
                "producer_job_id": "JOB-ONE",
                "recorded_at": "2026-01-01T00:00:00Z",
                "assignment_id": assignment_id,
            }],
        )
        self.assertTrue(result["authoritative"])
        # Verification must have succeeded so a real mutation needs persisting.
        self.assertNotIn("verification_warning", result)

        reloaded_run, _s, reloaded, _a = load_trusted_run(self.run_root)
        persisted_assignment = reloaded._verifier_assignments[assignment_id]
        self.assertEqual(persisted_assignment["status"], "completed")
        self.assertEqual(persisted_assignment["verdict"], "pass")

        # The persisted graph must also be internally consistent.
        self.assertEqual(compute_graph_digest(reloaded), reloaded.graph_digest)
        self.assertEqual(reloaded_run["graph_digest"], reloaded.graph_digest)


class ExpansionTransactionTest(ControlPlaneCase):
    def expansion_response(
        self,
        initial_batches: list | None = None,
        plan_batches: list | None = None,
        plan_mutator=None,
        graph_limits: dict | None = None,
    ) -> tuple[dict, dict]:
        self.register(role="work_planner_architect", batches=initial_batches)
        dispatch, attempt = self.prepare_and_launch()
        _run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        if graph_limits:
            from graph_v6 import compute_graph_digest
            from orchestrator_core import write_json

            graph.envelope.setdefault("limits", {}).update(graph_limits)
            graph.limits.update(graph_limits)
            graph.graph_digest = compute_graph_digest(graph)
            graph.save(self.run_root / "graph" / "graph.json")
            run_path = self.run_root / "run.json"
            run = json.loads(run_path.read_text())
            run["graph_digest"] = graph.graph_digest
            write_json(run_path, run)
        authority = graph._authorities[graph._jobs["JOB-ONE"]["authority_id"]]
        plan = {
            "schema_version": 6,
            "plan_id": "PLAN-ONE",
            "campaign_id": graph.envelope["campaign_id"],
            "cycle_id": "CYC-NEXT",
            "source_job_id": "JOB-ONE",
            "source_attempt_id": attempt,
            "source_response_id": "RESP-ONE",
            "authority_id": authority["authority_id"],
            "authority_scope_digest": content_hash(authority["scope"]),
            "base_graph_revision": graph.graph_revision,
            "base_graph_digest": graph.graph_digest,
            "expansion_kind": "direct_repair",
            "target_jobs": [{
                "local_job_id": "LOCAL-REPAIR",
                "role": "repair_worker",
                "purpose_key": "repair-target",
                "title": "Repair target",
                "context_snapshot_id": "CTX-REPAIR",
                "activation_id": "ACT-REPAIR",
                "authority_id": "AUTH-REPAIR",
                "side_effect_class": "none",
                "prompt_input_digest": "a" * 64,
            }],
            "edges": [{
                "source_job_id": "JOB-ONE", "target_job_id": "LOCAL-REPAIR",
                "edge_type": "success",
            }],
            "batches": plan_batches or [],
            "verifier_assignments": [],
            "repair_gates": [],
            "created_at": "2026-08-01T00:00:00Z",
        }
        if plan_mutator is not None:
            plan_mutator(plan)
        response = self.response(dispatch, attempt, expansion_plan=plan)
        if "authoritative" in response and "correction" not in response:
            self.assertTrue(response["authoritative"])
        return response, plan

    def test_pending_precedence_purity_and_retained_byte_commit(self) -> None:
        response, plan = self.expansion_response()
        first = self.cli("next", "--run", str(self.run_root))
        second = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(first, second)
        self.assertEqual(first["operation"], "commit_expansion")
        plan["target_jobs"][0]["title"] = "mutated worker file"
        self.write("RESP-ONE.json", {"untrusted": plan})
        committed = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", first["expansion_id"],
            "--expected-graph-revision", str(first["expected_graph_revision"]),
            "--expected-graph-digest", first["expected_graph_digest"],
            "--plan-digest", first["plan_digest"],
        )
        self.assertEqual(committed["status"], "committed")
        global_id = committed["canonical_job_mapping"][0]["global_job_id"]
        definition = load_trusted_run(self.run_root)[2]._jobs[global_id]
        self.assertEqual(definition["title"], "Repair target")
        replay = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", first["expansion_id"],
            "--expected-graph-revision", str(first["expected_graph_revision"]),
            "--expected-graph-digest", first["expected_graph_digest"],
            "--plan-digest", first["plan_digest"],
        )
        self.assertEqual(replay["status"], "idempotent_replay")
        scheduled = self.cli("next", "--run", str(self.run_root))
        self.assertEqual(scheduled["operation"], "prepare_dispatch")
        self.assertEqual(scheduled["job_id"], global_id)

    def test_contradictory_recovery_blocks(self) -> None:
        response, _plan = self.expansion_response()
        expansion_id = response["expansion"]["expansion_id"]
        staged = self.run_root / "transactions" / "staging" / f"{expansion_id}.staged.json"
        staged.write_bytes(b"contradiction")
        recovered = self.cli(
            "recover", "--run", str(self.run_root), "--transaction", expansion_id,
        )
        self.assertEqual(recovered["recovery_action"], "blocked")

    def test_sealed_batch_rejects_late_membership(self) -> None:
        _run, _setup, initial, _adapter = load_trusted_run(self.run_root)
        sealed = {
            "schema_version": 6,
            "batch_id": "BATCH-SEALED",
            "campaign_id": initial.envelope["campaign_id"],
            "cycle_id": "CYC-SEALED",
            "graph_generation": 1,
            "owner_authority_id": initial.envelope["authority_id"],
            "status": "sealed",
            "job_ids": ["JOB-ONE"],
            "mandatory_job_ids": ["JOB-ONE"],
            "required_gate_ids": [],
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
        response, _plan = self.expansion_response(
            initial_batches=[sealed],
            plan_batches=[{
                "batch_id": "BATCH-SEALED",
                "status": "open",
                "job_ids": ["LOCAL-REPAIR"],
                "mandatory_job_ids": ["LOCAL-REPAIR"],
                "owner_authority_id": initial.envelope["authority_id"],
            }],
        )
        self.assertEqual(response["operation"], "resume_job")
        self.assertIn("sealed or settled batch", response["correction"])
        graph = load_trusted_run(self.run_root)[2]
        self.assertFalse(any(item.get("status") == "pending" for item in graph._expansions.values()))

    def _fault_boundary(self, boundary: str) -> None:
        _response, _plan = self.expansion_response()
        operation = self.cli("next", "--run", str(self.run_root))
        arguments = (
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", operation["expansion_id"],
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--plan-digest", operation["plan_digest"],
        )
        failed = self.cli(*arguments, "--fault-at", boundary, expected=2)
        self.assertIn(boundary, failed["error"])
        run = json.loads((self.run_root / "run.json").read_text())
        from graph_v6 import GraphState

        graph = GraphState.load(self.run_root / "graph" / "graph.json")
        if boundary in {"after_staging", "after_manifest"}:
            self.assertEqual(run["graph_revision"], operation["expected_graph_revision"])
            self.assertEqual(graph.graph_revision, operation["expected_graph_revision"])
        elif boundary == "after_file_write":
            self.assertEqual(run["graph_revision"], operation["expected_graph_revision"])
            self.assertEqual(graph.graph_revision, operation["expected_graph_revision"])
            pending = self.cli("next", "--run", str(self.run_root))
            self.assertEqual(pending["operation"], "commit_expansion")
        elif boundary == "before_visibility":
            self.assertEqual(run["graph_revision"], operation["expected_graph_revision"])
            self.assertEqual(graph.graph_revision, operation["expected_graph_revision"] + 1)
            blocked = self.cli("next", "--run", str(self.run_root), expected=2)
            self.assertIn("disagree", blocked["error"])
        else:
            self.assertEqual(run["graph_revision"], operation["expected_graph_revision"] + 1)
            self.assertEqual(graph.graph_revision, run["graph_revision"])

        recovered = self.cli(*arguments)
        self.assertIn(recovered["status"], {"committed", "idempotent_replay"})
        final_run, _setup, final_graph, _adapter = load_trusted_run(self.run_root)
        global_id = recovered["canonical_job_mapping"][0]["global_job_id"]
        self.assertIn(global_id, final_graph._jobs)
        self.assertTrue((self.run_root / "jobs" / global_id / "job.json").exists())
        self.assertTrue((self.run_root / "jobs" / global_id / "prompt.md").exists())
        self.assertEqual(final_graph.expansion_ledger, [operation["expansion_id"]])
        self.assertEqual(len(final_graph._generations), 1)
        self.assertEqual(final_run["graph_revision"], operation["expected_graph_revision"] + 1)

    def test_fault_after_staging_rolls_forward(self) -> None:
        self._fault_boundary("after_staging")

    def test_fault_after_manifest_rolls_forward(self) -> None:
        self._fault_boundary("after_manifest")

    def test_fault_after_file_write_rolls_forward(self) -> None:
        self._fault_boundary("after_file_write")

    def test_fault_before_visibility_rolls_forward(self) -> None:
        self._fault_boundary("before_visibility")

    def test_fault_after_visibility_is_idempotent(self) -> None:
        self._fault_boundary("after_visibility")

    def test_fault_before_cleanup_is_idempotent(self) -> None:
        self._fault_boundary("before_cleanup")

    def test_commit_rejects_stale_graph_cas_without_staging(self) -> None:
        _response, _plan = self.expansion_response()
        operation = self.cli("next", "--run", str(self.run_root))
        rejected = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", operation["expansion_id"],
            "--expected-graph-revision", str(operation["expected_graph_revision"] + 1),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--plan-digest", operation["plan_digest"], expected=2,
        )
        self.assertIn("retained graph revision mismatch", rejected["error"])
        self.assertFalse((self.run_root / "transactions" / "manifests").exists())

    def test_commit_rejects_complete_prospective_cycle(self) -> None:
        def add_cycle(plan: dict) -> None:
            second = dict(plan["target_jobs"][0])
            second.update({
                "local_job_id": "LOCAL-SECOND",
                "purpose_key": "repair-second",
                "authority_id": "AUTH-SECOND",
                "context_snapshot_id": "CTX-SECOND",
                "activation_id": "ACT-SECOND",
            })
            plan["target_jobs"].append(second)
            plan["edges"] = [
                {"source_job_id": "LOCAL-REPAIR", "target_job_id": "LOCAL-SECOND", "edge_type": "success"},
                {"source_job_id": "LOCAL-SECOND", "target_job_id": "LOCAL-REPAIR", "edge_type": "success"},
            ]

        response, _plan = self.expansion_response(plan_mutator=add_cycle)
        expansion_id = response["expansion"]["expansion_id"]
        operation = self.cli("next", "--run", str(self.run_root))
        rejected = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", expansion_id,
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--plan-digest", operation["plan_digest"], expected=2,
        )
        self.assertIn("dependency cycle", rejected["error"])
        self.assertEqual(load_trusted_run(self.run_root)[0]["graph_revision"], 1)

    def test_commit_rejects_immutable_job_limit_wholly(self) -> None:
        response, _plan = self.expansion_response(graph_limits={"max_total_jobs": 2})
        expansion_id = response["expansion"]["expansion_id"]
        operation = self.cli("next", "--run", str(self.run_root))
        rejected = self.cli(
            "commit-expansion", "--run", str(self.run_root),
            "--expansion", expansion_id,
            "--expected-graph-revision", str(operation["expected_graph_revision"]),
            "--expected-graph-digest", operation["expected_graph_digest"],
            "--plan-digest", operation["plan_digest"], expected=2,
        )
        self.assertIn("total jobs limit exceeded", rejected["error"])
        self.assertEqual(len(load_trusted_run(self.run_root)[2]._jobs), 2)


class RepairGateTransitionTest(ControlPlaneCase):
    def valid_graph(self):
        root_job_id = json.loads((self.run_root / "run.json").read_text())["job_ids"][0]
        now = "2026-08-01T00:00:00Z"
        definition = {
            "schema_version": 6,
            "jobs": [
                {"job_id": "JOB-TARGET", "role": "implementation_worker", "purpose_key": "target", "prompt": "target"},
                {"job_id": "JOB-REPAIR", "role": "repair_worker", "purpose_key": "repair", "prompt": "repair"},
                {"job_id": "JOB-VERIFY", "role": "verifier", "purpose_key": "verify", "prompt": "verify"},
            ],
            "edges": [
                {"source_job_id": root_job_id, "target_job_id": "JOB-TARGET", "edge_type": "execution"},
                {"source_job_id": "JOB-TARGET", "target_job_id": "JOB-REPAIR", "edge_type": "execution"},
                {"source_job_id": "JOB-REPAIR", "target_job_id": "JOB-VERIFY", "edge_type": "execution"},
            ],
            "verifier_assignments": [{
                "schema_version": 6,
                "assignment_id": "VASS-CURRENT",
                "target_job_id": "JOB-TARGET",
                "condition_id": "COND-TESTS",
                "target_gate_revision": 2,
                "verifier_job_id": "JOB-VERIFY",
                "run_id": "cycle-one",
                "cycle_id": "CYC-ROUND",
                "graph_generation": 1,
                "source_snapshot_digest": "a" * 64,
                "required_evidence": [],
                "status": "assigned",
                "assigned_at": now,
            }],
            "repair_gate_history": [{
                "schema_version": 6,
                "history_id": "RGH-CURRENT",
                "target_job_id": "JOB-TARGET",
                "condition_id": "COND-TESTS",
                "revision": 2,
                "prior_revision": 1,
                "repair_job_id": "JOB-REPAIR",
                "verifier_assignment_id": "VASS-CURRENT",
                "finding_ids": ["FIND-TEST"],
                "status": "pending",
                "condition_result_id": None,
                "recorded_at": now,
            }],
        }
        self.cli(
            "register", "--run", str(self.run_root),
            "--definition", str(self.write("gates.json", definition)),
        )
        return load_trusted_run(self.run_root)[2]

    def test_stale_gate_rejected_and_current_pass_accepts_target(self) -> None:
        from graph_v6 import TargetAccepter, VerificationResultApplier

        graph = self.valid_graph()
        stale = dict(graph._verifier_assignments["VASS-CURRENT"])
        stale.update({"assignment_id": "VASS-STALE", "target_gate_revision": 1})
        graph._verifier_assignments["VASS-STALE"] = stale
        applier = VerificationResultApplier(graph)
        with self.assertRaisesRegex(RuntimeError, "stale revision"):
            applier.apply_verification_result("VASS-STALE", "pass")
        result = applier.apply_verification_result(
            "VASS-CURRENT", "pass", condition_result_id="CONDRES-CURRENT",
        )
        accepted = TargetAccepter(graph).accept_target(
            "JOB-TARGET", "VASS-CURRENT", result["verdict"]
        )
        self.assertTrue(accepted["history_preserved"])
        self.assertEqual(graph._target_acceptances["JOB-TARGET"]["target_gate_revision"], 2)


class SealingAndCancellationTest(ControlPlaneCase):
    def test_typed_unsuccessful_goal_decision_seals_without_false_success(self) -> None:
        self.register(role="goal_judge")
        dispatch, attempt = self.prepare_and_launch()
        _run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        judgment = {
            "schema_version": 6,
            "judgment_id": "JUDGE-NO-PROGRESS",
            "goal_gate_id": "GATE-ONE",
            "run_id": "cycle-one",
            "cycle_id": "CYC-ONE",
            "graph_revision": graph.graph_revision,
            "producer_job_id": "JOB-ONE",
            "decision": "BLOCKED_NO_PROGRESS",
            "evidence_refs": [],
            "reason": "bounded alternatives exhausted",
            "recorded_at": "2026-08-01T00:00:00Z",
        }
        result = self.response(dispatch, attempt, goal_judgment=judgment)
        self.assertEqual(result["terminal"]["outcome_type"], "no_progress")
        run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(graph.status, "sealed")

    def test_false_goal_achieved_with_open_batch_gets_same_session_correction(self) -> None:
        _run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        batch = {
            "schema_version": 6,
            "batch_id": "BATCH-OPEN",
            "campaign_id": graph.envelope["campaign_id"],
            "cycle_id": "CYC-OPEN",
            "graph_generation": 1,
            "owner_authority_id": graph.envelope["authority_id"],
            "status": "open",
            "job_ids": ["JOB-ONE"],
            "mandatory_job_ids": ["JOB-ONE"],
            "required_gate_ids": [],
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
        self.register(role="goal_judge", batches=[batch])
        dispatch, attempt = self.prepare_and_launch()
        _run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        judgment = {
            "schema_version": 6,
            "judgment_id": "JUDGE-RESULT",
            "goal_gate_id": "GATE-ONE",
            "run_id": "cycle-one",
            "cycle_id": "CYC-OPEN",
            "graph_revision": graph.graph_revision,
            "producer_job_id": "JOB-ONE",
            "decision": "GOAL_ACHIEVED",
            "evidence_refs": [],
            "reason": "claimed too early",
            "recorded_at": "2026-08-01T00:00:00Z",
        }
        result = self.response(dispatch, attempt, goal_judgment=judgment)
        self.assertEqual(result["operation"], "resume_job")
        self.assertIn("batch BATCH-OPEN is open", result["correction"])
        self.assertEqual(load_trusted_run(self.run_root)[0]["status"], "active")

    def test_cancellation_seals_and_late_response_is_nonauthoritative(self) -> None:
        self.register(role="work_planner_architect")
        dispatch, attempt = self.prepare_and_launch()
        canceled = self.cli(
            "cancel", "--run", str(self.run_root), "--reason", "operator stop",
        )
        self.assertEqual(canceled["run_status"], "cancelled")
        late = self.response(dispatch, attempt, response_id="RESP-LATE")
        self.assertFalse(late["authoritative"])
        run, _setup, graph, _adapter = load_trusted_run(self.run_root)
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(graph.status, "sealed")


if __name__ == "__main__":
    unittest.main()
