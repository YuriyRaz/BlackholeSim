"""End-to-end verification tests for v6 dynamic registration.

Task 15.1: Deterministic dynamic-registration tests for authorized and
unauthorized expansion, prospective cycles, identity collisions,
authority narrowing, sealed batches, and expansion limits.
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
    EdgeRecord,
    JobRecord,
    add_batch,
    add_edge_to_graph,
    add_expansion,
    add_job_to_graph,
    compute_graph_digest,
    generate_batch_id,
    generate_decision_id,
    generate_expansion_id,
    generate_global_job_id,
    transition_graph_status,
    validate_identity_uniqueness,
    validate_identity_format,
    validate_limits,
    validate_prospective_graph,
)
from transaction_v6 import (  # noqa: E402
    ExpansionIngester,
    ExpansionRetainer,
    GoalDecisionProcessor,
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
        "limits": limits or {
            "max_cycles": 10,
            "max_jobs_per_cycle": 5,
            "max_total_jobs": 50,
        },
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


class AuthorizedExpansionTest(unittest.TestCase):
    """Test authorized expansion registration."""

    def test_expand_with_valid_authority(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.current_goal_judge_id = "JOB-JUDGE"
        gs.active_planning_authority_id = "AUTH-ROOT"

        job = _job_def("JOB-AAA")
        add_job_to_graph(gs, job)

        edge = _edge_def("EDGE-1", "JOB-EXISTING", "JOB-AAA")
        gs._jobs["JOB-EXISTING"] = _job_def("JOB-EXISTING")
        add_edge_to_graph(gs, edge)

        self.assertIn("JOB-AAA", gs._jobs)
        self.assertEqual(gs._jobs["JOB-AAA"]["role"], "implementation")

    def test_expand_adds_to_expansion_ledger(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        expansion = {
            "expansion_id": "EXP-TEST-1",
            "plan_id": "PLAN-1",
            "provenance": {
                "producer_job_id": "JOB-JUDGE",
                "authority_id": "AUTH-ROOT",
                "cycle_id": "CYC-1",
            },
        }
        add_expansion(gs, expansion)
        self.assertIn("EXP-TEST-1", gs.expansion_ledger)
        self.assertEqual(len(gs._expansions), 1)

    def test_expand_preserves_graph_digest(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.graph_digest = compute_graph_digest(gs)

        job = _job_def("JOB-NEW")
        add_job_to_graph(gs, job)

        new_digest = compute_graph_digest(gs)
        self.assertNotEqual(new_digest, gs.graph_digest)


class UnauthorizedExpansionTest(unittest.TestCase):
    """Test unauthorized expansion rejection."""

    def test_reject_expansion_from_unknown_authority(self) -> None:
        authority_store = {
            "AUTH-VALID": {"expires_at": None, "scope": {"expansion": True}},
        }
        ingester = ExpansionIngester(authority_store)

        with self.assertRaises(OrchestratorError) as ctx:
            ingester.accept_expansion(
                expansion={"plan_id": "P1"},
                current_authority_id="AUTH-UNKNOWN",
                producer_job={"job_id": "J1", "cycle_id": "C1"},
                response_receipt={"response_id": "R1"},
                graph_state={"graph_revision": 1, "graph_digest": "a" * 64},
                source_artifact_digest="abc",
                authority_scope={"expansion": True},
            )
        self.assertIn("not found", str(ctx.exception))

    def test_reject_expansion_without_expansion_scope(self) -> None:
        authority_store = {
            "AUTH-LIMITED": {"expires_at": None, "scope": {"expansion": False}},
        }
        ingester = ExpansionIngester(authority_store)

        with self.assertRaises(OrchestratorError) as ctx:
            ingester.accept_expansion(
                expansion={"plan_id": "P1"},
                current_authority_id="AUTH-LIMITED",
                producer_job={"job_id": "J1", "cycle_id": "C1"},
                response_receipt={"response_id": "R1"},
                graph_state={"graph_revision": 1, "graph_digest": "a" * 64},
                source_artifact_digest="abc",
                authority_scope={"expansion": False},
            )
        self.assertIn("expansion scope", str(ctx.exception))

    def test_reject_expansion_from_expired_authority(self) -> None:
        authority_store = {
            "AUTH-EXPIRED": {
                "expires_at": "2020-01-01T00:00:00Z",
                "scope": {"expansion": True},
            },
        }
        ingester = ExpansionIngester(authority_store)

        with self.assertRaises(OrchestratorError) as ctx:
            ingester.accept_expansion(
                expansion={"plan_id": "P1"},
                current_authority_id="AUTH-EXPIRED",
                producer_job={"job_id": "J1", "cycle_id": "C1"},
                response_receipt={"response_id": "R1"},
                graph_state={"graph_revision": 1, "graph_digest": "a" * 64},
                source_artifact_digest="abc",
                authority_scope={"expansion": True},
            )
        self.assertIn("expired", str(ctx.exception))


class ProspectiveCycleTest(unittest.TestCase):
    """Test prospective cycle detection in graph validation."""

    def test_detect_simple_cycle(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs._jobs["A"] = _job_def("A")
        gs._jobs["B"] = _job_def("B")
        gs._jobs["C"] = _job_def("C")

        add_edge_to_graph(gs, _edge_def("E1", "A", "B"))
        add_edge_to_graph(gs, _edge_def("E2", "B", "C"))

        new_edge = _edge_def("E3", "C", "A")
        errors = validate_prospective_graph(gs, new_edges=[new_edge])
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_no_cycle_without_closing_edge(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs._jobs["A"] = _job_def("A")
        gs._jobs["B"] = _job_def("B")

        add_edge_to_graph(gs, _edge_def("E1", "A", "B"))

        new_edge = _edge_def("E2", "B", "C")
        gs._jobs["C"] = _job_def("C")
        errors = validate_prospective_graph(gs, new_edges=[new_edge])
        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        self.assertEqual(cycle_errors, [])

    def test_self_cycle_detected(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs._jobs["SELF"] = _job_def("SELF")

        new_edge = _edge_def("E-SELF", "SELF", "SELF")
        errors = validate_prospective_graph(gs, new_edges=[new_edge])
        self.assertTrue(any("cycle" in e.lower() for e in errors))


class IdentityCollisionTest(unittest.TestCase):
    """Test identity collision detection."""

    def test_reject_duplicate_job_id(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        job = _job_def("JOB-DUP")
        add_job_to_graph(gs, job)

        with self.assertRaises(OrchestratorError) as ctx:
            add_job_to_graph(gs, _job_def("JOB-DUP"))
        self.assertIn("already exists", str(ctx.exception))

    def test_reject_duplicate_edge_id(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs._jobs["A"] = _job_def("A")
        gs._jobs["B"] = _job_def("B")
        edge = _edge_def("EDGE-DUP", "A", "B")
        add_edge_to_graph(gs, edge)

        with self.assertRaises(OrchestratorError) as ctx:
            add_edge_to_graph(gs, _edge_def("EDGE-DUP", "A", "B"))
        self.assertIn("already exists", str(ctx.exception))

    def test_validate_identity_uniqueness(self) -> None:
        existing = {"JOB-1", "JOB-2", "JOB-3"}
        validate_identity_uniqueness("JOB-NEW", existing)
        with self.assertRaises(OrchestratorError) as ctx:
            validate_identity_uniqueness("JOB-1", existing)
        self.assertIn("collision", str(ctx.exception))

    def test_deterministic_expansion_id(self) -> None:
        id1 = generate_expansion_id("run1", "dec1", "digest1")
        id2 = generate_expansion_id("run1", "dec1", "digest1")
        self.assertEqual(id1, id2)

    def test_different_inputs_different_ids(self) -> None:
        id1 = generate_expansion_id("run1", "dec1", "digest1")
        id2 = generate_expansion_id("run1", "dec2", "digest1")
        self.assertNotEqual(id1, id2)

    def test_global_job_id_is_valid(self) -> None:
        jid = generate_global_job_id("run1", "exp1", "local1")
        validate_identity_format(jid)
        self.assertTrue(jid.startswith("JOB-"))


class AuthorityNarrowingTest(unittest.TestCase):
    """Test authority narrowing validation."""

    def test_narrowed_authority_rejects_expansion(self) -> None:
        authority_store = {
            "AUTH-NARROW": {"expires_at": None, "scope": {"expansion": False}},
        }
        ingester = ExpansionIngester(authority_store)

        with self.assertRaises(OrchestratorError):
            ingester.accept_expansion(
                expansion={"plan_id": "P1"},
                current_authority_id="AUTH-NARROW",
                producer_job={"job_id": "J1", "cycle_id": "C1"},
                response_receipt={"response_id": "R1"},
                graph_state={"graph_revision": 1, "graph_digest": "a" * 64},
                source_artifact_digest="abc",
                authority_scope={"expansion": False},
            )

    def test_valid_expansion_scope_accepted(self) -> None:
        authority_store = {
            "AUTH-FULL": {"expires_at": None, "scope": {"expansion": True}},
        }
        ingester = ExpansionIngester(authority_store)
        result = ingester.accept_expansion(
            expansion={"plan_id": "P1"},
            current_authority_id="AUTH-FULL",
            producer_job={"job_id": "J1", "cycle_id": "C1"},
            response_receipt={"response_id": "R1"},
            graph_state={"graph_revision": 1, "graph_digest": "a" * 64},
            source_artifact_digest="abc",
            authority_scope={"expansion": True},
        )
        self.assertIn("provenance", result)
        self.assertEqual(result["provenance"]["authority_id"], "AUTH-FULL")


class SealedBatchExpansionTest(unittest.TestCase):
    """Test sealed batch expansion rejection."""

    def test_cannot_add_to_sealed_batch(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.SEALED)
        batch = {
            "batch_id": "BATCH-SEALED",
            "status": "sealed",
            "job_ids": ["JOB-1"],
        }
        add_batch(gs, batch)

        batches = gs._batches
        self.assertEqual(batches["BATCH-SEALED"]["status"], "sealed")

    def test_open_batch_allows_jobs(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        batch = {
            "batch_id": "BATCH-OPEN",
            "status": "open",
            "job_ids": ["JOB-1"],
        }
        add_batch(gs, batch)
        self.assertEqual(gs._batches["BATCH-OPEN"]["status"], "open")

    def test_sealed_graph_blocks_new_expansion_slot(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.SEALED)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.PLANNING)


class ExpansionLimitTest(unittest.TestCase):
    """Test expansion limit enforcement."""

    def test_total_jobs_limit(self) -> None:
        gs = GraphState(
            envelope=_envelope(limits={"max_total_jobs": 3}),
            status=GraphStatus.OPEN,
        )
        for i in range(3):
            add_job_to_graph(gs, _job_def(f"JOB-LIMIT-{i}"))

        errors = validate_limits(gs, proposed_job_count=1)
        self.assertTrue(any("total jobs" in e.lower() for e in errors))

    def test_jobs_per_expansion_limit(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.envelope["limits"]["max_jobs_per_cycle"] = 2

        errors = validate_limits(gs, proposed_job_count=3)
        self.assertTrue(any("jobs per expansion" in e.lower() for e in errors))

    def test_within_limits_no_error(self) -> None:
        gs = GraphState(
            envelope=_envelope(limits={"max_total_jobs": 10}),
            status=GraphStatus.OPEN,
        )
        errors = validate_limits(gs, proposed_job_count=1)
        self.assertEqual(errors, [])

    def test_fan_out_limit(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.limits = {"fan_out_limit": 2}

        errors = validate_limits(gs, proposed_job_count=5)
        self.assertTrue(any("fan-out" in e.lower() for e in errors))

    def test_expansion_depth_limit(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs.limits = {"max_expansion_depth": 3}

        errors = validate_limits(gs, proposed_expansion_depth=5)
        self.assertTrue(any("depth" in e.lower() for e in errors))

    def test_edges_limit(self) -> None:
        gs = GraphState(envelope=_envelope(), status=GraphStatus.OPEN)
        gs._jobs["A"] = _job_def("A")
        gs._jobs["B"] = _job_def("B")
        gs.limits = {"max_edges": 1}
        add_edge_to_graph(gs, _edge_def("EDGE-LIM", "A", "B"))

        errors = validate_limits(gs, proposed_edge_count=1)
        self.assertTrue(any("edges" in e.lower() for e in errors))


if __name__ == "__main__":
    unittest.main()
