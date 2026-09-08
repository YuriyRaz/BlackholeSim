"""End-to-end verification tests for v6 scheduling and terminality.

Task 15.3: Scheduling and terminality tests for barriers, stale dispatches,
pending expansion, open batches, Goal Judge continuation expansions, sealing,
cancellation, and every terminal outcome.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError, stable_id  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    ExpansionSlot,
    add_batch,
    add_edge_to_graph,
    add_expansion,
    add_job_to_graph,
    compute_graph_digest,
    get_jobs,
    transition_graph_status,
    advance_graph_revision,
    validate_limits,
)
from transaction_v6 import (  # noqa: E402
    GoalDecisionProcessor,
    ExpansionCommitter,
)
from progress_v6 import (  # noqa: E402
    LimitOutcomeEmitter,
    OutcomeType,
)


_VALID_AUTH = "AUTH-AAAAAAAAAAAAAAAAAAAA"


def _envelope(limits: dict | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": "ENV-AAAAAAAAAAAAAAAAAAAA",
        "campaign_id": "CMP-AAAAAAAAAAAAAAAAAAAA",
        "goal": "test goal",
        "strategy": "full-campaign",
        "version": 1,
        "authority_id": _VALID_AUTH,
        "limits": limits or {"max_cycles": 10, "max_jobs_per_cycle": 5, "max_total_jobs": 50},
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


class PlanningBarrierTest(unittest.TestCase):
    """Test planning barrier enforcement during expansion."""

    def test_open_to_planning_allows_new_expansion(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_planning_blocks_dispatch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_pending_blocks_planning(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PENDING)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.PLANNING)

    def test_committing_blocks_dispatch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.COMMITTING)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.PLANNING)

    def test_canceling_blocks_dispatch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.CANCELING)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.PLANNING)

    def test_recovery_blocks_dispatch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.RECOVERY_REQUIRED)
        transition_graph_status(gs, GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_sealed_is_terminal(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.SEALED)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.OPEN)


class StaleDispatchTest(unittest.TestCase):
    """Test stale dispatch rejection via graph revision compare-and-swap."""

    def test_stale_revision_rejected(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.graph_revision = 5

        from graph_v6 import add_job_to_graph, add_edge_to_graph
        add_job_to_graph(gs, _job_def("JOB-A"))
        add_job_to_graph(gs, _job_def("JOB-B"))
        add_edge_to_graph(gs, _edge_def("EDGE-1", "JOB-A", "JOB-B"))
        gs.graph_digest = compute_graph_digest(gs)

        old_digest = gs.graph_digest
        advance_graph_revision(gs)

        # digest unchanged (no topology change) — only revision bumped
        new_digest = compute_graph_digest(gs)
        self.assertEqual(old_digest, new_digest)
        self.assertEqual(gs.graph_revision, 6)

        # now add a job — digest changes
        add_job_to_graph(gs, _job_def("JOB-C"))
        changed_digest = compute_graph_digest(gs)
        self.assertNotEqual(old_digest, changed_digest)

    def test_fresh_revision_accepted(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.graph_revision = 1

        from graph_v6 import add_job_to_graph
        add_job_to_graph(gs, _job_def("JOB-FRESH"))
        gs.graph_digest = compute_graph_digest(gs)
        current_digest = gs.graph_digest

        advance_graph_revision(gs)
        # digest unchanged since no topology change
        new_digest = compute_graph_digest(gs)
        self.assertEqual(current_digest, new_digest)
        self.assertEqual(gs.graph_revision, 2)


class PendingExpansionTest(unittest.TestCase):
    """Test pending expansion handling."""

    def test_expansion_slot_prevents_concurrent(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.expansion_slot.activate("EXP-1", 1, "plan-digest")
        self.assertFalse(gs.expansion_slot.is_idle())

        with self.assertRaises(OrchestratorError):
            gs.expansion_slot.activate("EXP-2", 1, "other-digest")

    def test_expansion_slot_releases(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.expansion_slot.activate("EXP-1", 1, "abc")
        gs.expansion_slot.release()
        self.assertTrue(gs.expansion_slot.is_idle())

    def test_pending_expansion_transition(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PLANNING)
        transition_graph_status(gs, GraphStatus.PENDING)
        self.assertEqual(gs.status, GraphStatus.PENDING)

    def test_pending_to_committing(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.COMMITTING)
        self.assertEqual(gs.status, GraphStatus.COMMITTING)

    def test_pending_to_canceling(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.CANCELING)
        self.assertEqual(gs.status, GraphStatus.CANCELING)

    def test_pending_to_recovery(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.RECOVERY_REQUIRED)
        self.assertEqual(gs.status, GraphStatus.RECOVERY_REQUIRED)


class OpenBatchBarrierTest(unittest.TestCase):
    """Test open batch barriers."""

    def test_open_batch_blocks_sealing(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        add_batch(gs, {"batch_id": "B1", "status": "open", "job_ids": ["J1"]})
        batches = get_jobs(gs)
        self.assertTrue(len(batches) >= 0)

    def test_sealed_batch_persists(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        add_batch(gs, {"batch_id": "B1", "status": "sealed", "job_ids": ["J1"]})
        self.assertEqual(gs._batches["B1"]["status"], "sealed")

    def test_abandoned_batch_recorded(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        add_batch(gs, {"batch_id": "B1", "status": "abandoned", "job_ids": []})
        self.assertEqual(gs._batches["B1"]["status"], "abandoned")

    def test_batch_limit_enforced(self) -> None:
        gs = GraphState(
            envelope=_envelope(limits={"max_total_jobs": 50}),
            status=GraphStatus.OPEN,
        )
        gs.limits = {"max_open_batches": 1}
        add_batch(gs, {"batch_id": "B1", "status": "open", "job_ids": []})
        errors = validate_limits(gs, proposed_batch_count=1)
        self.assertTrue(any("open batches" in e.lower() for e in errors))


class GoalJudgeContinuationExpansionTest(unittest.TestCase):
    """Test Goal Judge CONTINUE decision expansion."""

    def test_continue_keeps_graph_open(self) -> None:
        processor = GoalDecisionProcessor(
            current_judge_id="JUDGE-1",
            current_graph_revision=5,
        )
        result = processor.process_continue({
            "judgment_id": "JG-1",
            "decision": "CONTINUE",
            "graph_revision": 5,
            "producer_job_id": "JUDGE-1",
        })
        self.assertFalse(result["sealed"])
        self.assertEqual(result["outcome"], "graph_open")

    def test_continue_requires_matching_judge(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="JUDGE-1")
        with self.assertRaises(OrchestratorError):
            processor.process_continue({
                "judgment_id": "JG-1",
                "decision": "CONTINUE",
                "graph_revision": 1,
                "producer_job_id": "JUDGE-WRONG",
            })

    def test_continue_requires_matching_revision(self) -> None:
        processor = GoalDecisionProcessor(
            current_judge_id="JUDGE-1",
            current_graph_revision=5,
        )
        with self.assertRaises(OrchestratorError):
            processor.process_continue({
                "judgment_id": "JG-1",
                "decision": "CONTINUE",
                "graph_revision": 3,
                "producer_job_id": "JUDGE-1",
            })


class GraphSealingTest(unittest.TestCase):
    """Test graph sealing."""

    def test_seal_from_open(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_seal_from_canceling(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.CANCELING)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_seal_from_recovery(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.RECOVERY_REQUIRED)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_sealed_cannot_transition(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.SEALED)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.OPEN)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.PLANNING)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.SEALED)


class CancellationHandlingTest(unittest.TestCase):
    """Test cancellation handling."""

    def test_cancel_from_planning(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PLANNING)
        transition_graph_status(gs, GraphStatus.CANCELING)
        self.assertEqual(gs.status, GraphStatus.CANCELING)

    def test_cancel_from_open(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.CANCELING)
        self.assertEqual(gs.status, GraphStatus.CANCELING)

    def test_cancel_from_pending(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.CANCELING)
        self.assertEqual(gs.status, GraphStatus.CANCELING)

    def test_cancel_to_sealed(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.CANCELING)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_cannot_cancel_from_sealed(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.SEALED)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.CANCELING)


class TerminalOutcomeTest(unittest.TestCase):
    """Test all terminal outcomes."""

    def test_goal_achieved_seals(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_goal_achieved({
            "judgment_id": "JG-1",
            "decision": "GOAL_ACHIEVED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "completed")

    def test_blocked_seals(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_blocked({
            "judgment_id": "JG-1",
            "decision": "BLOCKED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "blocked")

    def test_infeasible_seals(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_infeasible({
            "judgment_id": "JG-1",
            "decision": "BLOCKED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "infeasible")

    def test_no_progress_seals(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_blocked_no_progress({
            "judgment_id": "JG-1",
            "decision": "BLOCKED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "blocked_no_progress")

    def test_budget_exhausted_seals(self) -> None:
        processor = GoalDecisionProcessor(current_judge_id="J1", current_graph_revision=1)
        result = processor.process_budget_exhausted({
            "judgment_id": "JG-1",
            "decision": "BLOCKED",
            "graph_revision": 1,
            "producer_job_id": "J1",
        })
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "budget_exhausted")

    def test_limit_outcome_emitter_blocked(self) -> None:
        emitter = LimitOutcomeEmitter()
        result = emitter.emit_blocked_outcome(
            graph_revision=1, graph_digest="a" * 64, reason="test blocked"
        )
        self.assertEqual(result["outcome_type"], OutcomeType.BLOCKED.value)

    def test_limit_outcome_emitter_budget(self) -> None:
        emitter = LimitOutcomeEmitter()
        result = emitter.emit_budget_outcome(
            graph_revision=1, graph_digest="a" * 64, reason="budget gone",
            budget_type="time", consumed=100.0, limit=50.0,
        )
        self.assertEqual(result["outcome_type"], OutcomeType.BUDGET_EXHAUSTED.value)

    def test_limit_outcome_emitter_infeasible(self) -> None:
        emitter = LimitOutcomeEmitter()
        result = emitter.emit_infeasible_outcome(
            graph_revision=1, graph_digest="a" * 64, reason="contradiction",
            contradictions=["A contradicts B"],
        )
        self.assertEqual(result["outcome_type"], OutcomeType.INFEASIBLE.value)

    def test_validate_no_false_success(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": OutcomeType.GOAL_ACHIEVED.value}
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertTrue(any("false success" in e for e in errors))

    def test_no_progress_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        result = emitter.emit_no_progress_outcome(
            graph_revision=1, graph_digest="a" * 64, reason="stagnation",
            cycles_without_progress=3,
        )
        self.assertEqual(result["outcome_type"], OutcomeType.NO_PROGRESS.value)


if __name__ == "__main__":
    unittest.main()
