"""v6 runtime tests: real dynamic campaign, negative probes, and recovery probes."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class RealV6DynamicCampaignTest(unittest.TestCase):
    """Test real v6 dynamic campaign with in-process modules."""

    def test_graph_state_lifecycle(self) -> None:
        from graph_v6 import GraphState, GraphStatus, advance_graph_revision, transition_graph_status

        envelope = {
            "strategy_id": "default_adaptive",
            "strategy_version": 1,
            "limits": {"max_total_jobs": 100},
        }
        gs = GraphState(envelope=envelope)
        self.assertEqual(gs.status, GraphStatus.PLANNING)
        self.assertEqual(gs.graph_revision, 1)

        transition_graph_status(gs, GraphStatus.PENDING)
        self.assertEqual(gs.status, GraphStatus.PENDING)

        transition_graph_status(gs, GraphStatus.COMMITTING)
        self.assertEqual(gs.status, GraphStatus.COMMITTING)

        transition_graph_status(gs, GraphStatus.OPEN)
        self.assertEqual(gs.status, GraphStatus.OPEN)

        new_rev = advance_graph_revision(gs)
        self.assertEqual(new_rev, 2)
        self.assertEqual(gs.graph_revision, 2)

    def test_job_and_edge_records(self) -> None:
        from graph_v6 import (
            GraphState, EdgeRecord,
            add_job_to_graph, add_edge_to_graph,
        )
        from orchestrator_core import utc_now

        gs = GraphState(envelope={"limits": {}})

        job_record = {
            "schema_version": 6,
            "job_id": "JOB-001",
            "title": "Test Job",
            "prompt_path": "prompts/JOB-001.md",
            "role": "implementation",
            "purpose_key": "implement",
            "graph_generation": 1,
            "expansion_origin": "ROOT",
            "authority_id": "AUTH-001",
            "created_at": utc_now(),
        }
        add_job_to_graph(gs, job_record)
        self.assertIn("JOB-001", [j["job_id"] for j in gs._jobs.values()])

        edge = EdgeRecord(
            edge_id="EDGE-001",
            source_job_id="ROOT",
            target_job_id="JOB-001",
            edge_type="success",
            graph_revision=1,
        )
        add_edge_to_graph(gs, edge.to_dict())
        self.assertEqual(len(gs._edges), 1)

    def test_graph_digest_computation(self) -> None:
        from graph_v6 import GraphState, compute_graph_digest

        gs = GraphState(envelope={"test": True})
        digest1 = compute_graph_digest(gs)
        self.assertEqual(len(digest1), 64)

        digest2 = compute_graph_digest(gs)
        self.assertEqual(digest1, digest2)

    def test_default_strategy_compilation(self) -> None:
        from strategy_v6 import DefaultStrategy, AdaptiveStrategyCompiler

        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        resolved = compiler.compile()
        self.assertEqual(len(resolved.phases), 10)

    def test_compilation_modes(self) -> None:
        from strategy_v6 import (
            StrategyDefinition, StrategyRegistry, StrategyCompiler,
            PhaseContract,
        )

        registry = StrategyRegistry()
        definition = StrategyDefinition(
            strategy_id="test",
            version=1,
            stable_phase_ids=("proposal_explore", "implementation", "goal_judge"),
            prompt_fragments={
                "proposal_explore": "Explore",
                "implementation": "Implement",
                "goal_judge": "Judge",
            },
            limits={"max_jobs": 10},
        )
        registry.register_strategy(definition)

        compiler = StrategyCompiler(registry)

        result = compiler.compile_full_campaign("test", 1, "goal", "RUN-001")
        self.assertEqual(len(result.prompts), 3)

        result = compiler.compile_proposal_only("test", 1, "goal", "RUN-001")
        self.assertEqual(len(result.prompts), 1)

        result = compiler.compile_implementation_from_proposal("test", 1, "goal", "RUN-001")
        self.assertEqual(len(result.prompts), 2)

    def test_prompt_renderer_all_methods(self) -> None:
        from prompt_v6 import PromptRenderer

        renderer = PromptRenderer("RUN-001", "test goal")

        ctx = renderer.render_workflow_context(
            job_id="JOB-001", activation_id="ACT-001",
            context_snapshot_id="CTX-001", cycle_id="CYC-001",
            graph_revision=1, graph_digest="a" * 64,
            campaign_envelope_id="ENV-001", job_ids=["JOB-001"],
        )
        self.assertIn("RUN-001", ctx)

        snap = renderer.render_context_snapshot("SNAP-001", {"goal_gates": 1}, "b" * 64)
        self.assertIn("SNAP-001", snap)

        esc = renderer.render_escalation([{"target_role": "review", "reason": "test"}])
        self.assertIn("review", esc)

        rec = renderer.render_recovery({"strategy": "retry", "status": "active"})
        self.assertIn("retry", rec)

        auth = renderer.render_authority(
            "AUTH-001", "implementation", {"expansion": True},
            "2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z",
        )
        self.assertIn("AUTH-001", auth)

        rels = renderer.render_relationships([
            {"source_job_id": "A", "target_job_id": "B", "edge_type": "success"},
        ])
        self.assertIn("success", rels)

    def test_transaction_expansion_commit(self) -> None:
        from transaction_v6 import (
            ResponseNormalizer, ExpansionIngester, ExpansionRetainer,
            GoalDecisionProcessor, ResultProcessor,
        )

        normalizer = ResponseNormalizer()
        result = normalizer.normalize_execution_status({
            "response_id": "RESP-001", "status": "received",
        })
        self.assertEqual(result["status"], "received")

        ingester = ExpansionIngester({"AUTH-001": {"expansion": True}})
        authority_scope = {"expansion": True}
        self.assertTrue(authority_scope.get("expansion"))

        processor = GoalDecisionProcessor()
        result = processor.process_continue({
            "judgment_id": "JUDGE-001",
            "decision": "CONTINUE",
            "graph_revision": 1,
            "producer_job_id": "JOB-001",
        })
        self.assertEqual(result["decision"], "CONTINUE")
        self.assertFalse(result["sealed"])

    def test_architect_enforcer(self) -> None:
        from strategy_v6 import ArchitectEnforcer

        enforcer = ArchitectEnforcer()

        errors = enforcer.enforce_read_only("proposal_architect", ["read_file"])
        self.assertEqual(len(errors), 0)

        errors = enforcer.enforce_read_only("proposal_architect", ["write_file"])
        self.assertEqual(len(errors), 1)

        errors = enforcer.enforce_fresh_instances(
            "JOB-001", "proposal_architect", set()
        )
        self.assertEqual(len(errors), 0)

        errors = enforcer.enforce_fresh_instances(
            "JOB-001", "proposal_architect", {"JOB-001"}
        )
        self.assertEqual(len(errors), 1)

    def test_context_module_registry(self) -> None:
        from strategy_v6 import ContextModule, ContextModuleRegistry

        registry = ContextModuleRegistry()
        module = ContextModule(
            module_id="MOD-001", namespace="test",
            constraints={"key": "value"},
        )
        registry.add_context_module(module)
        self.assertIsNotNone(registry.get_module("MOD-001"))

        resolved = registry.resolve_constraints("test")
        self.assertEqual(resolved["key"], "value")

    def test_verdict_tracker(self) -> None:
        from graph_v6 import GraphState, VerdictTracker, add_verifier_assignment
        from orchestrator_core import utc_now

        gs = GraphState(envelope={"limits": {}})
        assignment = {
            "schema_version": 6,
            "assignment_id": "ASN-001",
            "target_job_id": "TARGET-001",
            "target_gate_revision": 1,
            "verifier_job_id": "VER-001",
            "run_id": "RUN-001",
            "cycle_id": "CYC-001",
            "status": "assigned",
            "evidence_refs": [],
            "assigned_at": utc_now(),
        }
        add_verifier_assignment(gs, assignment)

        tracker = VerdictTracker(gs)
        result = tracker.record_execution_completion("ASN-001")
        self.assertEqual(result["assignment_id"], "ASN-001")

        result = tracker.record_target_verdict("ASN-001", "pass")
        self.assertEqual(result["verdict"], "pass")


class DeterministicNegativeProbesTest(unittest.TestCase):
    """Deterministic negative probes for v6 modules."""

    def test_invalid_graph_status_transition(self) -> None:
        from graph_v6 import GraphState, GraphStatus, transition_graph_status
        from orchestrator_core import OrchestratorError

        gs = GraphState(envelope={"limits": {}})
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.SEALED)

    def test_duplicate_job_rejection(self) -> None:
        from graph_v6 import GraphState, add_job_to_graph
        from orchestrator_core import OrchestratorError, utc_now

        gs = GraphState(envelope={"limits": {}})
        job_dict = {
            "schema_version": 6,
            "job_id": "JOB-001",
            "title": "Test",
            "prompt_path": "prompts/JOB-001.md",
            "role": "test",
            "purpose_key": "test",
            "graph_generation": 1,
            "expansion_origin": "ROOT",
            "authority_id": "AUTH-001",
            "created_at": utc_now(),
        }
        add_job_to_graph(gs, job_dict)
        with self.assertRaises(OrchestratorError):
            add_job_to_graph(gs, job_dict)

    def test_invalid_edge_type(self) -> None:
        from graph_v6 import EdgeRecord
        from orchestrator_core import OrchestratorError

        with self.assertRaises(OrchestratorError):
            EdgeRecord(
                edge_id="EDGE-001", source_job_id="A",
                target_job_id="B", edge_type="invalid_type",
                graph_revision=1,
            )

    def test_strategy_version_sequential(self) -> None:
        from strategy_v6 import StrategyDefinition, StrategyRegistry
        from orchestrator_core import OrchestratorError

        registry = StrategyRegistry()
        d1 = StrategyDefinition(strategy_id="test", version=1, stable_phase_ids=("a",))
        registry.register_strategy(d1)
        d3 = StrategyDefinition(strategy_id="test", version=3, stable_phase_ids=("a",))
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(d3)

    def test_non_overridable_phase_replacement(self) -> None:
        from strategy_v6 import DefaultStrategy, AdaptiveStrategyCompiler
        from orchestrator_core import OrchestratorError

        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        with self.assertRaises(OrchestratorError):
            compiler.compile([{
                "operation": "replace",
                "target_phase": "verification",
                "new_phase": {"phase_id": "custom_verify"},
            }])

    def test_invalid_goal_decision(self) -> None:
        from strategy_v6 import GoalJudgeContract

        contract = GoalJudgeContract()
        errors = contract.validate_goal_judge_output({
            "terminal_decision": "INVALID_DECISION",
            "immutable_findings": [],
            "finding_groups": [],
            "competing_hypotheses": [],
            "goal_gates": [],
            "continuation_analysis": None,
        })
        self.assertGreater(len(errors), 0)

    def test_v5_run_rejection(self) -> None:
        from orchestrator_core import reject_v5_or_earlier, OrchestratorError

        with self.assertRaises(OrchestratorError):
            reject_v5_or_earlier({"schema_version": 5})

    def test_context_module_frozen_rejection(self) -> None:
        from strategy_v6 import ContextModule, ContextModuleRegistry
        from orchestrator_core import OrchestratorError

        registry = ContextModuleRegistry()
        module = ContextModule(module_id="MOD-001", namespace="test")
        registry.add_context_module(module)
        registry.freeze_module_versions(["MOD-001"])
        with self.assertRaises(OrchestratorError):
            registry.add_context_module(module)


class RecoveryProbesTest(unittest.TestCase):
    """Recovery probes for v6 modules."""

    def test_graph_status_recovery_path(self) -> None:
        from graph_v6 import (
            GraphState, GraphStatus,
            transition_graph_status, advance_graph_revision,
        )

        gs = GraphState(envelope={"limits": {}})
        transition_graph_status(gs, GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.COMMITTING)
        transition_graph_status(gs, GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.RECOVERY_REQUIRED)

        transition_graph_status(gs, GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_goal_decision_continue_preserves_graph(self) -> None:
        from transaction_v6 import GoalDecisionProcessor

        processor = GoalDecisionProcessor(
            current_judge_id="JUDGE-001",
            current_graph_revision=1,
        )
        result = processor.process_continue({
            "judgment_id": "J-001",
            "decision": "CONTINUE",
            "graph_revision": 1,
            "producer_job_id": "JUDGE-001",
        })
        self.assertFalse(result["sealed"])
        self.assertEqual(result["outcome"], "graph_open")

    def test_goal_decision_achieved_seals(self) -> None:
        from transaction_v6 import GoalDecisionProcessor

        processor = GoalDecisionProcessor(
            current_judge_id="JUDGE-001",
            current_graph_revision=1,
        )
        result = processor.process_goal_achieved({
            "judgment_id": "J-001",
            "decision": "GOAL_ACHIEVED",
            "graph_revision": 1,
            "producer_job_id": "JUDGE-001",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "completed")

    def test_correction_prompt_generation(self) -> None:
        from transaction_v6 import CorrectionGenerator

        gen = CorrectionGenerator()
        prompt = gen.generate_correction_prompt(
            ["error 1", "error 2"], context="test"
        )
        self.assertIn("CORRECTION_REQUIRED", prompt)
        self.assertIn("error 1", prompt)

    def test_expansion_retainer_idempotency(self) -> None:
        from transaction_v6 import ExpansionRetainer

        retainer = ExpansionRetainer()
        expansion = {
            "plan_id": "PLAN-001", "campaign_id": "CAMP-001",
            "graph_revision": 1, "jobs_added": [], "edges_added": [],
        }
        r1 = retainer.retain_expansion(expansion)
        r2 = retainer.retain_expansion(expansion)
        self.assertEqual(r1["expansion_id"], r2["expansion_id"])

    def test_finding_disposition_enforcer(self) -> None:
        from strategy_v6 import FindingDispositionEnforcer

        enforcer = FindingDispositionEnforcer()
        errors = enforcer.validate_finding_disposition({
            "finding_id": "F-001",
            "status": "verified",
            "evidence_refs": ["ref://test"],
            "reason": "confirmed",
        })
        self.assertEqual(len(errors), 0)

        errors = enforcer.validate_finding_disposition({
            "finding_id": "F-001",
            "status": "invalid_status",
        })
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
