"""Tests for v6 target-scoped verification and repair rounds (Group 8)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, SCHEMA_VERSION, stable_id  # noqa: E402
from graph_v6 import (  # noqa: E402
    GraphState,
    VerifierAuthorityBinder,
    VerificationResultApplier,
    VerdictTracker,
    RepairRoundAppender,
    TargetAccepter,
    add_job_to_graph,
    add_verifier_assignment,
    add_repair_gate,
    get_repair_gate_history_for_target,
    get_verifier_assignments_for_target,
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
    revision: int = 1,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "history_id": history_id,
        "target_job_id": target_job_id,
        "revision": revision,
        "repair_job_id": repair_job_id,
        "finding_id": _valid_id(),
        "status": "applied",
        "evidence_refs": [],
        "recorded_at": _valid_datetime(),
    }


# ===========================================================================
# Task 8.1 Tests: Verifier authority binding
# ===========================================================================

class VerifierAuthorityBinderTest(unittest.TestCase):
    """Test VerifierAuthorityBinder binding verifier to exact target."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(self.gs, _minimal_job_def("JOB-TARGET", role="target"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-VERIFIER", role="verifier"))
        self.binder = VerifierAuthorityBinder(self.gs)

    def test_bind_verifier_authority_success(self) -> None:
        record = self.binder.bind_verifier_authority(
            assignment_id="VASS-TEST-1",
            target_job_id="JOB-TARGET",
            target_gate_revision=1,
            verifier_job_id="JOB-VERIFIER",
            run_id="run-test",
            cycle_id=_valid_id(),
            condition_id="COND-1",
            graph_generation=1,
            required_evidence_types=[],
        )
        self.assertEqual(record["assignment_id"], "VASS-TEST-1")
        self.assertEqual(record["target_job_id"], "JOB-TARGET")
        self.assertEqual(record["status"], "assigned")
        self.assertIn("VASS-TEST-1", self.gs._verifier_assignments)

    def test_validate_target_identity_rejects_missing(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.binder.validate_target_identity("JOB-MISSING")
        self.assertIn("not found", str(ctx.exception))

    def test_validate_target_identity_accepts_existing(self) -> None:
        self.binder.validate_target_identity("JOB-TARGET")

    def test_validate_gate_revision_rejects_mismatch(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate(
            target_job_id="JOB-TARGET", revision=1
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.binder.validate_gate_revision("JOB-TARGET", 999)
        self.assertIn("gate revision mismatch", str(ctx.exception))

    def test_validate_gate_revision_accepts_correct(self) -> None:
        self.binder.validate_gate_revision("JOB-TARGET", 1)

    def test_validate_graph_generation_rejects_mismatch(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-GEN", role="target"))
        self.gs._jobs["JOB-GEN"]["graph_generation"] = 2
        with self.assertRaises(OrchestratorError) as ctx:
            self.binder.validate_graph_generation("JOB-GEN", 1)
        self.assertIn("graph generation mismatch", str(ctx.exception))

    def test_validate_graph_generation_accepts_match(self) -> None:
        self.binder.validate_graph_generation("JOB-TARGET", 1)

    def test_validate_evidence_contract_rejects_no_history(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.binder.validate_evidence_contract(
                "JOB-TARGET", ["test-evidence"]
            )
        self.assertIn("evidence contract not satisfied", str(ctx.exception))

    def test_validate_evidence_contract_accepts_empty(self) -> None:
        self.binder.validate_evidence_contract("JOB-TARGET", [])


# ===========================================================================
# Task 8.2 Tests: Verification result applier
# ===========================================================================

class VerificationResultApplierTest(unittest.TestCase):
    """Test VerificationResultApplier applying results to exact target."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(self.gs, _minimal_job_def("JOB-TARGET", role="target"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-VERIFIER", role="verifier"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            target_job_id="JOB-TARGET",
            verifier_job_id="JOB-VERIFIER",
        ))
        self.applier = VerificationResultApplier(self.gs)

    def test_apply_verification_result_pass(self) -> None:
        result = self.applier.apply_verification_result(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
            evidence_refs=["run://test/evidence/1"],
        )
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["target_job_id"], "JOB-TARGET")
        assignment = self.gs._verifier_assignments["VASS-AAAAAAAAAAAAAAAAAAAA"]
        self.assertEqual(assignment["status"], "completed")
        self.assertEqual(assignment["verdict"], "pass")

    def test_apply_verification_result_fail(self) -> None:
        result = self.applier.apply_verification_result(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="fail",
        )
        self.assertEqual(result["verdict"], "fail")

    def test_apply_rejects_invalid_verdict(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
                verdict="invalid",
            )
        self.assertIn("invalid verdict", str(ctx.exception))

    def test_apply_rejects_missing_assignment(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-MISSING",
                verdict="pass",
            )
        self.assertIn("not found", str(ctx.exception))

    def test_reject_self_approval(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-SELF", role="verifier"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            assignment_id="VASS-SELF",
            target_job_id="JOB-SELF",
            verifier_job_id="JOB-SELF",
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-SELF",
                verdict="pass",
            )
        self.assertIn("self-approval", str(ctx.exception))

    def test_reject_stale_revision(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate(
            target_job_id="JOB-TARGET", revision=1
        ))
        add_repair_gate(self.gs, _minimal_repair_gate(
            history_id="RGH-2",
            target_job_id="JOB-TARGET",
            revision=2,
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
                verdict="pass",
            )
        self.assertIn("stale revision", str(ctx.exception))

    def test_reject_unauthorized_verifier(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-BAD", role="implementation"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            assignment_id="VASS-BAD",
            target_job_id="JOB-TARGET",
            verifier_job_id="JOB-BAD",
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-BAD",
                verdict="pass",
            )
        self.assertIn("unauthorized verifier", str(ctx.exception))

    def test_reject_missing_evidence(self) -> None:
        self.gs._verifier_authority_bindings["VASS-AAAAAAAAAAAAAAAAAAAA"] = {
            "required_evidence_types": ["test-evidence"],
        }
        with self.assertRaises(OrchestratorError) as ctx:
            self.applier.apply_verification_result(
                assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
                verdict="pass",
                evidence_refs=[],
            )
        self.assertIn("missing evidence", str(ctx.exception))


# ===========================================================================
# Task 8.3 Tests: Verdict tracker
# ===========================================================================

class VerdictTrackerTest(unittest.TestCase):
    """Test VerdictTracker separating execution from verdict."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(self.gs, _minimal_job_def("JOB-TARGET", role="target"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-VERIFIER", role="verifier"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            target_job_id="JOB-TARGET",
            verifier_job_id="JOB-VERIFIER",
        ))
        self.tracker = VerdictTracker(self.gs)

    def test_record_execution_completion(self) -> None:
        record = self.tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            completed_at="2026-01-15T11:00:00Z",
        )
        self.assertEqual(record["assignment_id"], "VASS-AAAAAAAAAAAAAAAAAAAA")
        self.assertEqual(record["completed_at"], "2026-01-15T11:00:00Z")
        self.assertEqual(record["target_job_id"], "JOB-TARGET")

    def test_record_execution_auto_timestamp(self) -> None:
        record = self.tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
        )
        self.assertIn("completed_at", record)
        self.assertIsNotNone(record["completed_at"])

    def test_record_execution_rejects_missing(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.tracker.record_execution_completion(assignment_id="VASS-MISSING")
        self.assertIn("not found", str(ctx.exception))

    def test_record_target_verdict_pass(self) -> None:
        record = self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
            evidence_refs=["run://test/evidence/1"],
        )
        self.assertEqual(record["verdict"], "pass")
        self.assertEqual(record["evidence_refs"], ["run://test/evidence/1"])

    def test_record_target_verdict_fail(self) -> None:
        record = self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="fail",
        )
        self.assertEqual(record["verdict"], "fail")

    def test_record_target_verdict_unavailable(self) -> None:
        record = self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="unavailable",
        )
        self.assertEqual(record["verdict"], "unavailable")

    def test_record_target_verdict_not_run(self) -> None:
        record = self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="not-run",
        )
        self.assertEqual(record["verdict"], "not-run")

    def test_record_target_verdict_rejects_invalid(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.tracker.record_target_verdict(
                assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
                verdict="invalid",
            )
        self.assertIn("invalid verdict", str(ctx.exception))

    def test_validate_verdict_separation_both_present(self) -> None:
        self.tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            completed_at="2026-01-15T11:00:00Z",
        )
        self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
        )
        result = self.tracker.validate_verdict_separation(
            "VASS-AAAAAAAAAAAAAAAAAAAA"
        )
        self.assertTrue(result)

    def test_validate_verdict_separation_rejects_same_timestamp(self) -> None:
        ts = "2026-01-15T11:00:00Z"
        self.tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            completed_at=ts,
        )
        self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
            recorded_at=ts,
        )
        with self.assertRaises(OrchestratorError) as ctx:
            self.tracker.validate_verdict_separation(
                "VASS-AAAAAAAAAAAAAAAAAAAA"
            )
        self.assertIn("verdict separation violated", str(ctx.exception))

    def test_get_execution_completion(self) -> None:
        self.tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA"
        )
        record = self.tracker.get_execution_completion(
            "VASS-AAAAAAAAAAAAAAAAAAAA"
        )
        self.assertIsNotNone(record)
        self.assertIsNone(self.tracker.get_execution_completion("VASS-MISSING"))

    def test_get_target_verdict(self) -> None:
        self.tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
        )
        record = self.tracker.get_target_verdict("VASS-AAAAAAAAAAAAAAAAAAAA")
        self.assertIsNotNone(record)
        self.assertIsNone(self.tracker.get_target_verdict("VASS-MISSING"))


