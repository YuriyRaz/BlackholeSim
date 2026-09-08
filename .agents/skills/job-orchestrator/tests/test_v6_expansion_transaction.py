"""Tests for v6 expansion transaction boundaries and recovery."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError, atomic_write, canonical_bytes  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    ExpansionSlot,
    validate_expansion_slot,
    add_job_to_graph,
    add_edge_to_graph,
    compute_graph_digest,
    transition_graph_status,
    advance_graph_revision,
)
from transaction_v6 import (  # noqa: E402
    ExpansionStager,
    TransactionManifest,
    ExpansionCommitter,
    ExpansionRecovery,
)


def _valid_id() -> str:
    return "T-ABCDEFGHIJKLMOPQRST"


def _valid_digest() -> str:
    return "a" * 64


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
        "created_at": "2026-01-15T10:30:00Z",
    }


def _minimal_job_def(job_id: str = "JOB-AAAAAAAAAAAAAAAAAAAA") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "title": f"test-{job_id}",
        "prompt_path": f"prompts/{job_id}.md",
        "role": "implementation",
        "purpose_key": "impl-main",
        "graph_generation": 1,
        "expansion_origin": "ROOT",
        "authority_id": _valid_id(),
        "created_at": "2026-01-15T10:30:00Z",
    }


def _minimal_edge_def(
    edge_id: str = "EDGE-AAAAAAAAAAAAAAAAAAAA",
    source: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    target: str = "JOB-BBBBBBBBBBBBBBBBBBBB",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "edge_id": edge_id,
        "source_job_id": source,
        "target_job_id": target,
        "edge_type": "success",
        "graph_revision": 1,
        "created_at": "2026-01-15T10:30:00Z",
    }


def _minimal_expansion() -> dict:
    return {
        "plan_id": _valid_id(),
        "campaign_id": _valid_id(),
        "graph_revision": 1,
        "jobs_added": [
            {
                "job_id": "LJOB-LOCAL1",
                "role": "implementation",
                "purpose_key": "impl-a",
                "expansion_origin": "ROOT",
                "authority_id": _valid_id(),
            },
        ],
        "edges_added": [
            {
                "source_job_id": "LJOB-LOCAL1",
                "target_job_id": "JOB-EXISTING",
                "edge_type": "success",
            },
        ],
    }


# ===========================================================================
# Task 6.1 Tests: Expansion slot
# ===========================================================================

class ExpansionSlotTest(unittest.TestCase):
    """Test ExpansionSlot creation, activation, and phase transitions."""

    def test_slot_starts_idle(self) -> None:
        slot = ExpansionSlot()
        self.assertTrue(slot.is_idle())
        self.assertIsNone(slot.active_expansion_id)
        self.assertEqual(slot.phase, ExpansionSlot.PHASE_IDLE)

    def test_activate_slot(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        self.assertFalse(slot.is_idle())
        self.assertEqual(slot.active_expansion_id, "EXP-1")
        self.assertEqual(slot.phase, ExpansionSlot.PHASE_PLANNING)
        self.assertEqual(slot.created_revision, 1)
        self.assertEqual(slot.plan_digest, "abc123")

    def test_activate_rejects_busy_slot(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        with self.assertRaises(OrchestratorError) as ctx:
            slot.activate("EXP-2", 2, "def456")
        self.assertIn("busy", str(ctx.exception))

    def test_advance_phase_planning_to_staging(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        slot.advance_phase(ExpansionSlot.PHASE_STAGING)
        self.assertEqual(slot.phase, ExpansionSlot.PHASE_STAGING)

    def test_advance_phase_staging_to_committing(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        slot.advance_phase(ExpansionSlot.PHASE_STAGING)
        slot.advance_phase(ExpansionSlot.PHASE_COMMITTING)
        self.assertEqual(slot.phase, ExpansionSlot.PHASE_COMMITTING)

    def test_advance_phase_committing_to_visible(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        slot.advance_phase(ExpansionSlot.PHASE_STAGING)
        slot.advance_phase(ExpansionSlot.PHASE_COMMITTING)
        slot.advance_phase(ExpansionSlot.PHASE_VISIBLE)
        self.assertEqual(slot.phase, ExpansionSlot.PHASE_VISIBLE)

    def test_advance_phase_invalid_skip(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        with self.assertRaises(OrchestratorError) as ctx:
            slot.advance_phase(ExpansionSlot.PHASE_COMMITTING)
        self.assertIn("invalid", str(ctx.exception))

    def test_release_slot(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        slot.release()
        self.assertTrue(slot.is_idle())
        self.assertIsNone(slot.active_expansion_id)

    def test_slot_round_trip(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 3, "plan-digest")
        slot.advance_phase(ExpansionSlot.PHASE_STAGING)
        d = slot.to_dict()
        slot2 = ExpansionSlot.from_dict(d)
        self.assertEqual(slot2.active_expansion_id, "EXP-1")
        self.assertEqual(slot2.phase, ExpansionSlot.PHASE_STAGING)
        self.assertEqual(slot2.created_revision, 3)

    def test_validate_expansion_slot_idle(self) -> None:
        slot = ExpansionSlot()
        errors = validate_expansion_slot(slot)
        self.assertEqual(errors, [])

    def test_validate_expansion_slot_active_valid(self) -> None:
        slot = ExpansionSlot()
        slot.activate("EXP-1", 1, "abc123")
        errors = validate_expansion_slot(slot)
        self.assertEqual(errors, [])

    def test_validate_expansion_slot_missing_expansion_id(self) -> None:
        slot = ExpansionSlot()
        slot.phase = ExpansionSlot.PHASE_PLANNING
        errors = validate_expansion_slot(slot)
        self.assertTrue(any("active_expansion_id" in e for e in errors))

    def test_validate_expansion_slot_missing_plan_digest(self) -> None:
        slot = ExpansionSlot()
        slot.active_expansion_id = "EXP-1"
        slot.phase = ExpansionSlot.PHASE_PLANNING
        slot.created_revision = 1
        errors = validate_expansion_slot(slot)
        self.assertTrue(any("plan_digest" in e for e in errors))


# ===========================================================================
# Task 6.1 Tests: Graph status transitions
# ===========================================================================

class GraphStatusTransitionExtendedTest(unittest.TestCase):
    """Test all graph status transitions for expansion lifecycle."""

    def test_planning_to_pending(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        transition_graph_status(gs, GraphStatus.PENDING)
        self.assertEqual(gs.status, GraphStatus.PENDING)

    def test_pending_to_committing(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.COMMITTING)
        self.assertEqual(gs.status, GraphStatus.COMMITTING)

    def test_committing_to_open(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.COMMITTING)
        transition_graph_status(gs, GraphStatus.OPEN)
        self.assertEqual(gs.status, GraphStatus.OPEN)

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

    def test_planning_to_canceling(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PLANNING)
        transition_graph_status(gs, GraphStatus.CANCELING)
        self.assertEqual(gs.status, GraphStatus.CANCELING)

    def test_pending_to_recovery(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.PENDING)
        transition_graph_status(gs, GraphStatus.RECOVERY_REQUIRED)
        self.assertEqual(gs.status, GraphStatus.RECOVERY_REQUIRED)

    def test_committing_to_recovery(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.COMMITTING)
        transition_graph_status(gs, GraphStatus.RECOVERY_REQUIRED)
        self.assertEqual(gs.status, GraphStatus.RECOVERY_REQUIRED)

    def test_open_to_recovery(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.OPEN)
        transition_graph_status(gs, GraphStatus.RECOVERY_REQUIRED)
        self.assertEqual(gs.status, GraphStatus.RECOVERY_REQUIRED)

    def test_recovery_to_planning(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.RECOVERY_REQUIRED)
        transition_graph_status(gs, GraphStatus.PLANNING)
        self.assertEqual(gs.status, GraphStatus.PLANNING)

    def test_recovery_to_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.RECOVERY_REQUIRED)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_canceling_to_sealed(self) -> None:
        gs = GraphState(envelope=_minimal_envelope(), status=GraphStatus.CANCELING)
        transition_graph_status(gs, GraphStatus.SEALED)
        self.assertEqual(gs.status, GraphStatus.SEALED)

    def test_graph_state_includes_expansion_slot(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        gs.expansion_slot.activate("EXP-1", 1, "abc")
        d = gs.to_dict()
        self.assertIn("expansion_slot", d)
        gs2 = GraphState.from_dict(d)
        self.assertEqual(gs2.expansion_slot.active_expansion_id, "EXP-1")


# ===========================================================================
# Task 6.2 Tests: Expansion staging
# ===========================================================================

class ExpansionStagingTest(unittest.TestCase):
    """Test ExpansionStager identity assignment, byte writing, and hashing."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_stage_expansion_assigns_identities(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1, "graph_generation": 1},
            plan_digest="abc123",
            run_id="run-1",
            decision_id="DEC-1",
        )
        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
        self.assertIn("expansion_id", manifest)
        self.assertTrue(manifest["expansion_id"].startswith("EXP-"))
        self.assertEqual(len(manifest["prospective_jobs"]), 1)
        self.assertTrue(manifest["prospective_jobs"][0]["job_id"].startswith("JOB-"))
        self.assertEqual(len(manifest["prospective_edges"]), 1)

    def test_write_staged_bytes(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1, "graph_generation": 1},
            plan_digest="abc123",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        self.assertEqual(len(digest), 64)
        staged_path = self.staging_dir / f"{manifest['expansion_id']}.staged.json"
        self.assertTrue(staged_path.exists())
        staged_bytes = staged_path.read_bytes()
        self.assertEqual(hashlib.sha256(staged_bytes).hexdigest(), digest)

    def test_hash_transaction_deterministic(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1, "graph_generation": 1},
            plan_digest="abc123",
            run_id="run-1",
            decision_id="DEC-1",
        )
        h1 = stager.hash_transaction(manifest)
        h2 = stager.hash_transaction(manifest)
        self.assertEqual(h1, h2)

    def test_stage_expansion_deterministic_id(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        m1 = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        m2 = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        self.assertEqual(m1["expansion_id"], m2["expansion_id"])


# ===========================================================================
# Task 6.3 Tests: Transaction manifest persistence
# ===========================================================================

class TransactionManifestTest(unittest.TestCase):
    """Test TransactionManifest persistence and visibility commit."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def test_persist_manifest(self) -> None:
        tx_manifest = TransactionManifest(self.manifest_dir)
        manifest = tx_manifest.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest={"prospective_jobs": [], "prospective_edges": []},
            staged_bytes_digest="abc123",
            transaction_digest="def456",
            graph_revision_before=1,
        )
        self.assertEqual(manifest["status"], "staged")
        self.assertTrue(tx_manifest.manifest_exists("EXP-1"))

    def test_load_manifest(self) -> None:
        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest={"test": True},
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        loaded = tx_manifest.load_manifest("EXP-1")
        self.assertEqual(loaded["expansion_id"], "EXP-1")
        self.assertEqual(loaded["staging_manifest"]["test"], True)

    def test_commit_visibility(self) -> None:
        graph_path = self._write_initial_graph()
        tx_manifest = TransactionManifest(self.manifest_dir)
        staging_manifest = {
            "prospective_jobs": [_minimal_job_def("JOB-NEW")],
            "prospective_edges": [],
        }
        tx_manifest.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest=staging_manifest,
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        new_rev = tx_manifest.commit_visibility(
            expansion_id="EXP-1",
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        self.assertEqual(new_rev, 2)
        gs = GraphState.load(graph_path)
        self.assertIn("JOB-NEW", gs._jobs)
        loaded_manifest = tx_manifest.load_manifest("EXP-1")
        self.assertEqual(loaded_manifest["status"], "committed")
        self.assertEqual(loaded_manifest["graph_revision_after"], 2)


# ===========================================================================
# Task 6.4 Tests: Idempotent commit-expansion CAS
# ===========================================================================

class ExpansionCommitterTest(unittest.TestCase):
    """Test ExpansionCommitter CAS validation and idempotent commit."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"
        self.staging_dir = Path(self._td.name) / "staging"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def _stage_and_manifest(self, graph_path: Path) -> tuple[str, dict, int, str]:
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1, "graph_generation": 1},
            plan_digest="plan-abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest=stager.hash_transaction(staging_manifest),
            graph_revision_before=1,
        )

        gs = GraphState.load(graph_path)
        actual_digest = compute_graph_digest(gs)

        return (
            staging_manifest["expansion_id"],
            staging_manifest,
            gs.graph_revision,
            actual_digest,
        )

    def test_validate_cas_valid(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        manifest = {
            "expansion_id": "EXP-1",
            "plan_digest": "abc",
            "status": "staged",
        }
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="digest-aaa",
            actual_graph_revision=1,
            actual_graph_digest="digest-aaa",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest=manifest,
        )
        self.assertEqual(errors, [])

    def test_validate_cas_revision_mismatch(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        manifest = {"expansion_id": "EXP-1", "plan_digest": "abc", "status": "staged"}
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="digest-aaa",
            actual_graph_revision=2,
            actual_graph_digest="digest-aaa",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest=manifest,
        )
        self.assertTrue(any("graph_revision" in e for e in errors))

    def test_validate_cas_expansion_id_mismatch(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        manifest = {"expansion_id": "EXP-WRONG", "plan_digest": "abc", "status": "staged"}
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="aaa",
            actual_graph_revision=1,
            actual_graph_digest="aaa",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest=manifest,
        )
        self.assertTrue(any("expansion_id" in e for e in errors))

    def test_commit_expansion(self) -> None:
        graph_path = self._write_initial_graph()
        expansion_id, staging_manifest, rev, digest = self._stage_and_manifest(graph_path)

        committer = ExpansionCommitter(self.manifest_dir)
        result = committer.commit_expansion(
            expansion_id=expansion_id,
            plan_digest="plan-abc",
            expected_graph_revision=rev,
            expected_graph_digest=digest,
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["graph_revision"], 2)

    def test_commit_expansion_cas_failure(self) -> None:
        graph_path = self._write_initial_graph()
        expansion_id, staging_manifest, rev, digest = self._stage_and_manifest(graph_path)

        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-X"))
        gs.graph_digest = compute_graph_digest(gs)
        wrong_digest = gs.graph_digest

        committer = ExpansionCommitter(self.manifest_dir)
        with self.assertRaises(OrchestratorError) as ctx:
            committer.commit_expansion(
                expansion_id=expansion_id,
                plan_digest="plan-abc",
                expected_graph_revision=rev,
                expected_graph_digest=wrong_digest,
                graph_state_path=graph_path,
                staging_manifest=staging_manifest,
            )
        self.assertIn("CAS", str(ctx.exception))

    def test_idempotent_commit(self) -> None:
        graph_path = self._write_initial_graph()
        expansion_id, staging_manifest, rev, digest = self._stage_and_manifest(graph_path)

        committer = ExpansionCommitter(self.manifest_dir)
        result1 = committer.commit_expansion(
            expansion_id=expansion_id,
            plan_digest="plan-abc",
            expected_graph_revision=rev,
            expected_graph_digest=digest,
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        result2 = committer.commit_expansion(
            expansion_id=expansion_id,
            plan_digest="plan-abc",
            expected_graph_revision=rev,
            expected_graph_digest=digest,
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        self.assertTrue(result2.get("idempotent_replay"))
        self.assertEqual(result1["graph_revision"], result2["graph_revision"])


# ===========================================================================
# Task 6.5 Tests: Roll-forward recovery
# ===========================================================================

class ExpansionRecoveryTest(unittest.TestCase):
    """Test crash recovery at every expansion transaction boundary."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def test_crash_before_writes(self) -> None:
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        result = recovery.recover_from_crash("EXP-NONEXISTENT")
        self.assertEqual(result["recovery_action"], "nothing_to_recover")

    def test_crash_during_partial_writes_staged_only(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(staging_manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "replay_staging")

    def test_crash_after_visibility_commit(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )
        tx_manifest.commit_visibility(
            expansion_id=staging_manifest["expansion_id"],
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(staging_manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "cleanup")

    def test_crash_before_cleanup_after_manifest(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(staging_manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "committed")

        gs = GraphState.load(graph_path)
        new_job_id = staging_manifest["prospective_jobs"][0]["job_id"]
        self.assertIn(new_job_id, gs._jobs)

    def test_contradictory_bytes_blocking(self) -> None:
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)

        manifest_path = self.manifest_dir / "EXP-1.manifest.json"
        staged_path = self.staging_dir / "EXP-1.staged.json"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": "EXP-1",
            "staged_bytes_digest": "aaaa" * 16,
            "status": "staged",
            "staging_manifest": {"expansion_id": "EXP-1"},
        }
        atomic_write(manifest_path, canonical_bytes(manifest))
        atomic_write(staged_path, b"different bytes")

        errors = recovery.block_contradictory("EXP-1")
        self.assertTrue(any("contradictory" in e.lower() for e in errors))

    def test_validate_manifest_clean(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        errors = recovery.validate_manifest(staging_manifest["expansion_id"])
        self.assertEqual(errors, [])

    def test_validate_manifest_missing(self) -> None:
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        errors = recovery.validate_manifest("EXP-MISSING")
        self.assertTrue(any("not found" in e for e in errors))

    def test_cleanup_removes_files(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])
        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        recovery.cleanup(staging_manifest["expansion_id"])
        self.assertFalse(
            (self.manifest_dir / f"{staging_manifest['expansion_id']}.manifest.json").exists()
        )
        self.assertFalse(
            (self.staging_dir / f"{staging_manifest['expansion_id']}.staged.json").exists()
        )


# ===========================================================================
# Task 6.6 Tests: No partial graph becomes schedulable
# ===========================================================================

class NoPartialGraphSchedulableTest(unittest.TestCase):
    """Prove that no partial graph becomes schedulable at any crash point."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def test_partial_graph_not_schedulable_after_staging_only(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        gs = GraphState.load(graph_path)
        self.assertNotIn("JOB-NEW", gs._jobs)
        self.assertEqual(gs.graph_revision, 1)

    def test_partial_graph_not_schedulable_after_manifest_only(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        gs = GraphState.load(graph_path)
        self.assertNotIn("JOB-NEW", gs._jobs)
        self.assertEqual(gs.graph_revision, 1)

    def test_graph_only_updated_after_commit_visibility(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        manifest = tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        new_job_id = staging_manifest["prospective_jobs"][0]["job_id"]

        gs_before = GraphState.load(graph_path)
        self.assertNotIn(new_job_id, gs_before._jobs)

        tx_manifest.commit_visibility(
            expansion_id=staging_manifest["expansion_id"],
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )

        gs_after = GraphState.load(graph_path)
        self.assertIn(new_job_id, gs_after._jobs)
        self.assertEqual(gs_after.graph_revision, 2)

    def test_cas_prevents_double_commit(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        staging_manifest = stager.stage_expansion(
            expansion=_minimal_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        staged_digest = stager.write_staged_bytes(staging_manifest, staging_manifest["expansion_id"])

        tx_manifest = TransactionManifest(self.manifest_dir)
        tx_manifest.persist_manifest(
            expansion_id=staging_manifest["expansion_id"],
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        gs = GraphState.load(graph_path)
        actual_digest = compute_graph_digest(gs)

        committer = ExpansionCommitter(self.manifest_dir)
        result1 = committer.commit_expansion(
            expansion_id=staging_manifest["expansion_id"],
            plan_digest="abc",
            expected_graph_revision=gs.graph_revision,
            expected_graph_digest=actual_digest,
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        self.assertEqual(result1["status"], "committed")

        gs_after = GraphState.load(graph_path)
        new_digest = compute_graph_digest(gs_after)
        result2 = committer.commit_expansion(
            expansion_id=staging_manifest["expansion_id"],
            plan_digest="abc",
            expected_graph_revision=gs_after.graph_revision,
            expected_graph_digest=new_digest,
            graph_state_path=graph_path,
            staging_manifest=staging_manifest,
        )
        self.assertTrue(result2.get("idempotent_replay"))
        self.assertEqual(gs_after.graph_revision, 2)


if __name__ == "__main__":
    unittest.main()
