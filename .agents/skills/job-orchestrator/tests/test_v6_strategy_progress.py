"""Tests for Group 12: Progress, Limits, and Autonomous Alternatives."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError
from progress_v6 import (
    DuplicateDetector,
    FingerprintRecord,
    LimitOutcomeEmitter,
    OutcomeType,
    ProgressCounter,
    ProgressFingerprintComputer,
    ProgressModule,
    StagnationHandler,
    validate_fingerprint,
    validate_progress,
)


# ---------------------------------------------------------------------------
# Task 12.1: Progress fingerprint computation
# ---------------------------------------------------------------------------

class ProgressFingerprintComputerTest(unittest.TestCase):
    """Tests for ProgressFingerprintComputer."""

    def test_compute_fingerprint_returns_sha256(self) -> None:
        computer = ProgressFingerprintComputer()
        record = FingerprintRecord()
        digest = computer.compute_fingerprint(record)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_compute_fingerprint_deterministic(self) -> None:
        computer = ProgressFingerprintComputer()
        record = FingerprintRecord(
            finding_signatures=["sig-a", "sig-b"],
            goal_gates=[{"gate_id": "G1", "status": "pass"}],
        )
        d1 = computer.compute_fingerprint(record)
        d2 = computer.compute_fingerprint(record)
        self.assertEqual(d1, d2)

    def test_compute_fingerprint_varies_with_input(self) -> None:
        computer = ProgressFingerprintComputer()
        r1 = FingerprintRecord(finding_signatures=["sig-a"])
        r2 = FingerprintRecord(finding_signatures=["sig-b"])
        self.assertNotEqual(computer.compute_fingerprint(r1), computer.compute_fingerprint(r2))

    def test_compute_fingerprint_sorted_inputs(self) -> None:
        computer = ProgressFingerprintComputer()
        r1 = FingerprintRecord(finding_signatures=["b", "a"])
        r2 = FingerprintRecord(finding_signatures=["a", "b"])
        self.assertEqual(computer.compute_fingerprint(r1), computer.compute_fingerprint(r2))

    def test_build_fingerprint_record(self) -> None:
        computer = ProgressFingerprintComputer()
        record = computer.build_fingerprint_record(
            finding_signatures=["s1"],
            goal_gates=[{"gate_id": "G1"}],
            hypotheses=[{"hypothesis_id": "H1"}],
            synthesis={"conclusion": "root_cause_identified"},
            work_plan={"plan_type": "direct_repair"},
            verification_findings=[{"finding_id": "V1"}],
            measurements=[{"metric": "coverage", "delta": 0.1}],
            goal_decisions=[{"decision": "CONTINUE"}],
        )
        self.assertIsInstance(record, FingerprintRecord)
        self.assertEqual(record.finding_signatures, ["s1"])
        self.assertEqual(len(record.goal_gates), 1)

    def test_to_schema_record(self) -> None:
        computer = ProgressFingerprintComputer()
        record = computer.to_schema_record(
            fingerprint_id="FP-123",
            cycle_id="CYC-456",
            run_id="run-789",
            graph_revision=3,
            jobs_completed=5,
            jobs_total=10,
            findings_count=2,
            fingerprint_digest="a" * 64,
        )
        self.assertEqual(record["schema_version"], 6)
        self.assertEqual(record["fingerprint_id"], "FP-123")
        self.assertEqual(record["jobs_completed"], 5)
        self.assertIn("created_at", record)


class ValidateFingerprintTest(unittest.TestCase):
    """Tests for validate_fingerprint."""

    def test_valid_record(self) -> None:
        record = {
            "schema_version": 6,
            "fingerprint_id": "FP-1",
            "cycle_id": "CYC-1",
            "run_id": "run-1",
            "graph_revision": 1,
            "jobs_completed": 0,
            "jobs_total": 1,
            "findings_count": 0,
            "fingerprint_digest": "a" * 64,
            "created_at": "2026-01-01T00:00:00Z",
        }
        errors = validate_fingerprint(record)
        self.assertEqual(errors, [])

    def test_missing_required_field(self) -> None:
        record = {"schema_version": 6}
        errors = validate_fingerprint(record)
        self.assertTrue(any("missing" in e for e in errors))

    def test_wrong_schema_version(self) -> None:
        record = {
            "schema_version": 5,
            "fingerprint_id": "FP-1",
            "cycle_id": "CYC-1",
            "run_id": "run-1",
            "graph_revision": 1,
            "jobs_completed": 0,
            "jobs_total": 1,
            "findings_count": 0,
            "fingerprint_digest": "a" * 64,
            "created_at": "2026-01-01T00:00:00Z",
        }
        errors = validate_fingerprint(record)
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_invalid_digest_length(self) -> None:
        record = {
            "schema_version": 6,
            "fingerprint_id": "FP-1",
            "cycle_id": "CYC-1",
            "run_id": "run-1",
            "graph_revision": 1,
            "jobs_completed": 0,
            "jobs_total": 1,
            "findings_count": 0,
            "fingerprint_digest": "abc",
            "created_at": "2026-01-01T00:00:00Z",
        }
        errors = validate_fingerprint(record)
        self.assertTrue(any("64 hex" in e for e in errors))


# ---------------------------------------------------------------------------
# Task 12.2: Count real progress
# ---------------------------------------------------------------------------

class ProgressCounterTest(unittest.TestCase):
    """Tests for ProgressCounter."""

    def test_count_passing_gates(self) -> None:
        counter = ProgressCounter()
        gates = [
            {"gate_id": "G1", "status": "pass"},
            {"gate_id": "G2", "status": "fail"},
            {"gate_id": "G3", "status": "pass"},
        ]
        self.assertEqual(counter.count_passing_gates(gates), 2)

    def test_count_passing_gates_empty(self) -> None:
        counter = ProgressCounter()
        self.assertEqual(counter.count_passing_gates([]), 0)

    def test_count_narrowed_findings(self) -> None:
        counter = ProgressCounter()
        current = [
            {"finding_id": "F1", "scope": {"a"}},
            {"finding_id": "F2", "scope": {"b"}},
        ]
        previous = [
            {"finding_id": "F1", "scope": {"a", "b"}},
            {"finding_id": "F2", "scope": {"b"}},
        ]
        self.assertEqual(counter.count_narrowed_findings(current, previous), 1)

    def test_count_narrowed_findings_no_previous(self) -> None:
        counter = ProgressCounter()
        current = [{"finding_id": "F1", "scope": {"a"}}]
        self.assertEqual(counter.count_narrowed_findings(current, None), 0)

    def test_count_resolved_uncertainty(self) -> None:
        counter = ProgressCounter()
        hypotheses = [
            {"hypothesis_id": "H1", "result_state": "supported"},
            {"hypothesis_id": "H2", "result_state": "refuted"},
            {"hypothesis_id": "H3", "result_state": "inconclusive"},
        ]
        self.assertEqual(counter.count_resolved_uncertainty(hypotheses), 2)

    def test_count_established_causes(self) -> None:
        counter = ProgressCounter()
        synthesis = {
            "planning_constraints": {
                "supported_causes": ["cause-a", "cause-b"],
                "refuted_causes": [],
                "unresolved_causes": ["cause-c"],
            }
        }
        self.assertEqual(counter.count_established_causes(synthesis), 2)

    def test_count_established_causes_empty(self) -> None:
        counter = ProgressCounter()
        self.assertEqual(counter.count_established_causes({}), 0)

    def test_count_removed_blockers(self) -> None:
        counter = ProgressCounter()
        gates = [
            {"gate_id": "G1", "previous_status": "blocked", "status": "pass"},
            {"gate_id": "G2", "previous_status": "open", "status": "pass"},
        ]
        self.assertEqual(counter.count_removed_blockers(gates), 1)

    def test_count_measurable_improvement(self) -> None:
        counter = ProgressCounter()
        measurements = [
            {"metric": "coverage", "delta": 0.1, "improvement_direction": "higher"},
            {"metric": "defects", "delta": -2, "improvement_direction": "lower"},
            {"metric": "time", "delta": 5.0, "improvement_direction": "lower"},
        ]
        self.assertEqual(counter.count_measurable_improvement(measurements), 2)

    def test_total_progress(self) -> None:
        counter = ProgressCounter()
        gates = [{"gate_id": "G1", "status": "pass"}]
        hypotheses = [{"hypothesis_id": "H1", "result_state": "supported"}]
        total = counter.total_progress(
            goal_gates=gates,
            findings=[],
            hypotheses=hypotheses,
        )
        self.assertEqual(total, 2)


class ValidateProgressTest(unittest.TestCase):
    """Tests for validate_progress."""

    def test_no_error_when_no_jobs(self) -> None:
        counter = ProgressCounter()
        errors = validate_progress(counter, jobs_completed=0)
        self.assertEqual(errors, [])

    def test_error_when_jobs_but_no_progress(self) -> None:
        counter = ProgressCounter()
        errors = validate_progress(
            counter,
            jobs_completed=5,
            goal_gates=[],
            findings=[],
        )
        self.assertTrue(len(errors) > 0)
        self.assertIn("no real progress", errors[0])

    def test_no_error_when_jobs_and_progress(self) -> None:
        counter = ProgressCounter()
        errors = validate_progress(
            counter,
            jobs_completed=5,
            goal_gates=[{"gate_id": "G1", "status": "pass"}],
            findings=[],
        )
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# Task 12.3: Duplicate detection
# ---------------------------------------------------------------------------

class DuplicateDetectorTest(unittest.TestCase):
    """Tests for DuplicateDetector."""

    def test_no_duplicate_first_time(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "test", "finding_id": "F1"}
        result = detector.detect_duplicate_hypotheses(hyp)
        self.assertFalse(result["is_duplicate"])

    def test_detect_duplicate_hypothesis(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "test", "finding_id": "F1"}
        detector.record_hypothesis(hyp)
        result = detector.detect_duplicate_hypotheses(hyp)
        self.assertTrue(result["is_duplicate"])

    def test_no_duplicate_different_hypothesis(self) -> None:
        detector = DuplicateDetector()
        h1 = {"hypothesis_text": "test-a", "finding_id": "F1"}
        h2 = {"hypothesis_text": "test-b", "finding_id": "F1"}
        detector.record_hypothesis(h1)
        result = detector.detect_duplicate_hypotheses(h2)
        self.assertFalse(result["is_duplicate"])

    def test_detect_duplicate_job(self) -> None:
        detector = DuplicateDetector()
        job = {"role": "repair", "purpose_key": "fix-bug", "authority_id": "A1"}
        detector.record_job(job)
        result = detector.detect_duplicate_jobs(job)
        self.assertTrue(result["is_duplicate"])

    def test_detect_duplicate_plan(self) -> None:
        detector = DuplicateDetector()
        plan = {"plan_type": "direct_repair", "selected_decision": "direct_repair", "targets": []}
        detector.record_plan(plan)
        result = detector.detect_duplicate_plans(plan)
        self.assertTrue(result["is_duplicate"])

    def test_reject_without_new_evidence(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "test", "finding_id": "F1"}
        detector.record_hypothesis(hyp)
        result = detector.reject_without_new_evidence(hyp, "hypothesis", None)
        self.assertTrue(result["rejected"])

    def test_accept_with_new_evidence(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "test", "finding_id": "F1"}
        detector.record_hypothesis(hyp)
        result = detector.reject_without_new_evidence(
            hyp, "hypothesis", ["new-evidence-ref"]
        )
        self.assertFalse(result["rejected"])

    def test_accept_non_duplicate(self) -> None:
        detector = DuplicateDetector()
        hyp = {"hypothesis_text": "unique", "finding_id": "F1"}
        result = detector.reject_without_new_evidence(hyp, "hypothesis", None)
        self.assertFalse(result["rejected"])

    def test_has_new_evidence(self) -> None:
        detector = DuplicateDetector()
        detector.record_evidence("item-1", ["ev-a", "ev-b"])
        self.assertTrue(detector.has_new_evidence("item-1", ["ev-c"]))
        self.assertFalse(detector.has_new_evidence("item-1", ["ev-a"]))

    def test_stable_hypothesis_signature_deterministic(self) -> None:
        h1 = {"hypothesis_text": "test", "finding_id": "F1", "predicted_observations": [], "falsifying_observations": []}
        h2 = {"hypothesis_text": "test", "finding_id": "F1", "predicted_observations": [], "falsifying_observations": []}
        s1 = DuplicateDetector._stable_hypothesis_signature(h1)
        s2 = DuplicateDetector._stable_hypothesis_signature(h2)
        self.assertEqual(s1, s2)

    def test_stable_job_signature_deterministic(self) -> None:
        j1 = {"role": "repair", "purpose_key": "fix", "authority_id": "A1"}
        j2 = {"role": "repair", "purpose_key": "fix", "authority_id": "A1"}
        s1 = DuplicateDetector._stable_job_signature(j1)
        s2 = DuplicateDetector._stable_job_signature(j2)
        self.assertEqual(s1, s2)


# ---------------------------------------------------------------------------
# Task 12.4: Stagnation handling
# ---------------------------------------------------------------------------

class StagnationHandlerTest(unittest.TestCase):
    """Tests for StagnationHandler."""

    def test_no_stagnation_below_threshold(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.detect_stagnation("item-1")
        self.assertFalse(result["is_stagnant"])
        self.assertEqual(result["failure_count"], 1)

    def test_stagnation_at_threshold(self) -> None:
        handler = StagnationHandler(max_failures=2)
        handler.detect_stagnation("item-1")
        result = handler.detect_stagnation("item-1")
        self.assertTrue(result["is_stagnant"])
        self.assertTrue(result["requires_alternate_approach"])

    def test_stagnation_independent_per_item(self) -> None:
        handler = StagnationHandler(max_failures=2)
        handler.detect_stagnation("item-1")
        result = handler.detect_stagnation("item-2")
        self.assertFalse(result["is_stagnant"])

    def test_material_difference_same(self) -> None:
        handler = StagnationHandler()
        original = {"hypothesis_text": "test", "evidence_source": "src-a"}
        proposed = {"hypothesis_text": "test", "evidence_source": "src-a"}
        result = handler.require_material_difference(original, proposed)
        self.assertFalse(result["is_materially_different"])

    def test_material_difference_hypothesis(self) -> None:
        handler = StagnationHandler()
        original = {"hypothesis_text": "old", "evidence_source": "src-a"}
        proposed = {"hypothesis_text": "new", "evidence_source": "src-a"}
        result = handler.require_material_difference(original, proposed)
        self.assertTrue(result["is_materially_different"])
        self.assertIn("hypothesis", result["differences"])

    def test_material_difference_evidence_source(self) -> None:
        handler = StagnationHandler()
        original = {"hypothesis_text": "test", "evidence_source": "src-a"}
        proposed = {"hypothesis_text": "test", "evidence_source": "src-b"}
        result = handler.require_material_difference(original, proposed)
        self.assertTrue(result["is_materially_different"])
        self.assertIn("evidence_source", result["differences"])

    def test_material_difference_enforcement_boundary(self) -> None:
        handler = StagnationHandler()
        original = {"enforcement_boundary": "local"}
        proposed = {"enforcement_boundary": "global"}
        result = handler.require_material_difference(original, proposed)
        self.assertTrue(result["is_materially_different"])
        self.assertIn("enforcement_boundary", result["differences"])

    def test_material_difference_migration_strategy(self) -> None:
        handler = StagnationHandler()
        original = {"migration_strategy": "in-place"}
        proposed = {"migration_strategy": "side-by-side"}
        result = handler.require_material_difference(original, proposed)
        self.assertTrue(result["is_materially_different"])
        self.assertIn("migration_strategy", result["differences"])

    def test_material_difference_decomposition(self) -> None:
        handler = StagnationHandler()
        original = {"decomposition": "monolith"}
        proposed = {"decomposition": "microservice"}
        result = handler.require_material_difference(original, proposed)
        self.assertTrue(result["is_materially_different"])
        self.assertIn("decomposition", result["differences"])

    def test_promote_to_multi_job(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_multi_job("item-1", 3)
        self.assertTrue(result["should_promote"])
        self.assertEqual(result["promotion_type"], "multi_job_repair")

    def test_no_promote_too_few_failures(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_multi_job("item-1", 2)
        self.assertFalse(result["should_promote"])

    def test_promote_to_openspec(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_openspec("item-1", 3, needs_material_redesign=True)
        self.assertTrue(result["should_promote"])
        self.assertEqual(result["promotion_type"], "openspec_work")

    def test_no_promote_to_openspec_without_redesign(self) -> None:
        handler = StagnationHandler(max_failures=3)
        result = handler.promote_to_openspec("item-1", 3, needs_material_redesign=False)
        self.assertFalse(result["should_promote"])

    def test_failure_history_tracked(self) -> None:
        handler = StagnationHandler(max_failures=3)
        handler.detect_stagnation("item-1", "reason-a")
        handler.detect_stagnation("item-1", "reason-b")
        history = handler.get_failure_history("item-1")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["reason"], "reason-a")
        self.assertEqual(history[1]["reason"], "reason-b")


# ---------------------------------------------------------------------------
# Task 12.5: Limit outcome emission
# ---------------------------------------------------------------------------

class LimitOutcomeEmitterTest(unittest.TestCase):
    """Tests for LimitOutcomeEmitter."""

    def test_emit_blocked_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = emitter.emit_blocked_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            reason="blocked by dependency",
            blocked_by="JOB-123",
        )
        self.assertEqual(outcome["outcome_type"], OutcomeType.BLOCKED.value)
        self.assertEqual(outcome["schema_version"], 6)
        self.assertEqual(outcome["blocked_by"], "JOB-123")
        self.assertIn("recorded_at", outcome)

    def test_emit_no_progress_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = emitter.emit_no_progress_outcome(
            graph_revision=2,
            graph_digest="b" * 64,
            reason="no improvement",
            cycles_without_progress=3,
        )
        self.assertEqual(outcome["outcome_type"], OutcomeType.NO_PROGRESS.value)
        self.assertEqual(outcome["cycles_without_progress"], 3)

    def test_emit_budget_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = emitter.emit_budget_outcome(
            graph_revision=3,
            graph_digest="c" * 64,
            reason="token limit exceeded",
            budget_type="tokens",
            consumed=100000,
            limit=80000,
        )
        self.assertEqual(outcome["outcome_type"], OutcomeType.BUDGET_EXHAUSTED.value)
        self.assertEqual(outcome["budget_type"], "tokens")
        self.assertEqual(outcome["consumed"], 100000)

    def test_emit_infeasible_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = emitter.emit_infeasible_outcome(
            graph_revision=4,
            graph_digest="d" * 64,
            reason="contradictory requirements",
            contradictions=["req-A conflicts with req-B"],
        )
        self.assertEqual(outcome["outcome_type"], OutcomeType.INFEASIBLE.value)
        self.assertEqual(len(outcome["contradictions"]), 1)

    def test_validate_no_false_success_when_limits_hit(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": OutcomeType.GOAL_ACHIEVED.value}
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertTrue(len(errors) > 0)
        self.assertIn("false success", errors[0])

    def test_validate_no_false_success_when_no_limits(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": OutcomeType.GOAL_ACHIEVED.value}
        errors = emitter.validate_no_false_success(outcome, limits_hit=False)
        self.assertEqual(errors, [])

    def test_validate_terminal_outcome_when_limits_hit(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": OutcomeType.BLOCKED.value}
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertEqual(errors, [])

    def test_validate_wrong_terminal_outcome(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = {"outcome_type": "something_wrong"}
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertTrue(len(errors) > 0)


# ---------------------------------------------------------------------------
# Task 12.6: Bounded graph fan-out and integrated tests
# ---------------------------------------------------------------------------

class ProgressModuleTest(unittest.TestCase):
    """Tests for ProgressModule integration."""

    def test_compute_cycle_fingerprint(self) -> None:
        module = ProgressModule()
        result = module.compute_cycle_fingerprint(
            cycle_id="CYC-1",
            run_id="run-1",
            graph_revision=1,
            jobs_completed=3,
            jobs_total=5,
            finding_signatures=["sig-a"],
            goal_gates=[{"gate_id": "G1", "status": "pass"}],
            hypotheses=[{"hypothesis_id": "H1", "result_state": "supported"}],
        )
        self.assertEqual(result["schema_version"], 6)
        self.assertEqual(result["jobs_completed"], 3)
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(len(result["fingerprint_digest"]), 64)

    def test_count_real_progress(self) -> None:
        module = ProgressModule()
        count = module.count_real_progress(
            goal_gates=[{"gate_id": "G1", "status": "pass"}],
            findings=[],
            hypotheses=[{"hypothesis_id": "H1", "result_state": "refuted"}],
        )
        self.assertEqual(count, 2)

    def test_check_and_emit_limit_outcome_no_limits(self) -> None:
        module = ProgressModule()
        result = module.check_and_emit_limit_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            limits_hit=False,
        )
        self.assertEqual(result["outcome_type"], OutcomeType.CONTINUE.value)

    def test_check_and_emit_limit_outcome_blocked(self) -> None:
        module = ProgressModule()
        result = module.check_and_emit_limit_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            limits_hit=True,
            limit_reason="max jobs reached",
        )
        self.assertEqual(result["outcome_type"], OutcomeType.BLOCKED.value)

    def test_check_and_emit_limit_outcome_budget(self) -> None:
        module = ProgressModule()
        result = module.check_and_emit_limit_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            limits_hit=True,
            limit_reason="tokens exhausted",
            budget_type="tokens",
            consumed=100000,
            limit=80000,
        )
        self.assertEqual(result["outcome_type"], OutcomeType.BUDGET_EXHAUSTED.value)

    def test_check_and_emit_limit_outcome_infeasible(self) -> None:
        module = ProgressModule()
        result = module.check_and_emit_limit_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            limits_hit=True,
            limit_reason="contradictions",
            contradictions=["A contradicts B"],
        )
        self.assertEqual(result["outcome_type"], OutcomeType.INFEASIBLE.value)


class BoundedGraphFanoutTest(unittest.TestCase):
    """Tests for bounded graph fan-out behavior."""

    def test_duplicate_detection_prevents_repeated_work(self) -> None:
        detector = DuplicateDetector()
        plan = {"plan_type": "direct_repair", "selected_decision": "direct_repair", "targets": []}
        detector.record_plan(plan)
        result = detector.detect_duplicate_plans(plan)
        self.assertTrue(result["is_duplicate"])

    def test_stagnation_triggers_alternate_approach(self) -> None:
        handler = StagnationHandler(max_failures=2)
        handler.detect_stagnation("repair-1")
        result = handler.detect_stagnation("repair-1")
        self.assertTrue(result["requires_alternate_approach"])

    def test_limit_emission_blocks_continuation(self) -> None:
        emitter = LimitOutcomeEmitter()
        outcome = emitter.emit_blocked_outcome(
            graph_revision=1,
            graph_digest="a" * 64,
            reason="fan-out limit",
        )
        self.assertEqual(outcome["outcome_type"], OutcomeType.BLOCKED.value)
        errors = emitter.validate_no_false_success(outcome, limits_hit=True)
        self.assertEqual(errors, [])

    def test_progress_counter_real_not_job_count(self) -> None:
        counter = ProgressCounter()
        total = counter.total_progress(
            goal_gates=[],
            findings=[],
            hypotheses=[],
            synthesis={},
            measurements=[],
        )
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()
