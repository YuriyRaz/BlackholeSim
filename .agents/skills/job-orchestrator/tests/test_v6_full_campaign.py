"""End-to-end verification tests for v6 full campaign scenarios.

Task 15.5: Full campaign scenarios for direct repair, multi-job implementation,
nested OpenSpec redesign, repeated Architect loops, cycle commit/push, and
final trusted goal achievement.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError, stable_id, content_hash  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    add_batch,
    add_edge_to_graph,
    add_expansion,
    add_job_to_graph,
    compute_graph_digest,
    get_job,
    get_jobs,
    transition_graph_status,
    advance_graph_revision,
    validate_prospective_graph,
)
from transaction_v6 import (  # noqa: E402
    GoalDecisionProcessor,
    ResultProcessor,
    ResponseNormalizer,
)
from strategy_v6 import (  # noqa: E402
    DefaultStrategy,
    GoalJudgeContract,
    HypothesisContract,
    SynthesisContract,
    WorkPlannerContract,
    PathSelectionRules,
    ArchitectEnforcer,
    DurableSolutionEnforcer,
    FindingDispositionEnforcer,
    AdaptiveStrategyCompiler,
    AdaptiveStrategyRegistry,
)
from progress_v6 import (  # noqa: E402
    DuplicateDetector,
    StagnationHandler,
    LimitOutcomeEmitter,
    OutcomeType,
    ProgressCounter,
)


_VALID_AUTH = "AUTH-AAAAAAAAAAAAAAAAAAAA"


def _envelope() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": "ENV-AAAAAAAAAAAAAAAAAAAA",
        "campaign_id": "CMP-AAAAAAAAAAAAAAAAAAAA",
        "goal": "fix broken feature",
        "strategy": "full-campaign",
        "version": 1,
        "authority_id": _VALID_AUTH,
        "limits": {"max_cycles": 10, "max_jobs_per_cycle": 5, "max_total_jobs": 50},
        "created_at": "2026-01-15T10:30:00Z",
    }


def _job_def(job_id: str, role: str = "implementation", gen: int = 1) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "title": f"test-{job_id}",
        "prompt_path": f"prompts/{job_id}.md",
        "role": role,
        "purpose_key": "test-purpose",
        "graph_generation": gen,
        "expansion_origin": "ROOT-00000000000000000000",
        "authority_id": _VALID_AUTH,
        "created_at": "2026-01-15T10:30:00Z",
    }


def _edge_def(edge_id: str, src: str, tgt: str, etype: str = "success") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "edge_id": edge_id,
        "source_job_id": src,
        "target_job_id": tgt,
        "edge_type": etype,
        "graph_revision": 1,
        "created_at": "2026-01-15T10:30:00Z",
    }


class DirectRepairScenarioTest(unittest.TestCase):
    """Test direct repair campaign scenario."""

    def test_direct_repair_fires_when_conditions_met(self) -> None:
        rules = PathSelectionRules()
        conditions = {
            "is_local": True, "is_reversible": True,
            "no_material_change": True, "single_cause": True,
        }
        self.assertTrue(rules.direct_repair_conditions(**conditions))
        errors = rules.validate_path_selection("direct_repair", conditions)
        self.assertEqual(errors, [])

    def test_direct_repair_adds_single_job(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        repair_job = _job_def("JOB-REPAIR-1", role="implementation")
        add_job_to_graph(gs, repair_job)
        edge = _edge_def("EDGE-R1", "JOB-TARGET", "JOB-REPAIR-1")
        gs._jobs["JOB-TARGET"] = _job_def("JOB-TARGET")
        add_edge_to_graph(gs, edge)

        jobs = get_jobs(gs)
        self.assertIn("JOB-REPAIR-1", jobs)
        self.assertIn("JOB-TARGET", jobs)

    def test_direct_repair_progress(self) -> None:
        counter = ProgressCounter()
        gates = [{"gate_id": "g1", "status": "pass"}]
        self.assertEqual(counter.count_passing_gates(gates), 1)

    def test_direct_repair_goal_achieved(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_goal_achieved({
            "judgment_id": "JG-1",
            "decision": "GOAL_ACHIEVED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])


class MultiJobImplementationTest(unittest.TestCase):
    """Test multi-job implementation scenario."""

    def test_multi_job_expansion(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        for i in range(3):
            add_job_to_graph(gs, _job_def(f"JOB-IMPL-{i}"))

        add_edge_to_graph(gs, _edge_def("E1", "JOB-IMPL-0", "JOB-IMPL-1"))
        add_edge_to_graph(gs, _edge_def("E2", "JOB-IMPL-1", "JOB-IMPL-2"))

        jobs = get_jobs(gs)
        self.assertEqual(len([j for j in jobs if j.startswith("JOB-IMPL-")]), 3)

    def test_multi_job_synthesis(self) -> None:
        processor = ResultProcessor()
        result = processor.process_synthesis_result({
            "schema_version": SCHEMA_VERSION,
            "synthesis_id": "SYN-1",
            "hypothesis_result_ids": ["H1", "H2"],
            "producer_job_id": "JOB-SYN",
            "cycle_id": "CYC-1",
            "conclusion": "root_cause_identified",
            "evidence_refs": [],
            "summary": "Found root cause",
            "recorded_at": "2026-01-15T10:30:00Z",
        })
        self.assertIn("synthesis_id", result)
        self.assertEqual(result["conclusion"], "root_cause_identified")

    def test_multi_job_work_plan(self) -> None:
        processor = ResultProcessor()
        result = processor.process_work_plan({
            "schema_version": SCHEMA_VERSION,
            "plan_id": "WP-1",
            "plan_type": "implementation_set",
            "cycle_id": "CYC-1",
            "producer_job_id": "JOB-WP",
            "targets": [{"target_id": "T1", "target_type": "job"}],
            "created_at": "2026-01-15T10:30:00Z",
        })
        self.assertEqual(result["plan_type"], "implementation_set")


class NestedOpenSpecRedesignTest(unittest.TestCase):
    """Test nested OpenSpec redesign scenario."""

    def test_openspec_batch_condition(self) -> None:
        rules = PathSelectionRules()
        self.assertTrue(rules.openspec_batch_conditions(
            material_redesign=True,
            migration_required=True,
        ))

    def test_openspec_batch_selection_valid(self) -> None:
        rules = PathSelectionRules()
        conditions = {"material_redesign": True, "contract_change": True}
        errors = rules.validate_path_selection("openspec_batch", conditions)
        self.assertEqual(errors, [])

    def test_openspec_batch_adds_batch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        add_batch(gs, {
            "batch_id": "BATCH-OS-1",
            "status": "open",
            "job_ids": ["JOB-OS-0", "JOB-OS-1"],
        })
        self.assertEqual(gs._batches["BATCH-OS-1"]["status"], "open")
        self.assertEqual(len(gs._batches["BATCH-OS-1"]["job_ids"]), 2)


class RepeatedArchitectLoopsTest(unittest.TestCase):
    """Test repeated Architect loop detection and stagnation handling."""

    def test_detect_stagnation(self) -> None:
        handler = StagnationHandler(max_failures=3)
        for i in range(3):
            result = handler.detect_stagnation("item-1", f"failure-{i}")
        self.assertTrue(result["is_stagnant"])
        self.assertTrue(result["requires_alternate_approach"])

    def test_no_stagnation_below_threshold(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.detect_stagnation("item-1")
        self.assertFalse(result["is_stagnant"])
        self.assertEqual(result["failure_count"], 1)

    def test_material_difference_check(self) -> None:
        handler = StagnationHandler()
        original = {"hypothesis_text": "H1", "evidence_source": "E1"}
        proposed_different = {"hypothesis_text": "H2", "evidence_source": "E1"}
        result = handler.require_material_difference(original, proposed_different)
        self.assertTrue(result["is_materially_different"])

    def test_no_material_difference(self) -> None:
        handler = StagnationHandler()
        original = {"hypothesis_text": "H1", "evidence_source": "E1"}
        proposed_same = {"hypothesis_text": "H1", "evidence_source": "E1"}
        result = handler.require_material_difference(original, proposed_same)
        self.assertFalse(result["is_materially_different"])

    def test_promote_to_multi_job(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_multi_job("item-1", 3)
        self.assertTrue(result["should_promote"])
        self.assertEqual(result["promotion_type"], "multi_job_repair")

    def test_promote_to_openspec(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_openspec("item-1", 3, needs_material_redesign=True)
        self.assertTrue(result["should_promote"])
        self.assertEqual(result["promotion_type"], "openspec_work")

    def test_architect_read_only(self) -> None:
        enforcer = ArchitectEnforcer()
        errors = enforcer.enforce_read_only("proposal_architect", ["write_file", "read_file"])
        self.assertTrue(any("write_file" in e for e in errors))

    def test_architect_fresh_instances(self) -> None:
        enforcer = ArchitectEnforcer()
        errors = enforcer.enforce_fresh_instances(
            "JOB-1", "proposal_architect", {"JOB-1"}
        )
        self.assertTrue(any("reuse" in e for e in errors))

    def test_no_self_verification(self) -> None:
        enforcer = ArchitectEnforcer()
        errors = enforcer.enforce_no_self_verification(
            "JOB-1", "JOB-1", "verifier", "target"
        )
        self.assertTrue(any("self-verification" in e for e in errors))


class CycleCommitPushTest(unittest.TestCase):
    """Test cycle commit/push scenario."""

    def test_cycle_progress_fingerprint(self) -> None:
        from progress_v6 import ProgressFingerprintComputer, FingerprintRecord
        computer = ProgressFingerprintComputer()
        record = FingerprintRecord(
            finding_signatures=["sig1"],
            goal_gates=[{"gate_id": "g1", "status": "pass"}],
        )
        digest = computer.compute_fingerprint(record)
        self.assertEqual(len(digest), 64)

    def test_progress_counter(self) -> None:
        counter = ProgressCounter()
        gates = [
            {"gate_id": "g1", "status": "pass"},
            {"gate_id": "g2", "status": "fail"},
        ]
        self.assertEqual(counter.count_passing_gates(gates), 1)

    def test_duplicate_detection(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "H1", "finding_id": "F1"}
        result = detector.detect_duplicate_hypotheses(hyp)
        self.assertFalse(result["is_duplicate"])
        detector.record_hypothesis(hyp)
        result2 = detector.detect_duplicate_hypotheses(hyp)
        self.assertTrue(result2["is_duplicate"])

    def test_reject_without_new_evidence(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "H1", "finding_id": "F1"}
        detector.record_hypothesis(hyp)
        result = detector.reject_without_new_evidence(hyp, "hypothesis")
        self.assertTrue(result["rejected"])

    def test_limit_outcome_no_false_success(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": OutcomeType.GOAL_ACHIEVED.value}
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertTrue(len(errors) > 0)


class FinalTrustedGoalAchievementTest(unittest.TestCase):
    """Test final trusted goal achievement scenario."""

    def test_goal_achieved_seals_graph(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_goal_achieved_processor(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_goal_achieved({
            "judgment_id": "JG-1",
            "decision": "GOAL_ACHIEVED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "completed")

    def test_goal_judge_contract_validation(self) -> None:
        contract = GoalJudgeContract()
        output = {
            "immutable_findings": [{"finding_id": "F1", "severity": "high", "evidence": [], "description": "test", "confidence": 0.9}],
            "finding_groups": [{"group_id": "G1", "finding_ids": ["F1"], "plausibility": "high"}],
            "competing_hypotheses": [{"hypothesis_id": "H1", "hypothesis_text": "test", "predicted_observations": [], "falsifying_observations": [], "null_hypothesis": False}],
            "goal_gates": [{"gate_id": "GG1", "requirement": "fix bug", "status": "pass"}],
            "continuation_analysis": None,
            "terminal_decision": "GOAL_ACHIEVED",
        }
        errors = contract.validate_goal_judge_output(output)
        self.assertEqual(errors, [])

    def test_finding_disposition_enforcer(self) -> None:
        enforcer = FindingDispositionEnforcer()
        disposition = {
            "finding_id": "F1",
            "status": "verified",
            "evidence_refs": ["ref1"],
            "reason": "fixed and verified",
        }
        errors = enforcer.validate_finding_disposition(disposition)
        self.assertEqual(errors, [])

    def test_finding_without_disposition_blocks_goal(self) -> None:
        enforcer = FindingDispositionEnforcer()
        errors = enforcer.block_goal_without_disposition(
            finding_ids={"F1", "F2"},
            dispositioned_finding_ids={"F1"},
        )
        self.assertTrue(any("F2" in e for e in errors))

    def test_durable_solution_enforcer(self) -> None:
        enforcer = DurableSolutionEnforcer()
        repair = {"repair_type": "fix_cause", "description": "root cause fix"}
        errors = enforcer.enforce_durable_solution(repair)
        self.assertEqual(errors, [])

    def test_provisional_mitigation_blocks_goal(self) -> None:
        enforcer = DurableSolutionEnforcer()
        repair = {"is_provisional": True, "mitigation_label": "PROVISIONAL_MITIGATION"}
        errors = enforcer.prevent_mitigation_completion(repair, "GOAL_ACHIEVED")
        self.assertTrue(any("provisional" in e.lower() for e in errors))

    def test_hypothesis_contract_validation(self) -> None:
        contract = HypothesisContract()
        output = {
            "hypothesis_id": "H1",
            "finding_id": "F1",
            "predicted_observations": [{"observation": "test", "evidence_source": "file"}],
            "falsifying_observations": [{"observation": "no test", "evidence_source": "file"}],
            "primary_evidence": [{"ref": "run://test", "digest": "abc", "summary": "test"}],
            "confidence": 0.8,
            "result_state": "supported",
        }
        errors = contract.validate_hypothesis_output(output)
        self.assertEqual(errors, [])

    def test_synthesis_contract_validation(self) -> None:
        contract = SynthesisContract()
        output = {
            "synthesis_id": "S1",
            "consumed_hypothesis_ids": ["H1"],
            "conclusion": "root_cause_identified",
            "planning_constraints": {
                "supported_causes": ["cause1"],
                "refuted_causes": [],
                "unresolved_causes": [],
            },
            "evidence_refs": [],
        }
        errors = contract.validate_synthesis_output(output, all_settled_hypothesis_ids=["H1"])
        self.assertEqual(errors, [])

    def test_work_planner_contract_validation(self) -> None:
        contract = WorkPlannerContract()
        output = {
            "plan_id": "WP1",
            "plan_type": "direct_repair",
            "selected_decision": "direct_repair",
            "targets": [{"target_id": "T1", "target_type": "file"}],
            "cycle_id": "CYC-1",
        }
        errors = contract.validate_work_planner_output(output)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
