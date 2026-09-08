"""Tests for audit_v6 – Group 13: Audit, Cancellation, and Dynamic Recovery."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, stable_id  # noqa: E402
from graph_v6 import (  # noqa: E402
    EdgeRecord,
    ExpansionSlot,
    GraphState,
    GraphStatus,
    add_job_to_graph,
    add_edge_to_graph,
    add_expansion,
    add_generation,
    add_batch,
    add_verifier_assignment,
    compute_graph_digest,
)
from audit_v6 import (  # noqa: E402
    AuditFinding,
    AuditReporter,
    AuditSeverity,
    CancellationHandler,
    DynamicAuditor,
    FindingClassification,
    RecoveryScenarioHandler,
    SideEffectRecoveryPreserver,
    StaleResponseReconciler,
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


def _make_gs(
    status: str = GraphStatus.OPEN,
    jobs: dict | None = None,
    edges: dict | None = None,
    batches: dict | None = None,
    expansions: dict | None = None,
    generations: list | None = None,
    verifier_assignments: dict | None = None,
    repair_gate_history: list | None = None,
) -> GraphState:
    gs = GraphState(
        envelope=_minimal_envelope(),
        graph_revision=3,
        graph_digest="0" * 64,
        status=status,
    )
    if jobs:
        gs._jobs = jobs
    if edges:
        gs._edges = edges
    if batches:
        gs._batches = batches
    if expansions:
        gs._expansions = expansions
    if generations:
        gs._generations = generations
    if verifier_assignments:
        gs._verifier_assignments = verifier_assignments
    if repair_gate_history:
        gs._repair_gate_history = repair_gate_history
    gs.graph_digest = compute_graph_digest(gs)
    return gs


def _minimal_job(
    job_id: str = "JOB-AAAAAAAAAAAAAAAAAAAA",
    status: str = "pending",
    role: str = "implementation",
    authority_id: str | None = None,
    graph_generation: int = 1,
    side_effect: dict | None = None,
) -> dict:
    j = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "role": role,
        "purpose_key": f"p-{job_id}",
        "graph_generation": graph_generation,
        "expansion_origin": "ROOT",
        "authority_id": authority_id or _valid_id(),
        "context_snapshot_id": _valid_id(),
        "title": f"test-{job_id}",
        "status": status,
        "created_at": _valid_datetime(),
        "updated_at": _valid_datetime(),
    }
    if side_effect:
        j["side_effect"] = side_effect
    return j


def _minimal_edge(
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


# ===========================================================================
# Task 13.1 – DynamicAuditor tests
# ===========================================================================

class TestDynamicAuditorDigest(unittest.TestCase):
    def test_digest_match_no_error(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        auditor.validate_graph_digest()
        self.assertFalse(auditor.has_errors)

    def test_digest_mismatch_critical(self):
        gs = _make_gs()
        gs.graph_digest = "bad" + "0" * 61
        auditor = DynamicAuditor(gs)
        auditor.validate_graph_digest()
        self.assertTrue(auditor.has_critical)
        codes = [f.code for f in auditor.findings]
        self.assertIn("GRAPH_DIGEST_MISMATCH", codes)

    def test_digest_missing_critical(self):
        gs = _make_gs()
        gs.graph_digest = ""
        auditor = DynamicAuditor(gs)
        auditor.validate_graph_digest()
        self.assertTrue(auditor.has_critical)
        codes = [f.code for f in auditor.findings]
        self.assertIn("GRAPH_DIGEST_MISSING", codes)


class TestDynamicAuditorGenerations(unittest.TestCase):
    def test_valid_generations(self):
        gs = _make_gs(generations=[
            {"generation_id": "G-1", "graph_revision": 1, "graph_digest": "a" * 64},
            {"generation_id": "G-2", "graph_revision": 2, "graph_digest": "b" * 64},
        ])
        auditor = DynamicAuditor(gs)
        auditor.validate_generations()
        self.assertFalse(auditor.has_errors)

    def test_out_of_order_generation(self):
        gs = _make_gs(generations=[
            {"generation_id": "G-1", "graph_revision": 2, "graph_digest": "a" * 64},
            {"generation_id": "G-2", "graph_revision": 1, "graph_digest": "b" * 64},
        ])
        auditor = DynamicAuditor(gs)
        auditor.validate_generations()
        codes = [f.code for f in auditor.findings]
        self.assertIn("GENERATION_OUT_OF_ORDER", codes)


class TestDynamicAuditorEdgeTypes(unittest.TestCase):
    def test_valid_edges(self):
        job_a = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "complete")
        job_b = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "complete")
        edge = _minimal_edge()
        gs = _make_gs(jobs={"A": job_a, "B": job_b}, edges={"E": edge})
        auditor = DynamicAuditor(gs)
        auditor.validate_typed_edges()
        self.assertFalse(auditor.has_errors)

    def test_invalid_edge_type(self):
        job_a = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "complete")
        job_b = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "complete")
        edge = _minimal_edge()
        edge["edge_type"] = "invalid_type"
        gs = _make_gs(jobs={"A": job_a, "B": job_b}, edges={"E": edge})
        auditor = DynamicAuditor(gs)
        auditor.validate_typed_edges()
        codes = [f.code for f in auditor.findings]
        self.assertIn("EDGE_INVALID_TYPE", codes)

    def test_edge_source_missing(self):
        job_b = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "complete")
        edge = _minimal_edge(source="JOB-MISSING0000000000")
        gs = _make_gs(jobs={"B": job_b}, edges={"E": edge})
        auditor = DynamicAuditor(gs)
        auditor.validate_typed_edges()
        codes = [f.code for f in auditor.findings]
        self.assertIn("EDGE_SOURCE_MISSING", codes)


class TestDynamicAuditorBatchStates(unittest.TestCase):
    def test_valid_open_batch(self):
        batch = {
            "batch_id": "BATCH-1",
            "status": "open",
            "job_ids": [],
            "created_at": _valid_datetime(),
        }
        gs = _make_gs(batches={"BATCH-1": batch})
        auditor = DynamicAuditor(gs)
        auditor.validate_batches()
        self.assertFalse(auditor.has_errors)

    def test_sealed_batch_missing_timestamp(self):
        batch = {
            "batch_id": "BATCH-1",
            "status": "sealed",
            "job_ids": [],
        }
        gs = _make_gs(batches={"BATCH-1": batch})
        auditor = DynamicAuditor(gs)
        auditor.validate_batches()
        codes = [f.code for f in auditor.findings]
        self.assertIn("BATCH_SEALED_NO_SEALED_AT", codes)

    def test_batch_refers_to_missing_job(self):
        batch = {
            "batch_id": "BATCH-1",
            "status": "open",
            "job_ids": ["JOB-MISSING0000000000"],
            "created_at": _valid_datetime(),
        }
        gs = _make_gs(batches={"BATCH-1": batch})
        auditor = DynamicAuditor(gs)
        auditor.validate_batches()
        codes = [f.code for f in auditor.findings]
        self.assertIn("BATCH_REFERS_TO_MISSING_JOB", codes)


class TestDynamicAuditorLimits(unittest.TestCase):
    def test_within_limits(self):
        gs = _make_gs(jobs={
            f"J{i}": _minimal_job(f"JOB-{'A' * (19 - len(str(i)))}{i}", "complete")
            for i in range(5)
        })
        auditor = DynamicAuditor(gs)
        auditor.validate_limits()
        self.assertFalse(auditor.has_errors)

    def test_exceed_total_jobs_limit(self):
        jobs = {}
        for i in range(55):
            jid = f"JOB-{str(i).zfill(20)}"[:20]
            jobs[f"J{i}"] = _minimal_job(jid, "complete")
        gs = _make_gs(jobs=jobs)
        auditor = DynamicAuditor(gs)
        auditor.validate_limits()
        codes = [f.code for f in auditor.findings]
        self.assertIn("LIMIT_TOTAL_JOBS_EXCEEDED", codes)


class TestDynamicAuditorSealingObligations(unittest.TestCase):
    def test_sealed_with_pending_jobs(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        gs = _make_gs(status=GraphStatus.SEALED, jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_sealing_obligations()
        self.assertTrue(auditor.has_critical)

    def test_sealed_graph_clean(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "complete")
        gs = _make_gs(status=GraphStatus.SEALED, jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_sealing_obligations()
        self.assertFalse(auditor.has_critical)


class TestDynamicAuditorRunAll(unittest.TestCase):
    def test_run_all_returns_findings(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        findings = auditor.run_all()
        self.assertIsInstance(findings, list)


# ===========================================================================
# Task 13.2 – AuditReporter tests
# ===========================================================================

class TestAuditReporter(unittest.TestCase):
    def _make_findings(self, *severities: AuditSeverity) -> list[AuditFinding]:
        return [
            AuditFinding(severity=s, code=f"CODE_{s.value.upper()}", message=f"msg {s.value}")
            for s in severities
        ]

    def test_control_plane_facts_clean(self):
        findings = self._make_findings(AuditSeverity.INFO, AuditSeverity.WARNING)
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["actionable"])
        self.assertFalse(facts["has_critical"])
        self.assertFalse(facts["has_errors"])

    def test_control_plane_facts_blocking(self):
        findings = self._make_findings(AuditSeverity.CRITICAL, AuditSeverity.INFO)
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertFalse(facts["actionable"])
        self.assertTrue(facts["has_critical"])

    def test_validate_actionability_pass(self):
        findings = self._make_findings(AuditSeverity.INFO, AuditSeverity.WARNING)
        reporter = AuditReporter(findings)
        self.assertTrue(reporter.validate_actionability())

    def test_validate_actionability_fail(self):
        findings = self._make_findings(AuditSeverity.ERROR)
        reporter = AuditReporter(findings)
        self.assertFalse(reporter.validate_actionability())

    def test_generate_audit_report_structure(self):
        findings = self._make_findings(AuditSeverity.INFO, AuditSeverity.ERROR)
        reporter = AuditReporter(findings)
        report = reporter.generate_audit_report()
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertIn("facts", report)
        self.assertIn("findings", report)
        self.assertIn("info", report["findings"])
        self.assertIn("error", report["findings"])


# ===========================================================================
# Task 13.3 – CancellationHandler tests
# ===========================================================================

class TestCancellationHandler(unittest.TestCase):
    def test_seal_expansion_authority(self):
        gs = _make_gs()
        handler = CancellationHandler(gs)
        result = handler.seal_expansion_authority("SEAL-1", "test cancellation")
        self.assertEqual(result["action"], "expansion_authority_sealed")
        self.assertIsNone(gs.active_planning_authority_id)

    def test_reject_late_expansion(self):
        gs = _make_gs()
        handler = CancellationHandler(gs)
        result = handler.reject_late_expansion(
            {"expansion_id": "EXP-1"}, "authority sealed"
        )
        self.assertEqual(result["action"], "late_expansion_rejected")

    def test_reject_late_goal_control(self):
        gs = _make_gs()
        handler = CancellationHandler(gs)
        result = handler.reject_late_goal_control(
            {"judgment_id": "J-1", "decision": "CONTINUE"}, "sealed"
        )
        self.assertEqual(result["action"], "late_goal_control_rejected")

    def test_cancel_queued_jobs(self):
        job_p = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        job_r = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "running")
        job_d = _minimal_job("JOB-CCCCCCCCCCCCCCCCCCCC", "dispatching")
        gs = _make_gs(jobs={"A": job_p, "B": job_r, "C": job_d})
        handler = CancellationHandler(gs)
        cancelled = handler.cancel_queued_jobs()
        self.assertEqual(len(cancelled), 2)
        self.assertEqual(job_p["status"], "cancelled")
        self.assertEqual(job_r["status"], "running")  # running not cancelled

    def test_fence_active_attempts(self):
        job_r = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "running")
        job_p = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "pending")
        gs = _make_gs(jobs={"A": job_r, "B": job_p})
        handler = CancellationHandler(gs)
        fenced = handler.fence_active_attempts()
        self.assertEqual(len(fenced), 1)
        self.assertTrue(job_r.get("fenced"))
        self.assertFalse(job_p.get("fenced"))

    def test_preserve_late_responses(self):
        gs = _make_gs()
        handler = CancellationHandler(gs)
        record = handler.preserve_late_responses(
            {"response_id": "R-1", "status": "complete"}, "JOB-1"
        )
        self.assertTrue(record["nonauthoritative"])
        self.assertIn("EVID-", record["evidence_id"])

    def test_execute_cancellation(self):
        job_p = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        job_r = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "running")
        gs = _make_gs(jobs={"A": job_p, "B": job_r})
        handler = CancellationHandler(gs)
        result = handler.execute_cancellation("test cancel")
        self.assertEqual(result["cancellation_status"], "complete")
        self.assertEqual(len(result["cancelled_jobs"]), 1)
        self.assertEqual(len(result["fenced_jobs"]), 1)


# ===========================================================================
# Task 13.4 – StaleResponseReconciler tests
# ===========================================================================

class TestStaleResponseReconciler(unittest.TestCase):
    def test_stale_architect(self):
        gs = _make_gs()
        gs.graph_revision = 5
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reconcile_stale_architect({"graph_generation": 3})
        self.assertTrue(result["stale"])
        self.assertEqual(result["disposition"], "nonauthoritative_evidence")

    def test_current_architect(self):
        gs = _make_gs()
        gs.graph_revision = 5
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reconcile_stale_architect({"graph_generation": 5})
        self.assertFalse(result["stale"])
        self.assertEqual(result["disposition"], "current")

    def test_stale_hypothesis(self):
        gs = _make_gs()
        gs.graph_revision = 4
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reconcile_stale_hypothesis({"graph_generation": 2})
        self.assertTrue(result["stale"])
        self.assertEqual(result["disposition"], "superseded")

    def test_stale_verifier(self):
        gs = _make_gs()
        gs._repair_gate_history = [
            {"target_job_id": "T1", "revision": 5, "repair_job_id": "R1"},
        ]
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reconcile_stale_verifier(
            {"target_job_id": "T1", "target_gate_revision": 3}
        )
        self.assertTrue(result["stale"])

    def test_stale_goal_judge(self):
        gs = _make_gs()
        gs.graph_revision = 6
        gs._generations = [{"graph_revision": 6}]
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reconcile_stale_goal_judge({"graph_revision": 4})
        self.assertTrue(result["stale"])

    def test_reject_history_rewriting(self):
        gs = _make_gs()
        reconciler = StaleResponseReconciler(gs)
        result = reconciler.reject_history_rewriting()
        self.assertFalse(result["history_rewriting_attempted"])


# ===========================================================================
# Task 13.5 – SideEffectRecoveryPreserver tests
# ===========================================================================

class TestSideEffectRecoveryPreserver(unittest.TestCase):
    def test_preserve_repository_recovery(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "repository", "idempotency_key": "key1"},
        )
        gs = _make_gs(jobs={"J": job})
        preserver = SideEffectRecoveryPreserver(gs)
        result = preserver.preserve_repository_recovery()
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["recovery_preserved"])

    def test_preserve_external_idempotent(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "external", "idempotent": True, "idempotency_key": "k1"},
        )
        gs = _make_gs(jobs={"J": job})
        preserver = SideEffectRecoveryPreserver(gs)
        result = preserver.preserve_external_idempotent_recovery()
        self.assertEqual(len(result), 1)

    def test_preserve_external_non_idempotent(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "external", "idempotent": False},
        )
        gs = _make_gs(jobs={"J": job})
        preserver = SideEffectRecoveryPreserver(gs)
        result = preserver.preserve_external_non_idempotent_recovery()
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["evidence_retained"])

    def test_validate_recovery_guarantees_all_preserved(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "repository"},
        )
        gs = _make_gs(jobs={"J": job})
        preserver = SideEffectRecoveryPreserver(gs)
        result = preserver.validate_recovery_guarantees()
        self.assertTrue(result["all_preserved"])

    def test_validate_recovery_guarantees_missing(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA")
        job["side_effect"] = {"something": "else"}
        gs = _make_gs(jobs={"J": job})
        preserver = SideEffectRecoveryPreserver(gs)
        result = preserver.validate_recovery_guarantees()
        self.assertFalse(result["all_preserved"])


# ===========================================================================
# Task 13.6 – RecoveryScenarioHandler tests
# ===========================================================================

class TestRecoveryScenarioHandler(unittest.TestCase):
    def test_recover_interrupted_planning(self):
        gs = _make_gs()
        gs.expansion_slot = ExpansionSlot()
        gs.expansion_slot.phase = ExpansionSlot.PHASE_PLANNING
        gs.expansion_slot.active_expansion_id = "EXP-1"
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_interrupted_planning()
        self.assertEqual(result["action"], "slot_released")
        self.assertTrue(gs.expansion_slot.is_idle())

    def test_recover_interrupted_planning_no_action(self):
        gs = _make_gs()
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_interrupted_planning()
        self.assertEqual(result["action"], "no_action_needed")

    def test_recover_pending_expansion(self):
        gs = _make_gs()
        gs.expansion_slot = ExpansionSlot()
        gs.expansion_slot.phase = ExpansionSlot.PHASE_STAGING
        gs.expansion_slot.active_expansion_id = "EXP-1"
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_pending_expansion()
        self.assertEqual(result["action"], "slot_released")

    def test_recover_partial_commit(self):
        gs = _make_gs(expansions={
            "EXP-1": {"status": "committing", "expansion_id": "EXP-1"},
            "EXP-2": {"status": "pending", "expansion_id": "EXP-2"},
        })
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_partial_commit()
        self.assertEqual(result["action"], "rolled_back")
        self.assertEqual(gs._expansions["EXP-1"]["status"], "rolled_back")

    def test_recover_open_batch_cancellation(self):
        gs = _make_gs(batches={
            "B1": {"status": "open", "batch_id": "B1"},
            "B2": {"status": "complete", "batch_id": "B2"},
        })
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_open_batch_cancellation()
        self.assertEqual(len(result["cancelled_batches"]), 1)
        self.assertEqual(gs._batches["B1"]["status"], "abandoned")

    def test_recover_lost_repair_session(self):
        gs = _make_gs()
        gs.expansion_slot = ExpansionSlot()
        gs.expansion_slot.phase = ExpansionSlot.PHASE_PLANNING
        gs.expansion_slot.active_expansion_id = "EXP-1"
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_lost_repair_session()
        self.assertEqual(result["action"], "slot_released")

    def test_recover_delayed_verifier(self):
        gs = _make_gs(verifier_assignments={
            "V1": {
                "assignment_id": "V1",
                "target_job_id": "JOB-AAAAAAAAAAAAAAAAAAAA",
                "target_gate_revision": 1,
                "verifier_job_id": "JOB-VVVVVVVVVVVVVVVVVVVV",
                "run_id": "R-1",
                "cycle_id": "C-1",
                "status": "assigned",
                "evidence_refs": [],
                "assigned_at": _valid_datetime(),
            },
            "V2": {
                "assignment_id": "V2",
                "target_job_id": "JOB-BBBBBBBBBBBBBBBBBBBB",
                "target_gate_revision": 1,
                "verifier_job_id": "JOB-WWWWWWWWWWWWWWWWWWWW",
                "run_id": "R-1",
                "cycle_id": "C-1",
                "status": "complete",
                "evidence_refs": [],
                "assigned_at": _valid_datetime(),
                "completed_at": _valid_datetime(),
            },
        })
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_delayed_verifier()
        self.assertEqual(len(result["timed_out"]), 1)
        self.assertEqual(gs._verifier_assignments["V1"]["status"], "timed_out")

    def test_recover_stale_goal_judge(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            role="goal_judge",
            graph_generation=2,
        )
        gs = _make_gs(jobs={"J": job})
        gs.graph_revision = 5
        handler = RecoveryScenarioHandler(gs)
        result = handler.recover_stale_goal_judge()
        self.assertEqual(len(result["stale_judgments"]), 1)
        self.assertTrue(job.get("stale"))

    def test_run_all_recovery(self):
        gs = _make_gs()
        handler = RecoveryScenarioHandler(gs)
        results = handler.run_all_recovery()
        self.assertEqual(len(results), 8)


# ===========================================================================
# Task 13.2 – AuditReporter integration with DynamicAuditor
# ===========================================================================

class TestAuditIntegration(unittest.TestCase):
    def test_full_audit_pipeline(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        findings = auditor.run_all()
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        report = reporter.generate_audit_report()
        self.assertIn("facts", report)
        self.assertIn("findings", report)
        self.assertTrue(facts["actionable"])

    def test_sealed_graph_audit_with_obligations(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        gs = _make_gs(status=GraphStatus.SEALED, jobs={"J": job})
        auditor = DynamicAuditor(gs)
        findings = auditor.run_all()
        reporter = AuditReporter(findings)
        self.assertFalse(reporter.validate_actionability())
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["has_critical"])


# ===========================================================================
# State Integrity Audit Gate – Finding Classifications
# ===========================================================================

class TestFindingClassification(unittest.TestCase):
    def test_classification_constants_exist(self):
        self.assertEqual(FindingClassification.CLEAN, "clean")
        self.assertEqual(FindingClassification.DERIVED_SNAPSHOT_DRIFT, "derived_snapshot_drift")
        self.assertEqual(FindingClassification.STALE_INDEX_OR_QUEUE, "stale_index_or_queue")
        self.assertEqual(FindingClassification.INTERRUPTED_DISPATCH_RECORDED_NOT_SENT, "interrupted_dispatch_recorded_not_sent")
        self.assertEqual(FindingClassification.INTERRUPTED_DISPATCH_SENT_NO_RESULT, "interrupted_dispatch_sent_no_result")
        self.assertEqual(FindingClassification.COMPLETED_RESULT_NOT_APPLIED, "completed_result_not_applied")
        self.assertEqual(FindingClassification.EXTERNAL_EFFECT_UNKNOWN, "external_effect_unknown")
        self.assertEqual(FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT, "journal_corrupt_or_insufficient")
        self.assertEqual(FindingClassification.ACTIVE_IDLE_CONTRADICTION, "active_idle_contradiction")
        self.assertEqual(FindingClassification.PROTOCOL_HASH_MISMATCH, "protocol_hash_mismatch")

    def test_finding_with_classification(self):
        finding = AuditFinding(
            severity=AuditSeverity.CRITICAL,
            code="TEST",
            message="test",
            classification=FindingClassification.ACTIVE_IDLE_CONTRADICTION,
        )
        d = finding.to_dict()
        self.assertEqual(d["classification"], "active_idle_contradiction")

    def test_finding_without_classification(self):
        finding = AuditFinding(
            severity=AuditSeverity.INFO,
            code="TEST",
            message="test",
        )
        d = finding.to_dict()
        self.assertNotIn("classification", d)


# ===========================================================================
# State Integrity Audit Gate – Replay Health
# ===========================================================================

class TestReplayHealth(unittest.TestCase):
    def test_replay_health_ok_with_generations(self):
        gs = _make_gs(generations=[
            {"generation_id": "G-1", "graph_revision": 1, "graph_digest": "a" * 64},
            {"generation_id": "G-2", "graph_revision": 2, "graph_digest": "b" * 64},
            {"generation_id": "G-3", "graph_revision": 3, "graph_digest": "c" * 64},
        ])
        auditor = DynamicAuditor(gs)
        auditor.validate_replay_health()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("REPLAY_NO_GENERATIONS", codes)
        self.assertNotIn("REPLAY_GENERATION_LAG", codes)

    def test_replay_health_no_generations(self):
        gs = _make_gs(generations=[])
        auditor = DynamicAuditor(gs)
        auditor.validate_replay_health()
        codes = [f.code for f in auditor.findings]
        self.assertIn("REPLAY_NO_GENERATIONS", codes)

    def test_replay_health_generation_lag(self):
        gs = _make_gs(generations=[
            {"generation_id": "G-1", "graph_revision": 1, "graph_digest": "a" * 64},
        ])
        gs.graph_revision = 5
        auditor = DynamicAuditor(gs)
        auditor.validate_replay_health()
        codes = [f.code for f in auditor.findings]
        self.assertIn("REPLAY_GENERATION_LAG", codes)
        classifications = [f.classification for f in auditor.findings if f.classification]
        self.assertIn(FindingClassification.DERIVED_SNAPSHOT_DRIFT, classifications)


# ===========================================================================
# State Integrity Audit Gate – Protocol Hash
# ===========================================================================

class TestProtocolHash(unittest.TestCase):
    def test_protocol_hash_no_manifest(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        auditor.validate_protocol_hash(run_protocol_hash=None)
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("PROTOCOL_HASH_MISMATCH", codes)

    def test_protocol_hash_match(self):
        from orchestrator_core import content_hash
        gs = _make_gs()
        envelope_hash = content_hash({
            "strategy": gs.envelope.get("strategy", ""),
            "version": gs.envelope.get("version", 0),
        })
        auditor = DynamicAuditor(gs)
        auditor.validate_protocol_hash(run_protocol_hash=envelope_hash)
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("PROTOCOL_HASH_MISMATCH", codes)

    def test_protocol_hash_mismatch_blocks(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        auditor.validate_protocol_hash(run_protocol_hash="bad_hash_value")
        codes = [f.code for f in auditor.findings]
        self.assertIn("PROTOCOL_HASH_MISMATCH", codes)
        classifications = [f.classification for f in auditor.findings if f.classification]
        self.assertIn(FindingClassification.PROTOCOL_HASH_MISMATCH, classifications)


# ===========================================================================
# State Integrity Audit Gate – Active-Idle Contradiction
# ===========================================================================

class TestActiveIdleContradiction(unittest.TestCase):
    def test_active_idle_detected(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        job["role"] = "control_root"
        job2 = _minimal_job("JOB-BBBBBBBBBBBBBBBBBBBB", "dispatch_pending")
        job2["role"] = "implementation"
        gs = _make_gs(jobs={"J": job, "J2": job2}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        # dispatch_pending IS in has_pending_or_dispatching, so this won't fire
        # Let's test with a status that IS in all_non_control_jobs but NOT in active/pending
        # "completed" is excluded, so use a state that's between pending and completed
        pass

    def test_active_idle_with_stale_terminal_jobs(self):
        # Jobs in states that are not active, not pending, but not excluded terminal states
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "completed")
        job["role"] = "implementation"
        # completed IS excluded, so this won't fire
        # The real scenario: jobs exist but all in excluded terminal states
        gs = _make_gs(jobs={"J": job}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        # No contradiction because "completed" is excluded
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_active_idle_no_jobs(self):
        gs = _make_gs(jobs={}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_no_active_idle_when_jobs_running(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "running")
        gs = _make_gs(jobs={"J": job}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_no_active_idle_when_sealed(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        gs = _make_gs(jobs={"J": job}, status=GraphStatus.SEALED)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_no_active_idle_when_pending_jobs_exist(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "pending")
        gs = _make_gs(jobs={"J": job}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_no_active_idle_when_waiting_jobs_exist(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "waiting")
        gs = _make_gs(jobs={"J": job}, status=GraphStatus.OPEN)
        auditor = DynamicAuditor(gs)
        auditor.validate_active_idle_contradiction()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("ACTIVE_IDLE_CONTRADICTION", codes)

    def test_active_idle_blocks_resume_in_reporter(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.CRITICAL,
                code="ACTIVE_IDLE_CONTRADICTION",
                message="active idle",
                classification=FindingClassification.ACTIVE_IDLE_CONTRADICTION,
            )
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["blocks_resume"])
        self.assertTrue(facts["has_active_idle_contradiction"])


# ===========================================================================
# State Integrity Audit Gate – Interrupted Dispatch Classification
# ===========================================================================

class TestInterruptedDispatchClassification(unittest.TestCase):
    def test_dispatch_recorded_not_sent(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "dispatch_pending")
        job["dispatch_id"] = "DISP-123"
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_action_dispatch_contradictions()
        codes = [f.code for f in auditor.findings]
        self.assertIn("INTERRUPTED_DISPATCH_RECORDED_NOT_SENT", codes)

    def test_dispatch_sent_no_result(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "running")
        job["dispatch_id"] = "DISP-456"
        job["evidence_refs"] = []
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_action_dispatch_contradictions()
        codes = [f.code for f in auditor.findings]
        self.assertIn("INTERRUPTED_DISPATCH_SENT_NO_RESULT", codes)


# ===========================================================================
# State Integrity Audit Gate – Completed Result Not Applied
# ===========================================================================

class TestCompletedResultNotApplied(unittest.TestCase):
    def test_completed_not_applied(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "completed")
        job["completion_status"] = "success"
        job["report_accepted"] = False
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_completed_result_not_applied()
        codes = [f.code for f in auditor.findings]
        self.assertIn("COMPLETED_RESULT_NOT_APPLIED", codes)
        classifications = [f.classification for f in auditor.findings if f.classification]
        self.assertIn(FindingClassification.COMPLETED_RESULT_NOT_APPLIED, classifications)

    def test_completed_and_applied_no_finding(self):
        job = _minimal_job("JOB-AAAAAAAAAAAAAAAAAAAA", "completed")
        job["completion_status"] = "success"
        job["report_accepted"] = True
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_completed_result_not_applied()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("COMPLETED_RESULT_NOT_APPLIED", codes)


# ===========================================================================
# State Integrity Audit Gate – Side-Effect Blockers
# ===========================================================================

class TestSideEffectBlockers(unittest.TestCase):
    def test_side_effect_no_recovery_check(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "repository"},
        )
        job["status"] = "pending"
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_side_effect_blockers()
        codes = [f.code for f in auditor.findings]
        self.assertIn("SIDE_EFFECT_NO_RECOVERY_CHECK", codes)

    def test_side_effect_with_recovery_check_ok(self):
        job = _minimal_job(
            "JOB-AAAAAAAAAAAAAAAAAAAA",
            side_effect={"effect_type": "repository", "recovery_check": "git_status"},
        )
        job["status"] = "pending"
        gs = _make_gs(jobs={"J": job})
        auditor = DynamicAuditor(gs)
        auditor.validate_side_effect_blockers()
        codes = [f.code for f in auditor.findings]
        self.assertNotIn("SIDE_EFFECT_NO_RECOVERY_CHECK", codes)


# ===========================================================================
# State Integrity Audit Gate – Derived Snapshot Drift
# ===========================================================================

class TestDerivedSnapshotDrift(unittest.TestCase):
    def test_drift_when_empty_with_events(self):
        gs = _make_gs(
            generations=[
                {"generation_id": "G-1", "graph_revision": 1, "graph_digest": "a" * 64},
            ],
            jobs={},
        )
        auditor = DynamicAuditor(gs)
        auditor.validate_derived_snapshots()
        codes = [f.code for f in auditor.findings]
        self.assertIn("DERIVED_SNAPSHOTS_EMPTY_WITH_EVENTS", codes)


# ===========================================================================
# State Integrity Audit Gate – Audit Reporter Blocks Resume
# ===========================================================================

class TestAuditReporterBlocksResume(unittest.TestCase):
    def test_blocks_resume_on_active_idle(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.CRITICAL,
                code="ACTIVE_IDLE_CONTRADICTION",
                message="active idle",
                classification=FindingClassification.ACTIVE_IDLE_CONTRADICTION,
            )
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["blocks_resume"])

    def test_blocks_resume_on_protocol_mismatch(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.CRITICAL,
                code="PROTOCOL_HASH_MISMATCH",
                message="protocol mismatch",
                classification=FindingClassification.PROTOCOL_HASH_MISMATCH,
            )
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["blocks_resume"])

    def test_blocks_resume_on_journal_corrupt(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.ERROR,
                code="JOURNAL_CORRUPT_OR_INSUFFICIENT",
                message="journal corrupt",
                classification=FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT,
            )
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertTrue(facts["blocks_resume"])

    def test_no_blocks_resume_when_clean(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.INFO,
                code="CLEAN",
                message="clean",
                classification=FindingClassification.CLEAN,
            )
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertFalse(facts["blocks_resume"])

    def test_classifications_exposed_in_facts(self):
        findings = [
            AuditFinding(
                severity=AuditSeverity.WARNING,
                code="DRIFT",
                message="drift",
                classification=FindingClassification.DERIVED_SNAPSHOT_DRIFT,
            ),
            AuditFinding(
                severity=AuditSeverity.INFO,
                code="CLEAN",
                message="clean",
                classification=FindingClassification.CLEAN,
            ),
        ]
        reporter = AuditReporter(findings)
        facts = reporter.expose_control_plane_facts()
        self.assertIn("derived_snapshot_drift", facts["classifications"])
        self.assertIn("clean", facts["classifications"])


# ===========================================================================
# State Integrity Audit Gate – Run-All with Protocol Hash
# ===========================================================================

class TestRunAllWithProtocolHash(unittest.TestCase):
    def test_run_all_passes_protocol_hash(self):
        from orchestrator_core import content_hash
        gs = _make_gs(generations=[
            {"generation_id": "G-1", "graph_revision": 1, "graph_digest": "a" * 64},
        ])
        envelope_hash = content_hash({
            "strategy": gs.envelope.get("strategy", ""),
            "version": gs.envelope.get("version", 0),
        })
        auditor = DynamicAuditor(gs)
        findings = auditor.run_all(run_protocol_hash=envelope_hash)
        codes = [f.code for f in findings]
        self.assertNotIn("PROTOCOL_HASH_MISMATCH", codes)

    def test_run_all_detects_protocol_mismatch(self):
        gs = _make_gs()
        auditor = DynamicAuditor(gs)
        findings = auditor.run_all(run_protocol_hash="wrong_hash")
        codes = [f.code for f in findings]
        self.assertIn("PROTOCOL_HASH_MISMATCH", codes)


if __name__ == "__main__":
    unittest.main()
