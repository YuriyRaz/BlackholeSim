"""Tests for Group 7: Dynamic Scheduling, Batches, and Terminality."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, SCHEMA_VERSION  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    PlanningBarrier,
    NextOperationSelector,
    DispatchValidator,
    EdgeReadinessChecker,
    BatchBarrier,
    GoalExpansionHandler,
    TerminalityChecker,
    TerminalOutcomeRecorder,
    compute_graph_digest,
    advance_graph_revision,
    add_job_to_graph,
    add_edge_to_graph,
    add_expansion,
    add_batch,
)


def _valid_id() -> str:
    return "T-ABCDEFGHIJKLMOPQRST"


def _valid_datetime() -> str:
    return "2026-01-15T10:30:00Z"


def _minimal_envelope() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": _valid_id(),
        "campaign_id": _valid_id(),
        "goal": "implement feature",
        "strategy": "full-campaign",
        "version": 1,
        "authority_id": _valid_id(),
        "limits": {
            "max_cycles": 10,
            "max_jobs_per_cycle": 5,
            "max_total_jobs": 50,
        },
        "created_at": _valid_datetime(),
    }


def _minimal_job_def(
    job_id: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    role: str = "implementation",
    purpose_key: str = "impl-main",
    expansion_origin: str = "ROOT",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "title": f"test-{job_id}",
        "prompt_path": f"prompts/{job_id}.md",
        "role": role,
        "purpose_key": purpose_key,
        "graph_generation": 1,
        "expansion_origin": expansion_origin,
        "authority_id": _valid_id(),
        "created_at": _valid_datetime(),
    }


def _minimal_edge_def(
    edge_id: str = "EDGE-AAAAAAAAAAAAAAAAAAAA",
    source: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    target: str = "JOB-BBBBBBBBBBBBBBBBBBBB",
    edge_type: str = "success",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "edge_id": edge_id,
        "source_job_id": source,
        "target_job_id": target,
        "edge_type": edge_type,
        "graph_revision": 1,
        "created_at": _valid_datetime(),
    }


def _minimal_expansion(
    expansion_id: str = "EXP-AAAAAAAAAAAAAAAAAAAA",
    status: str = "committed",
) -> dict:
    return {
        "expansion_id": expansion_id,
        "plan_id": "PLAN-1",
        "campaign_id": _valid_id(),
        "graph_revision": 1,
        "jobs_added": [],
        "edges_added": [],
        "status": status,
        "provenance": {
            "producer_job_id": _valid_id(),
            "authority_id": _valid_id(),
            "cycle_id": _valid_id(),
        },
        "created_at": _valid_datetime(),
    }


def _minimal_batch(
    batch_id: str = "BATCH-AAAAAAAAAAAAAAAAAAAA",
    status: str = "open",
    job_ids: list[str] | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "campaign_id": _valid_id(),
        "cycle_id": _valid_id(),
        "status": status,
        "job_ids": job_ids or [],
        "created_at": _valid_datetime(),
        "updated_at": _valid_datetime(),
    }


# ===========================================================================
# Task 7.1 Tests: Planning barrier enforcement
# ===========================================================================


class PlanningBarrierTest(unittest.TestCase):
    """Test PlanningBarrier class."""

    def test_acquire_planning_barrier_blocks_planning_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        with self.assertRaises(OrchestratorError) as ctx:
            PlanningBarrier.acquire_planning_barrier(gs)
        self.assertIn("planning barrier blocked", str(ctx.exception))

    def test_acquire_planning_barrier_blocks_pending_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PENDING)
        with self.assertRaises(OrchestratorError):
            PlanningBarrier.acquire_planning_barrier(gs)

    def test_acquire_planning_barrier_blocks_committing_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.COMMITTING)
        with self.assertRaises(OrchestratorError):
            PlanningBarrier.acquire_planning_barrier(gs)

    def test_acquire_planning_barrier_blocks_canceling_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.CANCELING)
        with self.assertRaises(OrchestratorError):
            PlanningBarrier.acquire_planning_barrier(gs)

    def test_acquire_planning_barrier_blocks_recovery_required(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.RECOVERY_REQUIRED)
        with self.assertRaises(OrchestratorError):
            PlanningBarrier.acquire_planning_barrier(gs)

    def test_acquire_planning_barrier_allows_open_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        PlanningBarrier.acquire_planning_barrier(gs)

    def test_acquire_planning_barrier_allows_sealed_status(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        PlanningBarrier.acquire_planning_barrier(gs)

    def test_validate_no_active_jobs_blocks_running(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "running"
        with self.assertRaises(OrchestratorError) as ctx:
            PlanningBarrier.validate_no_active_jobs(gs)
        self.assertIn("JOB-1", str(ctx.exception))

    def test_validate_no_active_jobs_blocks_dispatching(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "dispatching"
        with self.assertRaises(OrchestratorError):
            PlanningBarrier.validate_no_active_jobs(gs)

    def test_validate_no_active_jobs_allows_completed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        PlanningBarrier.validate_no_active_jobs(gs)

    def test_validate_no_pending_dispatch_blocks_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        gs._edges["EDGE-1"]["dispatch_status"] = "pending"
        with self.assertRaises(OrchestratorError) as ctx:
            PlanningBarrier.validate_no_pending_dispatch(gs)
        self.assertIn("EDGE-1", str(ctx.exception))

    def test_validate_no_pending_dispatch_allows_none(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        PlanningBarrier.validate_no_pending_dispatch(gs)

    def test_validate_single_expansion_slot_blocks_multiple(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp1 = _minimal_expansion("EXP-1", "pending")
        exp2 = _minimal_expansion("EXP-2", "planning")
        add_expansion(gs, exp1)
        add_expansion(gs, exp2)
        with self.assertRaises(OrchestratorError) as ctx:
            PlanningBarrier.validate_single_expansion_slot(gs)
        self.assertIn("2 active expansions", str(ctx.exception))

    def test_validate_single_expansion_slot_allows_one(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp1 = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp1)
        PlanningBarrier.validate_single_expansion_slot(gs)

    def test_validate_single_expansion_slot_allows_committed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp1 = _minimal_expansion("EXP-1", "committed")
        exp2 = _minimal_expansion("EXP-2", "committed")
        add_expansion(gs, exp1)
        add_expansion(gs, exp2)
        PlanningBarrier.validate_single_expansion_slot(gs)


# ===========================================================================
# Task 7.2 Tests: Next operation selection
# ===========================================================================


class NextOperationSelectorTest(unittest.TestCase):
    """Test NextOperationSelector class."""

    def test_select_next_operation_returns_commit_expansion_when_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        result = NextOperationSelector.select_next_operation(gs)
        self.assertEqual(result, "commit_expansion")

    def test_select_next_operation_returns_schedule_jobs_when_open(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        result = NextOperationSelector.select_next_operation(gs)
        self.assertEqual(result, "schedule_jobs")

    def test_select_next_operation_returns_terminal_when_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        result = NextOperationSelector.select_next_operation(gs)
        self.assertEqual(result, "terminal")

    def test_select_next_operation_returns_none_for_other(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        result = NextOperationSelector.select_next_operation(gs)
        self.assertEqual(result, "none")

    def test_validate_expansion_priority_blocks_wrong_operation(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError) as ctx:
            NextOperationSelector.validate_expansion_priority(gs, "schedule_jobs")
        self.assertIn("expansion priority violation", str(ctx.exception))

    def test_validate_expansion_priority_allows_correct_operation(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        NextOperationSelector.validate_expansion_priority(gs, "commit_expansion")

    def test_validate_expansion_priority_allows_no_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        NextOperationSelector.validate_expansion_priority(gs, "schedule_jobs")


# ===========================================================================
# Task 7.3 Tests: Dispatch graph revision validation
# ===========================================================================


class DispatchValidatorTest(unittest.TestCase):
    """Test DispatchValidator class."""

    def test_validate_dispatch_graph_revision_passes_match(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=5)
        DispatchValidator.validate_dispatch_graph_revision(gs, 5)

    def test_validate_dispatch_graph_revision_fails_mismatch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=5)
        with self.assertRaises(OrchestratorError) as ctx:
            DispatchValidator.validate_dispatch_graph_revision(gs, 3)
        self.assertIn("revision mismatch", str(ctx.exception))

    def test_reject_stale_dispatch_passes_match(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=5)
        gs.graph_digest = compute_graph_digest(gs)
        DispatchValidator.reject_stale_dispatch(gs, 5, gs.graph_digest)

    def test_reject_stale_dispatch_fails_digest_mismatch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=5)
        gs.graph_digest = compute_graph_digest(gs)
        with self.assertRaises(OrchestratorError) as ctx:
            DispatchValidator.reject_stale_dispatch(gs, 5, "wrong_digest")
        self.assertIn("stale dispatch rejected", str(ctx.exception))

    def test_reject_stale_dispatch_fails_revision_mismatch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=5)
        gs.graph_digest = compute_graph_digest(gs)
        with self.assertRaises(OrchestratorError) as ctx:
            DispatchValidator.reject_stale_dispatch(gs, 3, gs.graph_digest)
        self.assertIn("revision mismatch", str(ctx.exception))


# ===========================================================================
# Task 7.4 Tests: Edge readiness checking
# ===========================================================================


class EdgeReadinessCheckerTest(unittest.TestCase):
    """Test EdgeReadinessChecker class."""

    def test_check_edge_readiness_unknown_type(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        edge = _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2", "success")
        edge["edge_type"] = "unknown"
        gs._edges["EDGE-1"] = edge
        with self.assertRaises(OrchestratorError) as ctx:
            EdgeReadinessChecker.check_edge_readiness(gs, "EDGE-1")
        self.assertIn("unknown edge type", str(ctx.exception))

    def test_check_edge_readiness_missing_edge(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        with self.assertRaises(OrchestratorError) as ctx:
            EdgeReadinessChecker.check_edge_readiness(gs, "EDGE-MISSING")
        self.assertIn("not found", str(ctx.exception))

    def test_check_success_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["completion_status"] = "success"
        self.assertTrue(EdgeReadinessChecker.check_success_edge(gs, "JOB-1"))

    def test_check_success_edge_not_ready_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        self.assertFalse(EdgeReadinessChecker.check_success_edge(gs, "JOB-1"))

    def test_check_success_edge_not_ready_failed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["completion_status"] = "failed"
        self.assertFalse(EdgeReadinessChecker.check_success_edge(gs, "JOB-1"))

    def test_check_execution_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["execution_status"] = "success"
        self.assertTrue(EdgeReadinessChecker.check_execution_edge(gs, "JOB-1"))

    def test_check_execution_edge_not_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        self.assertFalse(EdgeReadinessChecker.check_execution_edge(gs, "JOB-1"))

    def test_check_all_settled_edge_ready_no_batch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        self.assertTrue(EdgeReadinessChecker.check_all_settled_edge(gs, "JOB-1"))

    def test_check_all_settled_edge_ready_batch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "complete", ["JOB-1", "JOB-2"])
        add_batch(gs, batch)
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["batch_id"] = "BATCH-1"
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        gs._jobs["JOB-2"]["status"] = "failed"
        gs._jobs["JOB-2"]["batch_id"] = "BATCH-1"
        self.assertTrue(EdgeReadinessChecker.check_all_settled_edge(gs, "JOB-1"))

    def test_check_all_settled_edge_not_ready_batch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open", ["JOB-1", "JOB-2"])
        add_batch(gs, batch)
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["batch_id"] = "BATCH-1"
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        gs._jobs["JOB-2"]["status"] = "running"
        gs._jobs["JOB-2"]["batch_id"] = "BATCH-1"
        self.assertFalse(EdgeReadinessChecker.check_all_settled_edge(gs, "JOB-1"))

    def test_check_report_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["report_accepted"] = True
        self.assertTrue(EdgeReadinessChecker.check_report_edge(gs, "JOB-1"))

    def test_check_report_edge_not_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        self.assertFalse(EdgeReadinessChecker.check_report_edge(gs, "JOB-1"))

    def test_check_verification_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["verification_passed"] = True
        self.assertTrue(EdgeReadinessChecker.check_verification_edge(gs, "JOB-1"))

    def test_check_verification_edge_not_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        self.assertFalse(EdgeReadinessChecker.check_verification_edge(gs, "JOB-1"))

    def test_check_batch_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "complete", ["JOB-1"])
        add_batch(gs, batch)
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["batch_id"] = "BATCH-1"
        self.assertTrue(EdgeReadinessChecker.check_batch_edge(gs, "JOB-1"))

    def test_check_batch_edge_not_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open", ["JOB-1"])
        add_batch(gs, batch)
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["batch_id"] = "BATCH-1"
        self.assertFalse(EdgeReadinessChecker.check_batch_edge(gs, "JOB-1"))

    def test_check_cycle_edge_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        gs._jobs["JOB-1"]["cycle_id"] = "CYC-1"
        self.assertTrue(EdgeReadinessChecker.check_cycle_edge(gs, "JOB-1"))

    def test_check_cycle_edge_not_ready(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "completed"
        self.assertFalse(EdgeReadinessChecker.check_cycle_edge(gs, "JOB-1"))

    def test_check_edge_readiness_integration(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2", "success"))
        job = _minimal_job_def("JOB-1")
        job["status"] = "completed"
        job["completion_status"] = "success"
        gs._jobs["JOB-1"] = job
        self.assertTrue(EdgeReadinessChecker.check_edge_readiness(gs, "EDGE-1"))


# ===========================================================================
# Task 7.5 Tests: Batch membership and barriers
# ===========================================================================


class BatchBarrierTest(unittest.TestCase):
    """Test BatchBarrier class."""

    def test_validate_batch_membership_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open", ["JOB-1", "JOB-2"])
        add_batch(gs, batch)
        BatchBarrier.validate_batch_membership(gs, "BATCH-1", "JOB-1")

    def test_validate_batch_membership_fails_not_member(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open", ["JOB-1"])
        add_batch(gs, batch)
        with self.assertRaises(OrchestratorError) as ctx:
            BatchBarrier.validate_batch_membership(gs, "BATCH-1", "JOB-2")
        self.assertIn("not a member", str(ctx.exception))

    def test_validate_batch_membership_fails_batch_not_found(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        with self.assertRaises(OrchestratorError) as ctx:
            BatchBarrier.validate_batch_membership(gs, "BATCH-MISSING", "JOB-1")
        self.assertIn("not found", str(ctx.exception))

    def test_validate_batch_sealing_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "sealed")
        add_batch(gs, batch)
        BatchBarrier.validate_batch_sealing(gs, "BATCH-1")

    def test_validate_batch_sealing_fails_open(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open")
        add_batch(gs, batch)
        with self.assertRaises(OrchestratorError) as ctx:
            BatchBarrier.validate_batch_sealing(gs, "BATCH-1")
        self.assertIn("must be sealed", str(ctx.exception))

    def test_validate_openspec_expansion_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open")
        add_batch(gs, batch)
        exp = {
            "expansion_id": "EXP-1",
            "batch_id": "BATCH-1",
            "type": "openspec",
            "status": "committed",
            "created_at": _valid_datetime(),
        }
        add_expansion(gs, exp)
        BatchBarrier.validate_openspec_expansion(gs, "BATCH-1")

    def test_validate_openspec_expansion_fails_missing(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open")
        add_batch(gs, batch)
        with self.assertRaises(OrchestratorError) as ctx:
            BatchBarrier.validate_openspec_expansion(gs, "BATCH-1")
        self.assertIn("requires nested OpenSpec expansion", str(ctx.exception))

    def test_validate_openspec_expansion_fails_wrong_type(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        batch = _minimal_batch("BATCH-1", "open")
        add_batch(gs, batch)
        exp = {
            "expansion_id": "EXP-1",
            "batch_id": "BATCH-1",
            "type": "other",
            "status": "committed",
            "created_at": _valid_datetime(),
        }
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError):
            BatchBarrier.validate_openspec_expansion(gs, "BATCH-1")


# ===========================================================================
# Task 7.6 Tests: Goal expansion handler
# ===========================================================================


class GoalExpansionHandlerTest(unittest.TestCase):
    """Test GoalExpansionHandler class."""

    def test_commit_continuation_expansion_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        GoalExpansionHandler.commit_continuation_expansion(gs, "EXP-1", "CONTINUE")
        self.assertEqual(gs._expansions["EXP-1"]["status"], "committed")

    def test_commit_continuation_expansion_fails_wrong_decision(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError) as ctx:
            GoalExpansionHandler.commit_continuation_expansion(gs, "EXP-1", "GOAL_ACHIEVED")
        self.assertIn("requires CONTINUE decision", str(ctx.exception))

    def test_commit_continuation_expansion_fails_not_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        exp = _minimal_expansion("EXP-1", "committed")
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError) as ctx:
            GoalExpansionHandler.commit_continuation_expansion(gs, "EXP-1", "CONTINUE")
        self.assertIn("must be pending", str(ctx.exception))

    def test_seal_on_goal_achieved_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        GoalExpansionHandler.seal_on_goal_achieved(gs, "GOAL_ACHIEVED")
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_seal_on_goal_achieved_fails_wrong_decision(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        with self.assertRaises(OrchestratorError) as ctx:
            GoalExpansionHandler.seal_on_goal_achieved(gs, "CONTINUE")
        self.assertIn("requires GOAL_ACHIEVED decision", str(ctx.exception))

    def test_seal_on_goal_achieved_fails_not_open(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        with self.assertRaises(OrchestratorError) as ctx:
            GoalExpansionHandler.seal_on_goal_achieved(gs, "GOAL_ACHIEVED")
        self.assertIn("must be open", str(ctx.exception))

    def test_seal_on_goal_achieved_fails_pending_expansions(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError) as ctx:
            GoalExpansionHandler.seal_on_goal_achieved(gs, "GOAL_ACHIEVED")
        self.assertIn("pending expansions", str(ctx.exception))


# ===========================================================================
# Task 7.7 Tests: Terminality checking
# ===========================================================================


class TerminalityCheckerTest(unittest.TestCase):
    """Test TerminalityChecker class."""

    def test_check_graph_sealed_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        TerminalityChecker.check_graph_sealed(gs)

    def test_check_graph_sealed_fails_open(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalityChecker.check_graph_sealed(gs)
        self.assertIn("must be sealed", str(ctx.exception))

    def test_check_obligations_passes_empty(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        TerminalityChecker.check_obligations(gs)

    def test_check_obligations_fails_pending_expansion(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        exp = _minimal_expansion("EXP-1", "pending")
        add_expansion(gs, exp)
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalityChecker.check_obligations(gs)
        self.assertIn("EXP-1", str(ctx.exception))

    def test_check_obligations_fails_pending_job(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        gs._jobs["JOB-1"]["status"] = "running"
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalityChecker.check_obligations(gs)
        self.assertIn("JOB-1", str(ctx.exception))

    def test_check_final_audit_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = compute_graph_digest(gs)
        TerminalityChecker.check_final_audit(gs)

    def test_check_final_audit_fails_missing_digest(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = ""
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalityChecker.check_final_audit(gs)
        self.assertIn("missing graph digest", str(ctx.exception))

    def test_check_final_audit_fails_digest_mismatch(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = "wrong_digest"
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalityChecker.check_final_audit(gs)
        self.assertIn("digest mismatch", str(ctx.exception))


# ===========================================================================
# Task 7.8 Tests: Terminal outcome recording
# ===========================================================================


class TerminalOutcomeRecorderTest(unittest.TestCase):
    """Test TerminalOutcomeRecorder class."""

    def test_validate_terminal_outcome_passes(self) -> None:
        for outcome in TerminalOutcomeRecorder.VALID_OUTCOMES:
            TerminalOutcomeRecorder.validate_terminal_outcome(outcome)

    def test_validate_terminal_outcome_fails_invalid(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalOutcomeRecorder.validate_terminal_outcome("invalid")
        self.assertIn("invalid terminal outcome type", str(ctx.exception))

    def test_record_terminal_outcome_passes(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = compute_graph_digest(gs)
        result = TerminalOutcomeRecorder.record_terminal_outcome(
            gs, "successful", goal_judge_decision="GOAL_ACHIEVED"
        )
        self.assertEqual(result["outcome_type"], "successful")
        self.assertEqual(result["goal_judge_decision"], "GOAL_ACHIEVED")
        self.assertEqual(len(gs._terminal_outcomes), 1)

    def test_record_terminal_outcome_fails_not_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        gs.graph_digest = compute_graph_digest(gs)
        with self.assertRaises(OrchestratorError) as ctx:
            TerminalOutcomeRecorder.record_terminal_outcome(gs, "successful")
        self.assertIn("must be sealed", str(ctx.exception))

    def test_record_terminal_outcome_fails_invalid_type(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = compute_graph_digest(gs)
        with self.assertRaises(OrchestratorError):
            TerminalOutcomeRecorder.record_terminal_outcome(gs, "invalid")

    def test_record_terminal_outcome_records_all_types(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = compute_graph_digest(gs)
        for outcome in TerminalOutcomeRecorder.VALID_OUTCOMES:
            TerminalOutcomeRecorder.record_terminal_outcome(gs, outcome)
            gs.graph_digest = compute_graph_digest(gs)
        self.assertEqual(len(gs._terminal_outcomes), len(TerminalOutcomeRecorder.VALID_OUTCOMES))

    def test_terminal_outcome_persists_in_graph(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        gs.graph_digest = compute_graph_digest(gs)
        TerminalOutcomeRecorder.record_terminal_outcome(gs, "successful")
        gs_dict = gs.to_dict()
        self.assertIn("terminal_outcomes", gs_dict)
        self.assertEqual(len(gs_dict["terminal_outcomes"]), 1)


if __name__ == "__main__":
    unittest.main()