# ===========================================================================
# Task 8.4 Tests: Repair round appender
# ===========================================================================

class RepairRoundAppenderTest(unittest.TestCase):
    """Test RepairRoundAppender appending repair work and fresh verifier."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(self.gs, _minimal_job_def("JOB-TARGET", role="target"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-REPAIR", role="repair"))
        self.appender = RepairRoundAppender(self.gs)

    def test_append_repair_round_success(self) -> None:
        record = self.appender.append_repair_round(
            target_job_id="JOB-TARGET",
            repair_job_id="JOB-REPAIR",
            finding_id="FIND-1",
            evidence_refs=["run://test/graph/1"],
        )
        self.assertEqual(record["target_job_id"], "JOB-TARGET")
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["repair_job_id"], "JOB-REPAIR")
        self.assertEqual(record["status"], "applied")
        history = get_repair_gate_history_for_target(self.gs, "JOB-TARGET")
        self.assertEqual(len(history), 1)

    def test_append_multiple_repair_rounds(self) -> None:
        self.appender.append_repair_round(
            target_job_id="JOB-TARGET",
            repair_job_id="JOB-REPAIR",
            finding_id="FIND-1",
        )
        self.appender.append_repair_round(
            target_job_id="JOB-TARGET",
            repair_job_id="JOB-REPAIR",
            finding_id="FIND-2",
        )
        history = get_repair_gate_history_for_target(self.gs, "JOB-TARGET")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["revision"], 1)
        self.assertEqual(history[1]["revision"], 2)

    def test_validate_repair_authority_rejects_missing_target(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.appender.validate_repair_authority("JOB-MISSING", None)
        self.assertIn("not found", str(ctx.exception))

    def test_validate_repair_authority_rejects_unauthorized_expansion(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.appender.validate_repair_authority("JOB-TARGET", "EXP-INVALID")
        self.assertIn("not in expansion ledger", str(ctx.exception))

    def test_validate_repair_authority_accepts_valid_expansion(self) -> None:
        self.gs.expansion_ledger.append("EXP-VALID")
        self.appender.validate_repair_authority("JOB-TARGET", "EXP-VALID")

    def test_validate_repair_authority_accepts_none_expansion(self) -> None:
        self.appender.validate_repair_authority("JOB-TARGET", None)

    def test_create_next_gate_revision(self) -> None:
        record = self.appender.create_next_gate_revision(
            target_job_id="JOB-TARGET",
            revision=1,
            repair_job_id="JOB-REPAIR",
            finding_id="FIND-1",
            evidence_refs=[],
        )
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["history_id"], stable_id("RGH", "JOB-TARGET", "1")[:4] + stable_id("RGH", "JOB-TARGET", "1")[4:].upper())


# ===========================================================================
# Task 8.5 Tests: Target accepter
# ===========================================================================

class TargetAccepterTest(unittest.TestCase):
    """Test TargetAccepter accepting target with history preservation."""

    def setUp(self) -> None:
        self.gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(self.gs, _minimal_job_def("JOB-TARGET", role="target"))
        add_job_to_graph(self.gs, _minimal_job_def("JOB-VERIFIER", role="verifier"))
        add_repair_gate(self.gs, _minimal_repair_gate(
            target_job_id="JOB-TARGET", revision=1
        ))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            target_job_id="JOB-TARGET",
            verifier_job_id="JOB-VERIFIER",
        ))
        self.accepter = TargetAccepter(self.gs)

    def test_accept_target_success(self) -> None:
        record = self.accepter.accept_target(
            target_job_id="JOB-TARGET",
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="pass",
            evidence_refs=["run://test/evidence/1"],
        )
        self.assertEqual(record["target_job_id"], "JOB-TARGET")
        self.assertEqual(record["verdict"], "pass")
        self.assertTrue(record["history_preserved"])

    def test_accept_target_rejects_non_pass(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.accepter.accept_target(
                target_job_id="JOB-TARGET",
                assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
                verdict="fail",
            )
        self.assertIn("pass", str(ctx.exception))

    def test_validate_current_repair_rejects_missing_assignment(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.accepter.validate_current_repair("JOB-TARGET", "VASS-MISSING")
        self.assertIn("not found", str(ctx.exception))

    def test_validate_current_repair_rejects_wrong_target(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-OTHER", role="target"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            assignment_id="VASS-OTHER",
            target_job_id="JOB-OTHER",
            verifier_job_id="JOB-VERIFIER",
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.accepter.validate_current_repair("JOB-TARGET", "VASS-OTHER")
        self.assertIn("not JOB-TARGET", str(ctx.exception))

    def test_validate_current_repair_rejects_no_history(self) -> None:
        add_job_to_graph(self.gs, _minimal_job_def("JOB-NOHIST", role="target"))
        add_verifier_assignment(self.gs, _minimal_verifier_assignment(
            assignment_id="VASS-NOHIST",
            target_job_id="JOB-NOHIST",
            verifier_job_id="JOB-VERIFIER",
        ))
        with self.assertRaises(OrchestratorError) as ctx:
            self.accepter.validate_current_repair("JOB-NOHIST", "VASS-NOHIST")
        self.assertIn("no repair history", str(ctx.exception))

    def test_preserve_history(self) -> None:
        add_repair_gate(self.gs, _minimal_repair_gate(
            history_id="RGH-2",
            target_job_id="JOB-TARGET",
            revision=2,
        ))
        result = self.accepter.preserve_history("JOB-TARGET")
        self.assertEqual(result["repair_gate_count"], 2)
        self.assertEqual(result["verifier_assignment_count"], 1)
        self.assertIn("RGH-AAAAAAAAAAAAAAAAAAAA", result["history_ids"])
        self.assertIn("RGH-2", result["history_ids"])


# ===========================================================================
# Duplicate condition names across targets
# ===========================================================================

class DuplicateConditionNamesTest(unittest.TestCase):
    """Test that duplicate condition names across different targets are allowed
    but must be distinct per target."""

    def test_duplicate_condition_names_across_targets(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T1", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-T2", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V1", role="verifier"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V2", role="verifier"))
        binder = VerifierAuthorityBinder(gs)

        r1 = binder.bind_verifier_authority(
            assignment_id="VASS-T1",
            target_job_id="JOB-T1",
            target_gate_revision=1,
            verifier_job_id="JOB-V1",
            run_id="run-1",
            cycle_id=_valid_id(),
            condition_id="COND-SHARED",
            graph_generation=1,
        )
        r2 = binder.bind_verifier_authority(
            assignment_id="VASS-T2",
            target_job_id="JOB-T2",
            target_gate_revision=1,
            verifier_job_id="JOB-V2",
            run_id="run-1",
            cycle_id=_valid_id(),
            condition_id="COND-SHARED",
            graph_generation=1,
        )
        self.assertEqual(gs._verifier_authority_bindings["VASS-T1"]["condition_id"], "COND-SHARED")
        self.assertEqual(gs._verifier_authority_bindings["VASS-T2"]["condition_id"], "COND-SHARED")
        self.assertEqual(len(gs._verifier_assignments), 2)


# ===========================================================================
# Multiple repair rounds
# ===========================================================================

class MultipleRepairRoundsTest(unittest.TestCase):
    """Test multiple sequential repair rounds on the same target."""

    def test_multiple_repair_rounds_increment_revision(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R1", role="repair"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R2", role="repair"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R3", role="repair"))
        appender = RepairRoundAppender(gs)

        g1 = appender.append_repair_round(
            target_job_id="JOB-T",
            repair_job_id="JOB-R1",
            finding_id="FIND-1",
        )
        g2 = appender.append_repair_round(
            target_job_id="JOB-T",
            repair_job_id="JOB-R2",
            finding_id="FIND-2",
        )
        g3 = appender.append_repair_round(
            target_job_id="JOB-T",
            repair_job_id="JOB-R3",
            finding_id="FIND-3",
        )
        self.assertEqual(g1["revision"], 1)
        self.assertEqual(g2["revision"], 2)
        self.assertEqual(g3["revision"], 3)
        history = get_repair_gate_history_for_target(gs, "JOB-T")
        self.assertEqual(len(history), 3)


# ===========================================================================
# Delayed old Verifiers
# ===========================================================================

class DelayedOldVerifierTest(unittest.TestCase):
    """Test that results from old (superseded) verifier assignments are rejected
    when a newer assignment exists."""

    def test_reject_result_from_old_assignment_after_new_gate(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V1", role="verifier"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V2", role="verifier"))
        add_repair_gate(gs, _minimal_repair_gate(
            target_job_id="JOB-T", revision=1
        ))
        add_repair_gate(gs, _minimal_repair_gate(
            history_id="RGH-2",
            target_job_id="JOB-T",
            revision=2,
        ))
        add_verifier_assignment(gs, _minimal_verifier_assignment(
            assignment_id="VASS-OLD",
            target_job_id="JOB-T",
            verifier_job_id="JOB-V1",
        ))
        add_verifier_assignment(gs, _minimal_verifier_assignment(
            assignment_id="VASS-NEW",
            target_job_id="JOB-T",
            verifier_job_id="JOB-V2",
        ))
        applier = VerificationResultApplier(gs)

        with self.assertRaises(OrchestratorError) as ctx:
            applier.apply_verification_result(
                assignment_id="VASS-OLD",
                verdict="pass",
            )
        self.assertIn("stale revision", str(ctx.exception))


# ===========================================================================
# Failed integration gates
# ===========================================================================

class FailedIntegrationGateTest(unittest.TestCase):
    """Test handling of failed integration gate verification results."""

    def test_fail_verdict_on_integration_gate(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V", role="verifier"))
        add_verifier_assignment(gs, _minimal_verifier_assignment(
            target_job_id="JOB-T",
            verifier_job_id="JOB-V",
        ))
        tracker = VerdictTracker(gs)

        tracker.record_execution_completion(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            completed_at="2026-01-15T11:00:00Z",
        )
        record = tracker.record_target_verdict(
            assignment_id="VASS-AAAAAAAAAAAAAAAAAAAA",
            verdict="fail",
            evidence_refs=["run://test/evidence/fail-1"],
        )
        self.assertEqual(record["verdict"], "fail")
        self.assertIn("fail-1", record["evidence_refs"][0])

        result = tracker.get_target_verdict("VASS-AAAAAAAAAAAAAAAAAAAA")
        self.assertIsNotNone(result)
        self.assertEqual(result["verdict"], "fail")


# ===========================================================================
# Transition to accepted completion
# ===========================================================================

class TransitionToAcceptedCompletionTest(unittest.TestCase):
    """Test the full transition from repair rounds to accepted completion."""

    def test_full_repair_to_acceptance_flow(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V", role="verifier"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R", role="repair"))
        add_repair_gate(gs, _minimal_repair_gate(
            target_job_id="JOB-T", revision=1
        ))
        add_verifier_assignment(gs, _minimal_verifier_assignment(
            target_job_id="JOB-T",
            verifier_job_id="JOB-V",
        ))

        appender = RepairRoundAppender(gs)
        g2 = appender.append_repair_round(
            target_job_id="JOB-T",
            repair_job_id="JOB-R",
            finding_id="FIND-2",
        )
        self.assertEqual(g2["revision"], 2)

        add_verifier_assignment(gs, _minimal_verifier_assignment(
            assignment_id="VASS-R2",
            target_job_id="JOB-T",
            verifier_job_id="JOB-V",
        ))

        accepter = TargetAccepter(gs)
        record = accepter.accept_target(
            target_job_id="JOB-T",
            assignment_id="VASS-R2",
            verdict="pass",
            evidence_refs=["run://test/evidence/accept-1"],
        )
        self.assertTrue(record["history_preserved"])
        history = get_repair_gate_history_for_target(gs, "JOB-T")
        self.assertEqual(len(history), 2)


# ===========================================================================
# History preservation
# ===========================================================================

class HistoryPreservationTest(unittest.TestCase):
    """Test that all earlier claims, findings, repairs, and results are preserved."""

    def test_history_preserved_after_acceptance(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-V", role="verifier"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R", role="repair"))
        for i in range(1, 4):
            add_repair_gate(gs, _minimal_repair_gate(
                history_id=f"RGH-{i}",
                target_job_id="JOB-T",
                revision=i,
                repair_job_id="JOB-R",
            ))
        add_verifier_assignment(gs, _minimal_verifier_assignment(
            assignment_id="VASS-FINAL",
            target_job_id="JOB-T",
            verifier_job_id="JOB-V",
        ))
        accepter = TargetAccepter(gs)
        history = accepter.preserve_history("JOB-T")
        self.assertEqual(history["repair_gate_count"], 3)
        self.assertEqual(len(history["history_ids"]), 3)

    def test_all_repair_records_stored(self) -> None:
        gs = GraphState(envelope=_minimal_envelope())
        add_job_to_graph(gs, _minimal_job_def("JOB-T", role="target"))
        add_job_to_graph(gs, _minimal_job_def("JOB-R", role="repair"))
        appender = RepairRoundAppender(gs)
        for i in range(1, 6):
            appender.append_repair_round(
                target_job_id="JOB-T",
                repair_job_id="JOB-R",
                finding_id=f"FIND-{i}",
            )
        history = get_repair_gate_history_for_target(gs, "JOB-T")
        self.assertEqual(len(history), 5)
        revisions = [r["revision"] for r in history]
        self.assertEqual(revisions, [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
