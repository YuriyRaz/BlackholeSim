"""Tests for the v6 append-only graph model."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, SCHEMA_VERSION, canonical_bytes, stable_id  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    JobRecord,
    EdgeRecord,
    VerifierRecord,
    RepairGateRecord,
    add_job_to_graph,
    add_edge_to_graph,
    add_verifier_assignment,
    add_repair_gate,
    add_expansion,
    add_generation,
    add_batch,
    get_job,
    get_jobs,
    get_edges,
    get_edges_from,
    get_edges_to,
    get_batches,
    get_verifier_assignments_for_target,
    get_repair_gate_history_for_target,
    compute_graph_digest,
    generate_expansion_id,
    generate_batch_id,
    generate_decision_id,
    generate_global_job_id,
    validate_identity_format,
    validate_identity_uniqueness,
    validate_prospective_graph,
    validate_limits,
    transition_graph_status,
    advance_graph_revision,
)


def _valid_id() -> str:
    return "T-ABCDEFGHIJKLMOPQRST"


def _valid_digest() -> str:
    return "a" * 64


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


def _minimal_verifier_assignment(
    assignment_id: str = "VASS-AAAAAAAAAAAAAAAAAAAA",
    target_job_id: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    verifier_job_id: str = "JOB-CCCCCCCCCCCCCCCCCCCC",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "assignment_id": assignment_id,
        "target_job_id": target_job_id,
        "target_gate_revision": 1,
        "verifier_job_id": verifier_job_id,
        "run_id": "2026-01-15T103000Z-test",
        "cycle_id": _valid_id(),
        "status": "assigned",
        "evidence_refs": [],
        "assigned_at": _valid_datetime(),
    }


def _minimal_repair_gate(
    history_id: str = "RGH-AAAAAAAAAAAAAAAAAAAA",
    target_job_id: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    repair_job_id: str = "JOB-DDDDDDDDDDDDDDDDDDDD",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "history_id": history_id,
        "target_job_id": target_job_id,
        "revision": 1,
        "repair_job_id": repair_job_id,
        "finding_id": _valid_id(),
        "status": "applied",
        "evidence_refs": [],
        "recorded_at": _valid_datetime(),
    }


# ===========================================================================
# Task 3.1 Tests: Graph state persistence
# ===========================================================================

class GraphStatePersistenceTest(unittest.TestCase):
    """Test GraphState creation, serialization, and round-trip."""

    def test_create_graph_state(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        self.assertEqual(gs.graph_revision, 1)
        self.assertEqual(gs.status, GraphStatus.PLANNING)
        self.assertEqual(gs.envelope["goal"], "implement feature")

    def test_to_dict_contains_all_fields(self) -> None:
        gs = GraphState(
            envelope=_minimal_envelope(),
            current_goal_judge_id="JUDGE-123",
            active_planning_authority_id="AUTH-456",
        )
        d = gs.to_dict()
        self.assertEqual(d["schema_version"], SCHEMA_VERSION)
        self.assertIn("envelope", d)
        self.assertIn("jobs", d)
        self.assertIn("edges", d)
        self.assertIn("batches", d)
        self.assertIn("verifier_assignments", d)
        self.assertIn("repair_gate_history", d)
        self.assertEqual(d["current_goal_judge_id"], "JUDGE-123")
        self.assertEqual(d["active_planning_authority_id"], "AUTH-456")

    def test_from_dict_round_trip(self) -> None:
        gs = GraphState(
            envelope=_minimal_envelope(),
            graph_revision=5,
            graph_digest="b" * 64,
            status=GraphStatus.OPEN,
            current_goal_judge_id="JUDGE-123",
        )
        gs._jobs["JOB-1"] = _minimal_job_def("JOB-1")
        gs._edges["EDGE-1"] = _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2")
        gs.expansion_ledger.append("EXP-1")

        d = gs.to_dict()
        gs2 = GraphState.from_dict(d)

        self.assertEqual(gs2.graph_revision, 5)
        self.assertEqual(gs2.graph_digest, "b" * 64)
        self.assertEqual(gs2.status, GraphStatus.OPEN)
        self.assertEqual(gs2.current_goal_judge_id, "JUDGE-123")
        self.assertIn("JOB-1", gs2._jobs)
        self.assertIn("EDGE-1", gs2._edges)
        self.assertEqual(gs2.expansion_ledger, ["EXP-1"])

    def test_save_and_load_round_trip(self) -> None:
        gs = GraphState(
            envelope=_minimal_envelope(),
            graph_revision=3,
            status=GraphStatus.OPEN,
        )
        gs._jobs["JOB-1"] = _minimal_job_def("JOB-1")

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "graph_state.json"
            gs.save(path)
            loaded = GraphState.load(path)

            self.assertEqual(loaded.graph_revision, 3)
            self.assertEqual(loaded.status, GraphStatus.OPEN)
            self.assertIn("JOB-1", loaded._jobs)

    def test_graph_status_enum_values(self) -> None:
        expected = {
            "planning", "pending", "committing", "open",
            "sealed", "canceling", "recovery_required",
        }
        actual = {s.value for s in GraphStatus}
        self.assertEqual(actual, expected)


# ===========================================================================
# Task 3.2 Tests: Job and edge management
# ===========================================================================

class JobRecordTest(unittest.TestCase):
    """Test JobRecord creation and serialization."""

    def test_create_job_record(self) -> None:
        jr = JobRecord(
            job_id="JOB-TEST",
            role="implementation",
            purpose_key="impl-main",
            graph_generation=1,
            expansion_origin="ROOT",
            authority_id="AUTH-1",
            context_snapshot_id="CTX-1",
        )
        self.assertEqual(jr.job_id, "JOB-TEST")
        self.assertEqual(jr.role, "implementation")
        self.assertEqual(jr.status, "pending")

    def test_job_record_to_dict(self) -> None:
        jr = JobRecord(
            job_id="JOB-TEST",
            role="verifier",
            purpose_key="verify-main",
            graph_generation=2,
            expansion_origin="JOB-PARENT",
            authority_id="AUTH-1",
            context_snapshot_id="CTX-1",
            repair_relationship={"target_job_id": "JOB-T", "finding_id": "FIND-1"},
        )
        d = jr.to_dict()
        self.assertEqual(d["schema_version"], SCHEMA_VERSION)
        self.assertEqual(d["role"], "verifier")
        self.assertEqual(d["repair_relationship"]["target_job_id"], "JOB-T")

    def test_job_record_from_dict(self) -> None:
        d = _minimal_job_def()
        jr = JobRecord.from_dict(d)
        self.assertEqual(jr.job_id, d["job_id"])
        self.assertEqual(jr.role, d["role"])


class EdgeRecordTest(unittest.TestCase):
    """Test EdgeRecord creation and type validation."""

    def test_create_valid_edge(self) -> None:
        for et in ["success", "execution", "all-settled", "report", "verification", "batch", "cycle"]:
            er = EdgeRecord(
                edge_id=f"EDGE-{et.upper()}",
                source_job_id="JOB-A",
                target_job_id="JOB-B",
                edge_type=et,
                graph_revision=1,
            )
            self.assertEqual(er.edge_type, et)

    def test_rejects_invalid_edge_type(self) -> None:
        with self.assertRaises(OrchestratorError):
            EdgeRecord(
                edge_id="EDGE-BAD",
                source_job_id="JOB-A",
                target_job_id="JOB-B",
                edge_type="invalid",
                graph_revision=1,
            )

    def test_edge_to_dict(self) -> None:
        er = EdgeRecord(
            edge_id="EDGE-1",
            source_job_id="JOB-A",
            target_job_id="JOB-B",
            edge_type="success",
            graph_revision=1,
            metadata={"key": "value"},
        )
        d = er.to_dict()
        self.assertEqual(d["edge_type"], "success")
        self.assertEqual(d["metadata"], {"key": "value"})


class VerifierRecordTest(unittest.TestCase):
    """Test VerifierRecord creation."""

    def test_create_verifier_record(self) -> None:
        vr = VerifierRecord(
            assignment_id="VASS-1",
            target_job_id="JOB-T",
            target_gate_revision=1,
            verifier_job_id="JOB-V",
            run_id="run-123",
            cycle_id="CYC-1",
        )
        self.assertEqual(vr.status, "assigned")
        self.assertIsNone(vr.completed_at)

    def test_verifier_to_dict(self) -> None:
        vr = VerifierRecord(
            assignment_id="VASS-1",
            target_job_id="JOB-T",
            target_gate_revision=2,
            verifier_job_id="JOB-V",
            run_id="run-123",
            cycle_id="CYC-1",
            evidence_refs=["run://test/jobs/123"],
        )
        d = vr.to_dict()
        self.assertEqual(d["target_gate_revision"], 2)
        self.assertEqual(d["evidence_refs"], ["run://test/jobs/123"])


class RepairGateRecordTest(unittest.TestCase):
    """Test RepairGateRecord creation."""

    def test_create_repair_gate_record(self) -> None:
        rgr = RepairGateRecord(
            history_id="RGH-1",
            target_job_id="JOB-T",
            revision=1,
            repair_job_id="JOB-R",
            finding_id="FIND-1",
            status="applied",
        )
        self.assertEqual(rgr.status, "applied")

    def test_repair_gate_to_dict(self) -> None:
        rgr = RepairGateRecord(
            history_id="RGH-1",
            target_job_id="JOB-T",
            revision=1,
            repair_job_id="JOB-R",
            finding_id="FIND-1",
            status="superseded",
            evidence_refs=["run://test/graph/1"],
        )
        d = rgr.to_dict()
        self.assertEqual(d["schema_version"], SCHEMA_VERSION)
        self.assertEqual(d["status"], "superseded")


class GraphManagementTest(unittest.TestCase):
    """Test adding/querying jobs, edges, verifier assignments to GraphState."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())

    def test_add_job(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        self.assertIn("JOB-1", self.gs._jobs)
        self.assertEqual(self.gs._jobs["JOB-1"]["role"], "implementation")

    def test_add_job_rejects_duplicate(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        with self.assertRaises(OrchestratorError):
            add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))

    def test_add_edge(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        self.assertIn("EDGE-1", self.gs._edges)

    def test_add_edge_rejects_duplicate(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        with self.assertRaises(OrchestratorError):
            add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))

    def test_add_verifier_assignment(self) -> None:
        add_verifier_assignment(self.gs, _minimal_verifier_assignment())
        self.assertIn("VASS-AAAAAAAAAAAAAAAAAAAA", self.gs._verifier_assignments)

    def test_add_verifier_rejects_duplicate(self) -> None:
        add_verifier_assignment(self.gs, _minimal_verifier_assignment())
        with self.assertRaises(OrchestratorError):
            add_verifier_assignment(self.gs, _minimal_verifier_assignment())

    def test_add_repair_gate(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate())
        self.assertEqual(len(self.gs._repair_gate_history), 1)

    def test_add_repair_gate_rejects_duplicate(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate())
        with self.assertRaises(OrchestratorError):
            add_repair_gate(self.gs, _minimal_repair_gate())

    def test_add_batch(self) -> None:
        batch = {
            "schema_version": SCHEMA_VERSION,
            "batch_id": "BATCH-1",
            "campaign_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "open",
            "job_ids": ["JOB-1"],
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        }
        add_batch(self.gs, batch)
        self.assertIn("BATCH-1", self.gs._batches)

    def test_add_expansion(self) -> None:
        exp = {
            "expansion_id": "EXP-1",
            "plan_id": "PLAN-1",
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": ["JOB-1"],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
            "created_at": _valid_datetime(),
        }
        add_expansion(self.gs, exp)
        self.assertIn("EXP-1", self.gs._expansions)
        self.assertIn("EXP-1", self.gs.expansion_ledger)

    def test_get_job(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        self.assertIsNotNone(get_job(self.gs, "JOB-1"))
        self.assertIsNone(get_job(self.gs, "JOB-MISSING"))

    def test_get_jobs(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        jobs = get_jobs(self.gs)
        self.assertEqual(len(jobs), 2)

    def test_get_edges(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        edges = get_edges(self.gs)
        self.assertEqual(len(edges), 1)

    def test_get_edges_from(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-3"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-2", "JOB-1", "JOB-3"))
        from_job1 = get_edges_from(self.gs, "JOB-1")
        self.assertEqual(len(from_job1), 2)
        from_job2 = get_edges_from(self.gs, "JOB-2")
        self.assertEqual(len(from_job2), 0)

    def test_get_edges_to(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        to_job2 = get_edges_to(self.gs, "JOB-2")
        self.assertEqual(len(to_job2), 1)

    def test_get_verifier_assignments_for_target(self) -> None:
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(target_job_id="JOB-T"))
        results = get_verifier_assignments_for_target(self.gs, "JOB-T")
        self.assertEqual(len(results), 1)
        results_empty = get_verifier_assignments_for_target(self.gs, "JOB-X")
        self.assertEqual(len(results_empty), 0)

    def test_get_repair_gate_history_for_target(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate(target_job_id="JOB-T"))
        results = get_repair_gate_history_for_target(self.gs, "JOB-T")
        self.assertEqual(len(results), 1)
        results_empty = get_repair_gate_history_for_target(self.gs, "JOB-X")
        self.assertEqual(len(results_empty), 0)

    def test_add_job_rejects_missing_job_id(self) -> None:
        with self.assertRaises(OrchestratorError):
            add_job_to_graph(self.gs, {"schema_version": SCHEMA_VERSION})

    def test_add_edge_rejects_missing_edge_id(self) -> None:
        with self.assertRaises(OrchestratorError):
            add_edge_to_graph(self.gs, {"schema_version": SCHEMA_VERSION})


# ===========================================================================
# Task 3.3 Tests: Canonical graph digest computation
# ===========================================================================

class GraphDigestTest(unittest.TestCase):
    """Test canonical graph digest computation."""

    def test_empty_graph_digest(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        digest = compute_graph_digest(gs)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_digest_changes_with_jobs(self) -> None:
        gs1 = GraphState(envelope=_minimal_envelope())
        d1 = compute_graph_digest(gs1)

        gs2 = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs2, _minimal_job_def("JOB-1"))
        d2 = compute_graph_digest(gs2)

        self.assertNotEqual(d1, d2)

    def test_digest_changes_with_edges(self) -> None:
        gs1 = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs1, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs1, _minimal_job_def("JOB-2"))
        d1 = compute_graph_digest(gs1)

        gs2 = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs2, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs2, _minimal_job_def("JOB-2"))
        add_edge_to_graph(gs2, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        d2 = compute_graph_digest(gs2)

        self.assertNotEqual(d1, d2)

    def test_digest_excludes_volatile_state(self) -> None:
        gs1 = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs1, _minimal_job_def("JOB-1"))
        d1 = compute_graph_digest(gs1)

        gs2 = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs2, _minimal_job_def("JOB-1"))
        gs2._jobs["JOB-1"]["status"] = "running"
        gs2._jobs["JOB-1"]["activation_id"] = "ACT-1"
        d2 = compute_graph_digest(gs2)

        self.assertEqual(d1, d2)

    def test_digest_deterministic(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        d1 = compute_graph_digest(gs)
        d2 = compute_graph_digest(gs)
        self.assertEqual(d1, d2)

    def test_digest_stable_across_recomputation(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        d1 = compute_graph_digest(gs)
        d2 = compute_graph_digest(gs)
        self.assertEqual(d1, d2)

    def test_digest_changes_with_envelope(self) -> None:
        env1 = _minimal_envelope()
        env1["goal"] = "goal A"
        gs1 = GraphState(envelope=env1)

        env2 = _minimal_envelope()
        env2["goal"] = "goal B"
        gs2 = GraphState(envelope=env2)

        self.assertNotEqual(compute_graph_digest(gs1), compute_graph_digest(gs2))

    def test_digest_changes_with_verifier_assignments(self) -> None:
        gs1 = GraphState(envelope=_minimal_envelope())
        d1 = compute_graph_digest(gs1)

        gs2 = GraphState(envelope=_minimal_envelope())
        add_verifier_assignment(gs2, _minimal_verifier_assignment())
        d2 = compute_graph_digest(gs2)

        self.assertNotEqual(d1, d2)


# ===========================================================================
# Task 3.4 Tests: Identity generation and collision detection
# ===========================================================================

class IdentityGenerationTest(unittest.TestCase):
    """Test deterministic identity generation."""

    def test_generate_expansion_id_deterministic(self) -> None:
        id1 = generate_expansion_id("run-1", "DEC-1", "abc123")
        id2 = generate_expansion_id("run-1", "DEC-1", "abc123")
        self.assertEqual(id1, id2)

    def test_generate_expansion_id_varies_with_inputs(self) -> None:
        id1 = generate_expansion_id("run-1", "DEC-1", "abc123")
        id2 = generate_expansion_id("run-1", "DEC-1", "def456")
        self.assertNotEqual(id1, id2)

    def test_generate_batch_id_deterministic(self) -> None:
        id1 = generate_batch_id("EXP-1", 0)
        id2 = generate_batch_id("EXP-1", 0)
        self.assertEqual(id1, id2)

    def test_generate_batch_id_varies_with_index(self) -> None:
        id1 = generate_batch_id("EXP-1", 0)
        id2 = generate_batch_id("EXP-1", 1)
        self.assertNotEqual(id1, id2)

    def test_generate_decision_id_deterministic(self) -> None:
        id1 = generate_decision_id("JOB-1", "resp-abc")
        id2 = generate_decision_id("JOB-1", "resp-abc")
        self.assertEqual(id1, id2)

    def test_generate_decision_id_varies_with_response(self) -> None:
        id1 = generate_decision_id("JOB-1", "resp-abc")
        id2 = generate_decision_id("JOB-1", "resp-def")
        self.assertNotEqual(id1, id2)

    def test_generate_global_job_id_deterministic(self) -> None:
        id1 = generate_global_job_id("run-1", "EXP-1", "local-1")
        id2 = generate_global_job_id("run-1", "EXP-1", "local-1")
        self.assertEqual(id1, id2)

    def test_generate_global_job_id_format(self) -> None:
        gid = generate_global_job_id("run-1", "EXP-1", "local-1")
        validate_identity_format(gid)
        self.assertTrue(gid.startswith("JOB-"))

    def test_validate_identity_format_valid(self) -> None:
        validate_identity_format("JOB-ABCDEFGHIJKLM")
        validate_identity_format("T-12345")

    def test_validate_identity_format_rejects_lowercase(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_identity_format("job-abc")

    def test_validate_identity_format_rejects_empty(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_identity_format("")

    def test_validate_identity_format_rejects_starts_with_digit(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_identity_format("1JOB-ABC")

    def test_validate_identity_uniqueness(self) -> None:
        validate_identity_uniqueness("JOB-1", {"JOB-2", "JOB-3"})

    def test_validate_identity_uniqueness_collision(self) -> None:
        with self.assertRaises(OrchestratorError):
            validate_identity_uniqueness("JOB-1", {"JOB-1", "JOB-2"})

    def test_validate_identity_uniqueness_empty_set(self) -> None:
        validate_identity_uniqueness("JOB-1", set())


# ===========================================================================
# Task 3.5 Tests: Prospective graph validation
# ===========================================================================

class ProspectiveGraphValidationTest(unittest.TestCase):
    """Test prospective graph validation for dependencies, cycles, etc."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())

    def test_valid_simple_graph(self) -> None:
        errors = validate_prospective_graph(self.gs)
        self.assertEqual(errors, [])

    def test_valid_graph_with_jobs_and_edges(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        errors = validate_prospective_graph(self.gs)
        self.assertEqual(errors, [])

    def test_edge_references_nonexistent_source(self) -> None:
        errors = validate_prospective_graph(
            self.gs,
            new_edges=[_minimal_edge_def("EDGE-1", "JOB-MISSING", "JOB-2")],
        )
        self.assertTrue(any("source_job_id" in e for e in errors))

    def test_edge_references_nonexistent_target(self) -> None:
        errors = validate_prospective_graph(
            self.gs,
            new_edges=[_minimal_edge_def("EDGE-1", "JOB-1", "JOB-MISSING")],
        )
        self.assertTrue(any("target_job_id" in e for e in errors))

    def test_existing_edge_references_nonexistent_job(self) -> None:
        add_edge_to_graph.__wrapped__ = None  # bypass validation for test
        self.gs._edges["EDGE-1"] = {
            "edge_id": "EDGE-1",
            "source_job_id": "JOB-GHOST",
            "target_job_id": "JOB-2",
            "edge_type": "success",
            "graph_revision": 1,
        }
        errors = validate_prospective_graph(self.gs)
        self.assertTrue(any("JOB-GHOST" in e for e in errors))

    def test_detects_simple_cycle(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-2", "JOB-2", "JOB-1"))
        errors = validate_prospective_graph(self.gs)
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_no_cycle_with_linear_chain(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-3"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-2", "JOB-2", "JOB-3"))
        errors = validate_prospective_graph(self.gs)
        self.assertFalse(any("cycle" in e.lower() for e in errors))

    def test_new_edge_creates_cycle(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-1"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-2"))
        add_edge_to_graph(self.gs, _minimal_edge_def("EDGE-1", "JOB-1", "JOB-2"))
        errors = validate_prospective_graph(
            self.gs,
            new_edges=[_minimal_edge_def("EDGE-2", "JOB-2", "JOB-1")],
        )
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_expansion_origin_must_exist(self) -> None:
        errors = validate_prospective_graph(
            self.gs,
            new_jobs=[_minimal_job_def("JOB-1", expansion_origin="JOB-GHOST")],
        )
        self.assertTrue(any("expansion_origin" in e for e in errors))

    def test_repair_target_must_exist(self) -> None:
        job = _minimal_job_def("JOB-1")
        job["repair_relationship"] = {
            "target_job_id": "JOB-GHOST",
            "finding_id": "FIND-1",
        }
        errors = validate_prospective_graph(self.gs, new_jobs=[job])
        self.assertTrue(any("repair target" in e for e in errors))

    def test_empty_role_rejected(self) -> None:
        job = _minimal_job_def("JOB-1")
        job["role"] = ""
        errors = validate_prospective_graph(self.gs, new_jobs=[job])
        self.assertTrue(any("role is empty" in e for e in errors))

    def test_empty_purpose_key_rejected(self) -> None:
        job = _minimal_job_def("JOB-1")
        job["purpose_key"] = ""
        errors = validate_prospective_graph(self.gs, new_jobs=[job])
        self.assertTrue(any("purpose_key is empty" in e for e in errors))

    def test_batch_references_nonexistent_job(self) -> None:
        self.gs._batches["BATCH-1"] = {
            "batch_id": "BATCH-1",
            "status": "open",
            "job_ids": ["JOB-GHOST"],
        }
        errors = validate_prospective_graph(self.gs)
        self.assertTrue(any("batch" in e.lower() and "JOB-GHOST" in e for e in errors))

    def test_multiple_errors(self) -> None:
        job = _minimal_job_def("JOB-1")
        job["role"] = ""
        job["purpose_key"] = ""
        errors = validate_prospective_graph(
            self.gs,
            new_jobs=[job],
            new_edges=[_minimal_edge_def("EDGE-1", "JOB-1", "JOB-MISSING")],
        )
        self.assertGreater(len(errors), 1)

    def test_unreachable_job_with_no_edges(self) -> None:
        job = _minimal_job_def("JOB-1", expansion_origin="ROOT")
        job["expansion_origin"] = "JOB-PARENT"
        errors = validate_prospective_graph(self.gs, new_jobs=[job])
        self.assertTrue(any("unreachable" in e for e in errors))


# ===========================================================================
# Task 3.6 Tests: Limit enforcement
# ===========================================================================

class LimitEnforcementTest(unittest.TestCase):
    """Test immutable ceilings enforcement with whole-plan rejection."""

    def test_within_limits(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        errors = validate_limits(gs, proposed_job_count=2)
        self.assertEqual(errors, [])

    def test_exceeds_total_jobs(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        for i in range(50):
            gs._jobs[f"JOB-{i}"] = _minimal_job_def(f"JOB-{i}")
        errors = validate_limits(gs, proposed_job_count=1)
        self.assertTrue(any("total jobs" in e for e in errors))

    def test_exceeds_jobs_per_cycle(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        errors = validate_limits(gs, proposed_job_count=6)
        self.assertTrue(any("per expansion" in e for e in errors))

    def test_exceeds_graph_vertices(self) -> None:
        env = _minimal_envelope()
        env["limits"]["max_total_jobs"] = 100
        gs = GraphState(envelope=env)
        gs.limits = {"max_vertices": 3}
        for i in range(3):
            gs._jobs[f"JOB-{i}"] = _minimal_job_def(f"JOB-{i}")
        errors = validate_limits(gs, proposed_job_count=1)
        self.assertTrue(any("vertices" in e for e in errors))

    def test_exceeds_graph_edges(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_edges": 2}
        for i in range(3):
            gs._edges[f"EDGE-{i}"] = _minimal_edge_def(f"EDGE-{i}", f"JOB-{i}", f"JOB-{i+1}")
        errors = validate_limits(gs)
        self.assertTrue(any("edges" in e for e in errors))

    def test_exceeds_expansion_depth(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_expansion_depth": 2}
        errors = validate_limits(gs, proposed_expansion_depth=3)
        self.assertTrue(any("depth" in e for e in errors))

    def test_exceeds_fan_out(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"fan_out_limit": 3}
        errors = validate_limits(gs, proposed_job_count=4)
        self.assertTrue(any("fan-out" in e for e in errors))

    def test_exceeds_concurrency(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_concurrency": 2}
        errors = validate_limits(gs, proposed_concurrency=3)
        self.assertTrue(any("concurrency" in e for e in errors))

    def test_exceeds_external_effects(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_external_effects": 1}
        errors = validate_limits(gs, proposed_external_effects=2)
        self.assertTrue(any("external effects" in e for e in errors))

    def test_exceeds_prompt_size(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_prompt_size": 1000}
        errors = validate_limits(gs, proposed_prompt_size=2000)
        self.assertTrue(any("prompt size" in e for e in errors))

    def test_exceeds_plan_size(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_plan_size": 500}
        errors = validate_limits(gs, proposed_plan_size=1000)
        self.assertTrue(any("plan size" in e for e in errors))

    def test_exceeds_time(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_time_seconds": 60.0}
        errors = validate_limits(gs, estimated_time_seconds=120.0)
        self.assertTrue(any("time" in e for e in errors))

    def test_exceeds_cost(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_cost": 10.0}
        errors = validate_limits(gs, estimated_cost=15.0)
        self.assertTrue(any("cost" in e for e in errors))

    def test_exceeds_hypotheses_per_group(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_hypotheses_per_group": 3}
        errors = validate_limits(gs, proposed_hypothesis_count=5)
        self.assertTrue(any("hypotheses" in e for e in errors))

    def test_exceeds_open_batches(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {"max_open_batches": 2}
        gs._batches["B1"] = {"batch_id": "B1", "status": "open"}
        gs._batches["B2"] = {"batch_id": "B2", "status": "open"}
        errors = validate_limits(gs, proposed_batch_count=1)
        self.assertTrue(any("open batches" in e for e in errors))

    def test_whole_plan_rejection(self) -> None:
        """Multiple limit violations all reported, not just the first."""
        gs = GraphState(envelope=_minimal_envelope())
        gs.limits = {
            "max_concurrency": 1,
            "max_external_effects": 0,
        }
        errors = validate_limits(
            gs,
            proposed_concurrency=5,
            proposed_external_effects=3,
        )
        self.assertGreaterEqual(len(errors), 2)

    def test_no_limits_configured_passes(self) -> None:
        env = _minimal_envelope()
        env["limits"] = {}
        gs = GraphState(envelope=env)
        gs.limits = {}
        errors = validate_limits(gs, proposed_job_count=1000)
        self.assertEqual(errors, [])


# ===========================================================================
# Graph status transitions
# ===========================================================================

class GraphStatusTransitionTest(unittest.TestCase):
    """Test graph status transition validation."""

    def test_planning_to_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        transition_graph_status(gs, GraphStatus.PENDING)
        self.assertEqual(gs.status, GraphStatus.PENDING)

    def test_planning_to_open_rejected(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.OPEN)

    def test_open_to_planning(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_open_to_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_sealed_is_terminal(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.SEALED)
        with self.assertRaises(OrchestratorError):
            transition_graph_status(gs, GraphStatus.OPEN)

    def test_canceling_to_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.CANCELING)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_advance_graph_revision(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), graph_revision=1)
        old_digest = gs.graph_digest
        new_rev = advance_graph_revision(gs)
        self.assertEqual(new_rev, 2)
        self.assertEqual(gs.graph_revision, 2)
        self.assertNotEqual(gs.graph_digest, old_digest)


if __name__ == "__main__":
    unittest.main()
