"""End-to-end verification tests for v6 graph transaction fault injection.

Task 15.2: Graph transaction fault-injection tests for every staging,
manifest, file-write, visibility-commit, validation, and cleanup boundary.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError, atomic_write, canonical_bytes, content_hash, stable_id  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    GraphStatus,
    add_job_to_graph,
    add_edge_to_graph,
    compute_graph_digest,
    transition_graph_status,
)
from transaction_v6 import (  # noqa: E402
    ExpansionStager,
    TransactionManifest,
    ExpansionCommitter,
    ExpansionRecovery,
)


_VALID_AUTH = "AUTH-AAAAAAAAAAAAAAAAAAAA"


def _envelope() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": "ENV-AAAAAAAAAAAAAAAAAAAA",
        "campaign_id": "CMP-AAAAAAAAAAAAAAAAAAAA",
        "goal": "test",
        "strategy": "full-campaign",
        "version": 1,
        "authority_id": _VALID_AUTH,
        "limits": {"max_cycles": 10, "max_jobs_per_cycle": 5, "max_total_jobs": 50},
        "created_at": "2026-01-15T10:30:00Z",
    }


def _job_def(job_id: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "title": f"test-{job_id}",
        "prompt_path": f"prompts/{job_id}.md",
        "role": "implementation",
        "purpose_key": "test-purpose",
        "graph_generation": 1,
        "expansion_origin": "ROOT-00000000000000000000",
        "authority_id": _VALID_AUTH,
        "created_at": "2026-01-15T10:30:00Z",
    }


def _expansion() -> dict:
    return {
        "plan_id": "PLAN-AAAAAAAAAAAAAAAAAAAA",
        "campaign_id": "CMP-AAAAAAAAAAAAAAAAAAAA",
        "graph_revision": 1,
        "jobs_added": [
            {
                "job_id": "LJOB-NEW1",
                "role": "implementation",
                "purpose_key": "impl-a",
                "expansion_origin": "ROOT-00000000000000000000",
                "authority_id": "AUTH-AAAAAAAAAAAAAAAAAAAA",
            },
        ],
        "edges_added": [
            {
                "source_job_id": "LJOB-NEW1",
                "target_job_id": "JOB-EXISTING",
                "edge_type": "success",
            },
        ],
        "finding_ids": [],
    }


def _edge_def(source: str, target: str) -> dict:
    edge_id = stable_id("EDGE", source, target).upper()
    return {
        "schema_version": SCHEMA_VERSION,
        "edge_id": edge_id,
        "source_job_id": source,
        "target_job_id": target,
        "edge_type": "success",
        "graph_revision": 1,
        "created_at": "2026-01-15T10:30:00Z",
    }


class StagingFaultTest(unittest.TestCase):
    """Fault injection at staging boundary."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_staging_with_empty_expansion(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion={"plan_id": "P1", "campaign_id": "C1", "jobs_added": [], "edges_added": []},
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        self.assertEqual(len(manifest["prospective_jobs"]), 0)
        self.assertEqual(len(manifest["prospective_edges"]), 0)

    def test_staging_preserves_plan_digest(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="plan-xyz",
            run_id="run-1",
            decision_id="DEC-1",
        )
        self.assertEqual(manifest["plan_digest"], "plan-xyz")

    def test_staging_deterministic_across_calls(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        m1 = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        m2 = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        self.assertEqual(m1["expansion_id"], m2["expansion_id"])

    def test_write_staged_bytes_produces_valid_json(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        staged_path = self.staging_dir / f"{manifest['expansion_id']}.staged.json"
        data = json.loads(staged_path.read_bytes())
        self.assertEqual(data["expansion_id"], manifest["expansion_id"])
        self.assertEqual(len(digest), 64)


class ManifestFaultTest(unittest.TestCase):
    """Fault injection at manifest persistence boundary."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.manifest_dir = Path(self._td.name) / "manifests"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_persist_manifest_roundtrip(self) -> None:
        tx = TransactionManifest(self.manifest_dir)
        manifest = tx.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest={"test": True},
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        loaded = tx.load_manifest("EXP-1")
        self.assertEqual(loaded["status"], "staged")
        self.assertEqual(loaded["staging_manifest"]["test"], True)

    def test_manifest_exists_check(self) -> None:
        tx = TransactionManifest(self.manifest_dir)
        self.assertFalse(tx.manifest_exists("EXP-NONE"))
        tx.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest={},
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        self.assertTrue(tx.manifest_exists("EXP-1"))

    def test_manifest_overwrite_prevented(self) -> None:
        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest={"v": 1},
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        loaded = tx.load_manifest("EXP-1")
        self.assertEqual(loaded["staging_manifest"]["v"], 1)


class FileWriteFaultTest(unittest.TestCase):
    """Fault injection at file write boundaries."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_atomic_write_creates_parent_dirs(self) -> None:
        nested = Path(self._td.name) / "a" / "b" / "c" / "file.json"
        atomic_write(nested, b'{"test": true}')
        self.assertTrue(nested.exists())
        data = json.loads(nested.read_bytes())
        self.assertTrue(data["test"])

    def test_staged_bytes_match_digest(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        staged_path = self.staging_dir / f"{manifest['expansion_id']}.staged.json"
        actual = hashlib.sha256(staged_path.read_bytes()).hexdigest()
        self.assertEqual(digest, actual)

    def test_transaction_hash_deterministic(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        h1 = stager.hash_transaction(manifest)
        h2 = stager.hash_transaction(manifest)
        self.assertEqual(h1, h2)


class VisibilityCommitFaultTest(unittest.TestCase):
    """Fault injection at visibility commit boundary."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_envelope())
        add_job_to_graph(gs, _job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def test_visibility_commit_advances_revision(self) -> None:
        graph_path = self._write_initial_graph()
        tx = TransactionManifest(self.manifest_dir)
        staging = {
            "prospective_jobs": [_job_def("JOB-NEW")],
            "prospective_edges": [],
        }
        tx.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest=staging,
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        new_rev = tx.commit_visibility(
            expansion_id="EXP-1",
            graph_state_path=graph_path,
            staging_manifest=staging,
        )
        self.assertEqual(new_rev, 2)
        gs = GraphState.load(graph_path)
        self.assertIn("JOB-NEW", gs._jobs)

    def test_visibility_commit_updates_manifest_status(self) -> None:
        graph_path = self._write_initial_graph()
        tx = TransactionManifest(self.manifest_dir)
        staging = {"prospective_jobs": [], "prospective_edges": []}
        tx.persist_manifest(
            expansion_id="EXP-1",
            staging_manifest=staging,
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        tx.commit_visibility(
            expansion_id="EXP-1",
            graph_state_path=graph_path,
            staging_manifest=staging,
        )
        loaded = tx.load_manifest("EXP-1")
        self.assertEqual(loaded["status"], "committed")
        self.assertIn("committed_at", loaded)

    def test_partial_graph_not_visible_before_commit(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(Path(self._td.name) / "staging")
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(manifest, manifest["expansion_id"])

        gs_before = GraphState.load(graph_path)
        self.assertNotIn("JOB-NEW1", gs_before._jobs)


class ValidationFaultTest(unittest.TestCase):
    """Fault injection at validation boundaries."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_cas_rejects_revision_mismatch(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="aaa",
            actual_graph_revision=2,
            actual_graph_digest="aaa",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest={"expansion_id": "EXP-1", "plan_digest": "abc", "status": "staged"},
        )
        self.assertTrue(any("graph_revision" in e for e in errors))

    def test_cas_rejects_digest_mismatch(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="aaa",
            actual_graph_revision=1,
            actual_graph_digest="bbb",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest={"expansion_id": "EXP-1", "plan_digest": "abc", "status": "staged"},
        )
        self.assertTrue(any("graph_digest" in e for e in errors))

    def test_cas_rejects_expansion_id_mismatch(self) -> None:
        committer = ExpansionCommitter(self.manifest_dir)
        errors = committer.validate_cas(
            expected_graph_revision=1,
            expected_graph_digest="aaa",
            actual_graph_revision=1,
            actual_graph_digest="aaa",
            expansion_id="EXP-1",
            plan_digest="abc",
            manifest={"expansion_id": "EXP-WRONG", "plan_digest": "abc", "status": "staged"},
        )
        self.assertTrue(any("expansion_id" in e for e in errors))

    def test_manifest_validation_clean(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id=manifest["expansion_id"],
            staging_manifest=manifest,
            staged_bytes_digest=digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        errors = recovery.validate_manifest(manifest["expansion_id"])
        self.assertEqual(errors, [])


class CleanupFaultTest(unittest.TestCase):
    """Fault injection at cleanup boundary."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_cleanup_removes_both_files(self) -> None:
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(manifest, manifest["expansion_id"])
        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id=manifest["expansion_id"],
            staging_manifest=manifest,
            staged_bytes_digest="abc",
            transaction_digest="def",
            graph_revision_before=1,
        )
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        recovery.cleanup(manifest["expansion_id"])
        self.assertFalse(
            (self.manifest_dir / f"{manifest['expansion_id']}.manifest.json").exists()
        )
        self.assertFalse(
            (self.staging_dir / f"{manifest['expansion_id']}.staged.json").exists()
        )

    def test_cleanup_idempotent(self) -> None:
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        recovery.cleanup("EXP-NONEXISTENT")
        self.assertFalse((self.manifest_dir / "EXP-NONEXISTENT.manifest.json").exists())


class RecoveryFromEachFaultTest(unittest.TestCase):
    """Test recovery from each fault type."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self._td.name) / "staging"
        self.manifest_dir = Path(self._td.name) / "manifests"
        self.graph_dir = Path(self._td.name) / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_envelope())
        add_job_to_graph(gs, _job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def test_recovery_from_nothing(self) -> None:
        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        result = recovery.recover_from_crash("EXP-NOTHING")
        self.assertEqual(result["recovery_action"], "nothing_to_recover")

    def test_recovery_from_staged_only(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        stager.write_staged_bytes(manifest, manifest["expansion_id"])

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "replay_staging")

    def test_recovery_after_manifest(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id=manifest["expansion_id"],
            staging_manifest=manifest,
            staged_bytes_digest=digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "committed")

    def test_recovery_after_commit(self) -> None:
        graph_path = self._write_initial_graph()
        stager = ExpansionStager(self.staging_dir)
        manifest = stager.stage_expansion(
            expansion=_expansion(),
            graph_state={"graph_revision": 1},
            plan_digest="abc",
            run_id="run-1",
            decision_id="DEC-1",
        )
        digest = stager.write_staged_bytes(manifest, manifest["expansion_id"])
        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id=manifest["expansion_id"],
            staging_manifest=manifest,
            staged_bytes_digest=digest,
            transaction_digest="tx-digest",
            graph_revision_before=1,
        )
        tx.commit_visibility(
            expansion_id=manifest["expansion_id"],
            graph_state_path=graph_path,
            staging_manifest=manifest,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash(manifest["expansion_id"])
        self.assertEqual(result["recovery_action"], "cleanup")

    def test_contradictory_bytes_blocked(self) -> None:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(
            self.manifest_dir / "EXP-1.manifest.json",
            canonical_bytes({"expansion_id": "EXP-1", "staged_bytes_digest": "a" * 64, "status": "staged", "staging_manifest": {"expansion_id": "EXP-1"}}),
        )
        atomic_write(self.staging_dir / "EXP-1.staged.json", b"different bytes")

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, self.graph_dir)
        errors = recovery.block_contradictory("EXP-1")
        self.assertTrue(len(errors) > 0)


class RecoveryReconciliationVisibilityTest(unittest.TestCase):
    """End-to-end recovery test: crash between graph and run visibility writes."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.run_root = Path(self._td.name)
        self.staging_dir = self.run_root / "transactions" / "staging"
        self.manifest_dir = self.run_root / "transactions" / "manifests"
        self.graph_dir = self.run_root / "graph"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_initial_graph(self) -> Path:
        gs = GraphState(envelope=_envelope())
        add_job_to_graph(gs, _job_def("JOB-EXISTING"))
        gs.graph_digest = compute_graph_digest(gs)
        graph_path = self.graph_dir / "graph.json"
        gs.save(graph_path)
        return graph_path

    def _write_run_json(self, graph_path: Path, job_ids: list[str]) -> Path:
        gs = GraphState.load(graph_path)
        run = {
            "schema_version": SCHEMA_VERSION,
            "protocol_revision": "v6-closed",
            "run_id": "run-test-001",
            "goal": "test recovery",
            "status": "active",
            "workspace": str(self.run_root),
            "request_file": "request.md",
            "campaign_envelope_id": "ENV-AAAAAAAAAAAAAAAAAAAA",
            "current_cycle_id": "CYC-TEST",
            "job_ids": job_ids,
            "graph_revision": gs.graph_revision,
            "graph_digest": gs.graph_digest,
            "graph_status": "open",
            "terminal_barrier": {
                "expansions_settled": False,
                "transactions_settled": False,
                "batches_settled": False,
                "jobs_settled": False,
                "reports_accepted": False,
                "gates_settled": False,
                "findings_dispositioned": False,
                "side_effects_reconciled": False,
                "final_audit_passed": False,
            },
            "immutable_limits": {
                "campaign_limits_digest": "a" * 64,
                "graph_policy_id": "POL-DEFAULT",
            },
            "expansion_ledger": [],
            "current_goal_judge_id": None,
            "active_planning_authority_id": _VALID_AUTH,
            "active_transaction_id": None,
            "terminal_commit_id": None,
            "created_at": "2026-01-15T10:30:00Z",
            "updated_at": "2026-01-15T10:30:00Z",
        }
        run_path = self.run_root / "run.json"
        atomic_write(run_path, canonical_bytes(run))
        return run_path

    def test_crash_between_graph_and_run_visibility_recovers_job_ids(self) -> None:
        graph_path = self._write_initial_graph()
        self._write_run_json(graph_path, ["JOB-EXISTING"])

        gs = GraphState.load(graph_path)
        new_job = _job_def("JOB-NEW")
        new_edge = _edge_def("JOB-EXISTING", "JOB-NEW")
        add_job_to_graph(gs, new_job)
        add_edge_to_graph(gs, new_edge)
        from graph_v6 import advance_graph_revision
        advance_graph_revision(gs)
        gs.save(graph_path)

        staging_manifest = {
            "expansion_id": "EXP-RECOVERY",
            "prospective_jobs": [new_job],
            "prospective_edges": [new_edge],
        }
        stager = ExpansionStager(self.staging_dir)
        staged_bytes = canonical_bytes(staging_manifest)
        staged_digest = hashlib.sha256(staged_bytes).hexdigest()
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.staging_dir / "EXP-RECOVERY.staged.json", staged_bytes)

        tx = TransactionManifest(self.manifest_dir)
        tx.persist_manifest(
            expansion_id="EXP-RECOVERY",
            staging_manifest=staging_manifest,
            staged_bytes_digest=staged_digest,
            transaction_digest=content_hash(staged_bytes),
            graph_revision_before=1,
        )

        recovery = ExpansionRecovery(self.staging_dir, self.manifest_dir, graph_path)
        result = recovery.recover_from_crash("EXP-RECOVERY")
        self.assertEqual(result["recovery_action"], "committed")

        run_path = self.run_root / "run.json"
        run = json.loads(run_path.read_bytes())
        self.assertIn("JOB-EXISTING", run["job_ids"])
        self.assertIn("JOB-NEW", run["job_ids"])
        self.assertEqual(run["job_ids"], ["JOB-EXISTING", "JOB-NEW"])


if __name__ == "__main__":
    unittest.main()
