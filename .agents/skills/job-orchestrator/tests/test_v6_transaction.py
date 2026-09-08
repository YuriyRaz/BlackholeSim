"""Tests for v6 typed decision and expansion ingestion transactions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError  # noqa: E402
from transaction_v6 import (  # noqa: E402
    CorrectionGenerator,
    ExpansionIngester,
    ExpansionRetainer,
    GoalDecisionProcessor,
    ResponseNormalizer,
    ResultProcessor,
)


def _valid_id() -> str:
    return "T-ABCDEFGHIJKLMOPQRST"


def _valid_digest() -> str:
    return "a" * 64


def _valid_datetime() -> str:
    return "2026-01-15T10:30:00Z"


def _valid_evidence_ref() -> str:
    return "run://test/jobs/JOB123"


class ResponseNormalizationTest(unittest.TestCase):
    """Test ResponseNormalizer for each role type."""

    def setUp(self) -> None:
        self.normalizer = ResponseNormalizer()

    def test_normalize_execution_status_complete(self) -> None:
        result = self.normalizer.normalize_execution_status({
            "response_id": _valid_id(),
            "status": "complete",
        })
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["status"], "complete")
        self.assertIn("normalized_at", result)

    def test_normalize_execution_status_received(self) -> None:
        result = self.normalizer.normalize_execution_status({
            "response_id": _valid_id(),
            "status": "received",
        })
        self.assertEqual(result["status"], "received")

    def test_normalize_execution_status_invalid(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_execution_status({
                "response_id": _valid_id(),
                "status": "invalid_status",
            })
        self.assertIn("invalid execution status", str(ctx.exception))

    def test_normalize_goal_decision_goal_achieved(self) -> None:
        judgment = {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "GOAL_ACHIEVED",
            "evidence_refs": [_valid_evidence_ref()],
            "reason": "all gates passed",
            "recorded_at": _valid_datetime(),
        }
        result = self.normalizer.normalize_goal_decision(judgment)
        self.assertEqual(result["decision"], "GOAL_ACHIEVED")
        self.assertEqual(result["graph_revision"], 1)

    def test_normalize_goal_decision_continue(self) -> None:
        judgment = {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "CONTINUE",
            "evidence_refs": [],
            "reason": "more work needed",
            "recorded_at": _valid_datetime(),
        }
        result = self.normalizer.normalize_goal_decision(judgment)
        self.assertEqual(result["decision"], "CONTINUE")

    def test_normalize_goal_decision_invalid(self) -> None:
        judgment = {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "MAYBE",
            "evidence_refs": [],
            "reason": "unclear",
            "recorded_at": _valid_datetime(),
        }
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_goal_decision(judgment)
        self.assertIn("invalid goal decision", str(ctx.exception))

    def test_normalize_hypothesis_result_supported(self) -> None:
        result = self.normalizer.normalize_hypothesis_result({
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": _valid_id(),
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "supported",
            "evidence_refs": [_valid_evidence_ref()],
            "predicted_observations": [],
            "falsifying_observations": [],
            "primary_evidence": "test evidence",
            "confidence": "high",
            "reason": "evidence supports",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result["status"], "supported")

    def test_normalize_hypothesis_result_refuted(self) -> None:
        result = self.normalizer.normalize_hypothesis_result({
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": _valid_id(),
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "refuted",
            "evidence_refs": [_valid_evidence_ref()],
            "predicted_observations": [],
            "falsifying_observations": [],
            "primary_evidence": "test evidence",
            "confidence": "high",
            "reason": "contradicted by data",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result["status"], "refuted")

    def test_normalize_hypothesis_result_invalid(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_hypothesis_result({
                "schema_version": SCHEMA_VERSION,
                "hypothesis_result_id": _valid_id(),
                "finding_id": _valid_id(),
                "producer_job_id": _valid_id(),
                "cycle_id": _valid_id(),
                "status": "invalid",
                "evidence_refs": [],
                "reason": "test",
                "recorded_at": _valid_datetime(),
            })
        self.assertIn("invalid hypothesis status", str(ctx.exception))

    def test_normalize_synthesis_result(self) -> None:
        result = self.normalizer.normalize_synthesis_result({
            "schema_version": SCHEMA_VERSION,
            "synthesis_id": _valid_id(),
            "hypothesis_result_ids": [_valid_id()],
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "conclusion": "root_cause_identified",
            "evidence_refs": [_valid_evidence_ref()],
            "summary": "root cause found",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result["conclusion"], "root_cause_identified")

    def test_normalize_synthesis_result_invalid_conclusion(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_synthesis_result({
                "schema_version": SCHEMA_VERSION,
                "synthesis_id": _valid_id(),
                "hypothesis_result_ids": [_valid_id()],
                "producer_job_id": _valid_id(),
                "cycle_id": _valid_id(),
                "conclusion": "invalid_conclusion",
                "evidence_refs": [],
                "summary": "test",
                "recorded_at": _valid_datetime(),
            })
        self.assertIn("invalid synthesis conclusion", str(ctx.exception))

    def test_normalize_work_plan_direct_repair(self) -> None:
        result = self.normalizer.normalize_work_plan({
            "schema_version": SCHEMA_VERSION,
            "plan_id": _valid_id(),
            "plan_type": "direct_repair",
            "cycle_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "targets": [{"target_id": _valid_id(), "target_type": "finding"}],
            "created_at": _valid_datetime(),
        })
        self.assertEqual(result["plan_type"], "direct_repair")

    def test_normalize_work_plan_invalid_type(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_work_plan({
                "schema_version": SCHEMA_VERSION,
                "plan_id": _valid_id(),
                "plan_type": "invalid_plan",
                "cycle_id": _valid_id(),
                "producer_job_id": _valid_id(),
                "targets": [{"target_id": _valid_id(), "target_type": "finding"}],
                "created_at": _valid_datetime(),
            })
        self.assertIn("invalid work plan type", str(ctx.exception))

    def test_normalize_expansion(self) -> None:
        result = self.normalizer.normalize_expansion({
            "schema_version": SCHEMA_VERSION,
            "expansion_id": _valid_id(),
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
            "created_at": _valid_datetime(),
        })
        self.assertEqual(result["expansion_id"], _valid_id())

    def test_normalize_verification_passed(self) -> None:
        result = self.normalizer.normalize_verification({
            "status": "passed",
            "goal_gate_result_id": _valid_id(),
        })
        self.assertEqual(result["status"], "passed")

    def test_normalize_verification_invalid(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.normalizer.normalize_verification({"status": "maybe"})
        self.assertIn("invalid verification status", str(ctx.exception))


class ExpansionAcceptanceTest(unittest.TestCase):
    """Test ExpansionIngester authority and provenance binding."""

    def setUp(self) -> None:
        self.authority = {
            "authority_id": _valid_id(),
            "campaign_id": _valid_id(),
            "job_identity": _valid_id(),
            "role": "expander",
            "scope": {"expansion": True, "repair": False, "verification": False},
            "granted_at": _valid_datetime(),
            "expires_at": "2099-12-31T23:59:59Z",
        }
        self.ingester = ExpansionIngester(
            authority_store={self.authority["authority_id"]: self.authority}
        )

    def test_accept_expansion_valid(self) -> None:
        expansion = {
            "schema_version": SCHEMA_VERSION,
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
        }
        producer_job = {"job_id": _valid_id(), "cycle_id": _valid_id()}
        response_receipt = {"receipt_id": _valid_id()}
        graph_state = {"graph_revision": 1, "graph_digest": _valid_digest()}
        result = self.ingester.accept_expansion(
            expansion=expansion,
            current_authority_id=self.authority["authority_id"],
            producer_job=producer_job,
            response_receipt=response_receipt,
            graph_state=graph_state,
            source_artifact_digest=_valid_digest(),
            authority_scope={"expansion": True, "repair": False, "verification": False},
        )
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertIn("provenance", result)
        self.assertEqual(
            result["provenance"]["producer_job_id"], producer_job["job_id"]
        )

    def test_accept_expansion_no_authority(self) -> None:
        expansion = {"plan_id": _valid_id()}
        producer_job = {"job_id": _valid_id(), "cycle_id": _valid_id()}
        response_receipt = {"receipt_id": _valid_id()}
        graph_state = {"graph_revision": 1, "graph_digest": _valid_digest()}
        with self.assertRaises(OrchestratorError) as ctx:
            self.ingester.accept_expansion(
                expansion=expansion,
                current_authority_id="NONEXISTENT",
                producer_job=producer_job,
                response_receipt=response_receipt,
                graph_state=graph_state,
                source_artifact_digest=_valid_digest(),
                authority_scope={"expansion": True, "repair": False, "verification": False},
            )
        self.assertIn("not found", str(ctx.exception))

    def test_accept_expansion_no_expansion_scope(self) -> None:
        expansion = {"plan_id": _valid_id()}
        producer_job = {"job_id": _valid_id(), "cycle_id": _valid_id()}
        response_receipt = {"receipt_id": _valid_id()}
        graph_state = {"graph_revision": 1, "graph_digest": _valid_digest()}
        with self.assertRaises(OrchestratorError) as ctx:
            self.ingester.accept_expansion(
                expansion=expansion,
                current_authority_id=self.authority["authority_id"],
                producer_job=producer_job,
                response_receipt=response_receipt,
                graph_state=graph_state,
                source_artifact_digest=_valid_digest(),
                authority_scope={"expansion": False, "repair": False, "verification": False},
            )
        self.assertIn("expansion scope", str(ctx.exception))

    def test_bind_expansion_provenance(self) -> None:
        producer_job = {"job_id": _valid_id(), "cycle_id": _valid_id()}
        response_receipt = {"receipt_id": _valid_id()}
        graph_state = {"graph_revision": 3, "graph_digest": _valid_digest()}
        provenance = self.ingester.bind_expansion_provenance(
            producer_job=producer_job,
            response_receipt=response_receipt,
            graph_state=graph_state,
            source_artifact_digest=_valid_digest(),
            authority_id=self.authority["authority_id"],
            expansion={},
        )
        self.assertEqual(provenance["producer_job_id"], producer_job["job_id"])
        self.assertEqual(provenance["authority_id"], self.authority["authority_id"])
        self.assertEqual(provenance["graph_revision"], 3)
        self.assertIn("response_receipt_digest", provenance)
        self.assertIn("source_artifact_digest", provenance)


class ExpansionRetentionTest(unittest.TestCase):
    """Test ExpansionRetainer idempotency and conflict rejection."""

    def setUp(self) -> None:
        self.retainer = ExpansionRetainer()

    def test_retain_expansion(self) -> None:
        expansion = {
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
        }
        record = self.retainer.retain_expansion(expansion)
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)
        self.assertIn("expansion_id", record)
        self.assertIn("canonical_digest", record)
        self.assertEqual(record["plan_id"], expansion["plan_id"])
        self.assertEqual(record["campaign_id"], expansion["campaign_id"])

    def test_retain_expansion_idempotent(self) -> None:
        expansion = {
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
        }
        record1 = self.retainer.retain_expansion(expansion)
        record2 = self.retainer.retain_expansion(expansion)
        self.assertEqual(record1["expansion_id"], record2["expansion_id"])

    def test_reject_conflicting_reuse(self) -> None:
        expansion = {
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
        }
        record = self.retainer.retain_expansion(expansion)
        with self.assertRaises(OrchestratorError) as ctx:
            self.retainer.reject_conflicting_reuse(
                record["expansion_id"], "b" * 64
            )
        self.assertIn("conflicting identity reuse", str(ctx.exception))

    def test_reject_conflicting_reuse_matching_digest(self) -> None:
        expansion = {
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
        }
        record = self.retainer.retain_expansion(expansion)
        self.retainer.reject_conflicting_reuse(
            record["expansion_id"], record["canonical_digest"]
        )

    def test_make_idempotent_unknown_id(self) -> None:
        with self.assertRaises(OrchestratorError) as ctx:
            self.retainer.make_idempotent("NONEXISTENT")
        self.assertIn("not found", str(ctx.exception))


class GoalDecisionProcessingTest(unittest.TestCase):
    """Test GoalDecisionProcessor for each decision type."""

    def setUp(self) -> None:
        self.processor = GoalDecisionProcessor(
            current_judge_id=_valid_id(),
            current_graph_revision=1,
        )
        self.valid_judgment = {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "GOAL_ACHIEVED",
            "evidence_refs": [_valid_evidence_ref()],
            "reason": "all gates passed",
            "recorded_at": _valid_datetime(),
        }

    def test_process_goal_achieved(self) -> None:
        result = self.processor.process_goal_achieved(self.valid_judgment)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["decision"], "GOAL_ACHIEVED")

    def test_process_continue(self) -> None:
        judgment = {**self.valid_judgment, "decision": "CONTINUE"}
        result = self.processor.process_continue(judgment)
        self.assertFalse(result["sealed"])
        self.assertEqual(result["outcome"], "graph_open")
        self.assertEqual(result["decision"], "CONTINUE")

    def test_process_blocked(self) -> None:
        judgment = {**self.valid_judgment, "decision": "BLOCKED"}
        result = self.processor.process_blocked(judgment)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "blocked")

    def test_process_infeasible(self) -> None:
        judgment = {**self.valid_judgment, "decision": "BLOCKED"}
        result = self.processor.process_infeasible(judgment)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "infeasible")

    def test_process_blocked_no_progress(self) -> None:
        judgment = {**self.valid_judgment, "decision": "BLOCKED"}
        result = self.processor.process_blocked_no_progress(judgment)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "blocked_no_progress")

    def test_process_budget_exhausted(self) -> None:
        judgment = {**self.valid_judgment, "decision": "BLOCKED"}
        result = self.processor.process_budget_exhausted(judgment)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["outcome"], "budget_exhausted")

    def test_validate_goal_authority_wrong_judge(self) -> None:
        judgment = {**self.valid_judgment, "producer_job_id": "WRONG-JOB"}
        with self.assertRaises(OrchestratorError) as ctx:
            self.processor.validate_goal_authority(judgment)
        self.assertIn("does not match", str(ctx.exception))

    def test_validate_goal_authority_wrong_revision(self) -> None:
        judgment = {**self.valid_judgment, "graph_revision": 999}
        with self.assertRaises(OrchestratorError) as ctx:
            self.processor.validate_goal_authority(judgment)
        self.assertIn("does not match", str(ctx.exception))

    def test_validate_goal_authority_no_restriction(self) -> None:
        processor = GoalDecisionProcessor(
            current_judge_id=None,
            current_graph_revision=0,
        )
        processor.validate_goal_authority(self.valid_judgment)


class ResultProcessingTest(unittest.TestCase):
    """Test ResultProcessor for each result type with stable identities."""

    def setUp(self) -> None:
        self.processor = ResultProcessor()

    def test_process_hypothesis_result(self) -> None:
        result = self.processor.process_hypothesis_result({
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": _valid_id(),
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "supported",
            "evidence_refs": [_valid_evidence_ref()],
            "predicted_observations": [],
            "falsifying_observations": [],
            "primary_evidence": "test evidence",
            "confidence": "high",
            "reason": "evidence supports",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["status"], "supported")
        self.assertTrue(result["hypothesis_result_id"].startswith("HYPRES-"))

    def test_process_hypothesis_result_stable_identity(self) -> None:
        result1 = self.processor.process_hypothesis_result({
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": _valid_id(),
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "supported",
            "evidence_refs": [],
            "predicted_observations": [],
            "falsifying_observations": [],
            "primary_evidence": "test evidence",
            "confidence": "high",
            "reason": "test",
            "recorded_at": _valid_datetime(),
        })
        print("ID IS", result1["hypothesis_result_id"]); result2 = self.processor.process_hypothesis_result({
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": result1["hypothesis_result_id"],
            "finding_id": result1["finding_id"],
            "producer_job_id": result1["producer_job_id"],
            "cycle_id": result1["cycle_id"],
            "status": "supported",
            "evidence_refs": [],
            "predicted_observations": [],
            "falsifying_observations": [],
            "primary_evidence": "test evidence",
            "confidence": "high",
            "reason": "test",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result1["hypothesis_result_id"], result2["hypothesis_result_id"])

    def test_process_synthesis_result(self) -> None:
        result = self.processor.process_synthesis_result({
            "schema_version": SCHEMA_VERSION,
            "synthesis_id": _valid_id(),
            "hypothesis_result_ids": [_valid_id()],
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "conclusion": "root_cause_identified",
            "evidence_refs": [_valid_evidence_ref()],
            "summary": "root cause found",
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(result["conclusion"], "root_cause_identified")
        self.assertTrue(result["synthesis_id"].startswith("SYNRES-"))

    def test_process_work_plan(self) -> None:
        result = self.processor.process_work_plan({
            "schema_version": SCHEMA_VERSION,
            "plan_id": _valid_id(),
            "plan_type": "direct_repair",
            "cycle_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "targets": [{"target_id": _valid_id(), "target_type": "finding"}],
            "created_at": _valid_datetime(),
        })
        self.assertEqual(result["plan_type"], "direct_repair")
        self.assertTrue(result["plan_id"].startswith("WRKPLN-"))

    def test_process_finding(self) -> None:
        result = self.processor.process_finding({
            "schema_version": SCHEMA_VERSION,
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "producer_role": "verifier",
            "cycle_id": _valid_id(),
            "severity": "high",
            "confidence": 0.9,
            "evidence": [{"ref": _valid_evidence_ref(), "digest": _valid_digest()}],
            "description": "critical bug found",
            "created_at": _valid_datetime(),
        })
        self.assertTrue(result["disposition_id"].startswith("FNDISP-"))
        self.assertEqual(result["status"], "accepted_risk")
        self.assertEqual(result["finding_id"], _valid_id())

    def test_process_finding_append_only(self) -> None:
        self.processor.process_finding({
            "schema_version": SCHEMA_VERSION,
            "finding_id": "FINDING-A",
            "producer_job_id": _valid_id(),
            "producer_role": "verifier",
            "cycle_id": _valid_id(),
            "severity": "high",
            "confidence": 0.9,
            "evidence": [{"ref": _valid_evidence_ref(), "digest": _valid_digest()}],
            "description": "first finding",
            "created_at": _valid_datetime(),
        })
        self.processor.process_finding({
            "schema_version": SCHEMA_VERSION,
            "finding_id": "FINDING-B",
            "producer_job_id": _valid_id(),
            "producer_role": "verifier",
            "cycle_id": _valid_id(),
            "severity": "low",
            "confidence": 0.5,
            "evidence": [{"ref": _valid_evidence_ref(), "digest": _valid_digest()}],
            "description": "second finding",
            "created_at": _valid_datetime(),
        })
        self.assertEqual(len(self.processor._disposition_log), 2)

    def test_process_progress(self) -> None:
        result = self.processor.process_progress({
            "run_id": "2026-01-15T103000Z-test",
            "graph_revision": 1,
            "jobs_completed": 3,
            "jobs_total": 5,
        })
        self.assertTrue(result["progress_id"].startswith("PROG-"))
        self.assertEqual(result["jobs_completed"], 3)

    def test_process_review(self) -> None:
        result = self.processor.process_review({
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "approved",
        })
        self.assertTrue(result["review_id"].startswith("REVIEW-"))
        self.assertEqual(result["status"], "approved")


class CorrectionPromptGenerationTest(unittest.TestCase):
    """Test CorrectionGenerator for invalid decisions."""

    def setUp(self) -> None:
        self.generator = CorrectionGenerator()

    def test_generate_correction_prompt(self) -> None:
        prompt = self.generator.generate_correction_prompt(
            errors=["missing field: producer_job_id", "invalid status"],
            context="goal judgment",
        )
        self.assertIn("CORRECTION_REQUIRED", prompt)
        self.assertIn("missing field: producer_job_id", prompt)
        self.assertIn("invalid status", prompt)
        self.assertIn("goal judgment", prompt)
        self.assertIn("Do not repeat domain side effects", prompt)

    def test_generate_correction_prompt_no_context(self) -> None:
        prompt = self.generator.generate_correction_prompt(
            errors=["error 1"],
        )
        self.assertIn("CORRECTION_REQUIRED", prompt)
        self.assertNotIn("Context:", prompt)

    def test_validate_decision_format_valid(self) -> None:
        errors = self.generator.validate_decision_format({
            "schema_version": SCHEMA_VERSION,
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "recorded_at": _valid_datetime(),
        })
        self.assertEqual(errors, [])

    def test_validate_decision_format_missing_field(self) -> None:
        errors = self.generator.validate_decision_format({
            "schema_version": SCHEMA_VERSION,
        })
        self.assertTrue(any("producer_job_id" in e for e in errors))

    def test_validate_decision_format_wrong_version(self) -> None:
        errors = self.generator.validate_decision_format({
            "schema_version": 5,
            "producer_job_id": _valid_id(),
            "cycle_id": _valid_id(),
            "recorded_at": _valid_datetime(),
        })
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_validate_decision_format_not_dict(self) -> None:
        errors = self.generator.validate_decision_format("not a dict")
        self.assertEqual(len(errors), 1)
        self.assertIn("JSON object", errors[0])

    def test_validate_decision_authority_valid(self) -> None:
        errors = self.generator.validate_decision_authority(
            {"producer_job_id": _valid_id()},
            expected_producer=_valid_id(),
        )
        self.assertEqual(errors, [])

    def test_validate_decision_authority_unauthorized(self) -> None:
        errors = self.generator.validate_decision_authority(
            {"producer_job_id": "OTHER-ID"},
            expected_producer=_valid_id(),
        )
        self.assertTrue(any("unauthorized" in e for e in errors))

    def test_validate_decision_staleness_valid(self) -> None:
        errors = self.generator.validate_decision_staleness(
            {"graph_revision": 5},
            current_graph_revision=5,
        )
        self.assertEqual(errors, [])

    def test_validate_decision_staleness_stale(self) -> None:
        errors = self.generator.validate_decision_staleness(
            {"graph_revision": 3},
            current_graph_revision=5,
        )
        self.assertTrue(any("stale" in e for e in errors))

    def test_validate_decision_limits_valid(self) -> None:
        errors = self.generator.validate_decision_limits({
            "reason": "short",
            "evidence_refs": [_valid_evidence_ref()],
        })
        self.assertEqual(errors, [])

    def test_validate_decision_limits_long_field(self) -> None:
        errors = self.generator.validate_decision_limits({
            "reason": "x" * 10001,
        })
        self.assertTrue(any("exceeds maximum length" in e for e in errors))

    def test_validate_decision_limits_too_many_refs(self) -> None:
        errors = self.generator.validate_decision_limits({
            "evidence_refs": [_valid_evidence_ref()] * 101,
        })
        self.assertTrue(any("exceeds maximum" in e for e in errors))

    def test_validate_decision_semantics_valid_goal(self) -> None:
        errors = self.generator.validate_decision_semantics({
            "decision": "GOAL_ACHIEVED",
        })
        self.assertEqual(errors, [])

    def test_validate_decision_semantics_valid_strategy(self) -> None:
        errors = self.generator.validate_decision_semantics({
            "decision_type": "expand",
        })
        self.assertEqual(errors, [])

    def test_validate_decision_semantics_invalid_type(self) -> None:
        errors = self.generator.validate_decision_semantics({
            "decision": "INVALID",
        })
        self.assertTrue(any("invalid decision type" in e for e in errors))

    def test_validate_decision_semantics_invalid_evidence_ref(self) -> None:
        errors = self.generator.validate_decision_semantics({
            "decision": "CONTINUE",
            "evidence_refs": ["bad-ref-format"],
        })
        self.assertTrue(any("invalid evidence ref format" in e for e in errors))

    def test_validate_decision_semantics_valid_evidence_ref(self) -> None:
        errors = self.generator.validate_decision_semantics({
            "decision": "CONTINUE",
            "evidence_refs": [_valid_evidence_ref()],
        })
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
