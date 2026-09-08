"""v6 progress tracking, duplicate detection, stagnation handling, and limit outcomes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from orchestrator_core import (
    SCHEMA_VERSION,
    OrchestratorError,
    canonical_bytes,
    content_hash,
    stable_id,
    utc_now,
)


# ---------------------------------------------------------------------------
# Task 12.1: Progress fingerprint computation
# ---------------------------------------------------------------------------

class FingerprintRecord:
    """Immutable record of all components contributing to a cycle progress fingerprint."""

    def __init__(
        self,
        finding_signatures: list[str] | None = None,
        goal_gates: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        work_plan: dict[str, Any] | None = None,
        verification_findings: list[dict[str, Any]] | None = None,
        measurements: list[dict[str, Any]] | None = None,
        goal_decisions: list[dict[str, Any]] | None = None,
    ) -> None:
        self.finding_signatures = finding_signatures or []
        self.goal_gates = goal_gates or []
        self.hypotheses = hypotheses or []
        self.synthesis = synthesis or {}
        self.work_plan = work_plan or {}
        self.verification_findings = verification_findings or []
        self.measurements = measurements or []
        self.goal_decisions = goal_decisions or []


class ProgressFingerprintComputer:
    """Compute cycle progress fingerprints from finding signatures, goal gates,
    hypotheses, synthesis, work plan, verification findings, measurements,
    and goal decisions."""

    def compute_fingerprint(self, record: FingerprintRecord) -> str:
        """Hash all components into a stable SHA-256 fingerprint digest."""
        payload = {
            "finding_signatures": sorted(record.finding_signatures),
            "goal_gates": self._canonicalize_list(record.goal_gates),
            "hypotheses": self._canonicalize_list(record.hypotheses),
            "synthesis": self._canonicalize_dict(record.synthesis),
            "work_plan": self._canonicalize_dict(record.work_plan),
            "verification_findings": self._canonicalize_list(record.verification_findings),
            "measurements": self._canonicalize_list(record.measurements),
            "goal_decisions": self._canonicalize_list(record.goal_decisions),
        }
        return content_hash(payload)

    def build_fingerprint_record(
        self,
        finding_signatures: list[str] | None = None,
        goal_gates: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        work_plan: dict[str, Any] | None = None,
        verification_findings: list[dict[str, Any]] | None = None,
        measurements: list[dict[str, Any]] | None = None,
        goal_decisions: list[dict[str, Any]] | None = None,
    ) -> FingerprintRecord:
        """Build a FingerprintRecord from individual components."""
        return FingerprintRecord(
            finding_signatures=finding_signatures,
            goal_gates=goal_gates,
            hypotheses=hypotheses,
            synthesis=synthesis,
            work_plan=work_plan,
            verification_findings=verification_findings,
            measurements=measurements,
            goal_decisions=goal_decisions,
        )

    def to_schema_record(
        self,
        fingerprint_id: str,
        cycle_id: str,
        run_id: str,
        graph_revision: int,
        jobs_completed: int,
        jobs_total: int,
        findings_count: int,
        fingerprint_digest: str,
    ) -> dict[str, Any]:
        """Convert to a v6 progress-fingerprint schema record."""
        import re
        id_pattern = re.compile(r"[A-Z][A-Z0-9_-]{0,127}")
        if not id_pattern.fullmatch(fingerprint_id):
            fingerprint_id = fingerprint_id.upper().replace(" ", "_")
        if not id_pattern.fullmatch(cycle_id):
            cycle_id = cycle_id.upper().replace(" ", "_")
        return {
            "schema_version": SCHEMA_VERSION,
            "fingerprint_id": fingerprint_id,
            "cycle_id": cycle_id,
            "run_id": run_id,
            "graph_revision": graph_revision,
            "jobs_completed": jobs_completed,
            "jobs_total": jobs_total,
            "findings_count": findings_count,
            "fingerprint_digest": fingerprint_digest,
            "created_at": utc_now(),
        }

    @staticmethod
    def _canonicalize_dict(d: dict[str, Any]) -> dict[str, Any]:
        """Produce a sorted, canonical representation of a dict."""
        if not d:
            return {}
        return {k: v for k, v in sorted(d.items())}

    @staticmethod
    def _canonicalize_list(items: list[Any]) -> list[Any]:
        """Produce a sorted, canonical representation of a list of dicts/strings."""
        if not items:
            return []
        if items and isinstance(items[0], dict):
            return sorted(items, key=lambda x: canonical_bytes(x))
        return sorted(items, key=str)


def validate_fingerprint(record: dict[str, Any]) -> list[str]:
    """Ensure all fingerprint components are included. Returns error list."""
    errors: list[str] = []
    required_fields = [
        "fingerprint_id",
        "cycle_id",
        "run_id",
        "graph_revision",
        "jobs_completed",
        "jobs_total",
        "findings_count",
        "fingerprint_digest",
        "created_at",
    ]
    for field_name in required_fields:
        if field_name not in record:
            errors.append(f"missing required field: {field_name}")

    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    digest = record.get("fingerprint_digest", "")
    if isinstance(digest, str) and not all(c in "0123456789abcdef" for c in digest):
        errors.append("fingerprint_digest must be a hex string")
    if isinstance(digest, str) and len(digest) != 64:
        errors.append("fingerprint_digest must be exactly 64 hex characters")

    return errors


# ---------------------------------------------------------------------------
# Task 12.2: Count real progress
# ---------------------------------------------------------------------------

class ProgressCounter:
    """Count progress only for independently passing gates, narrowed findings,
    resolved uncertainty, supported or refuted hypotheses, established causes,
    removed blockers, or measurable improvement."""

    def count_passing_gates(self, goal_gates: list[dict[str, Any]]) -> int:
        """Count gates that independently pass (status == 'pass')."""
        return sum(
            1 for gate in goal_gates
            if gate.get("status") == "pass"
        )

    def count_narrowed_findings(
        self,
        findings: list[dict[str, Any]],
        previous_findings: list[dict[str, Any]] | None = None,
    ) -> int:
        """Count findings whose scope has been reduced since previous cycle."""
        if not previous_findings:
            return 0
        prev_map = {f.get("finding_id"): f for f in previous_findings}
        narrowed = 0
        for finding in findings:
            fid = finding.get("finding_id")
            prev = prev_map.get(fid)
            if prev is None:
                continue
            prev_scope = prev.get("scope", set())
            curr_scope = finding.get("scope", set())
            if isinstance(prev_scope, set) and isinstance(curr_scope, set):
                if curr_scope < prev_scope:
                    narrowed += 1
            elif isinstance(prev_scope, list) and isinstance(curr_scope, list):
                if len(curr_scope) < len(prev_scope):
                    narrowed += 1
        return narrowed

    def count_resolved_uncertainty(
        self,
        hypotheses: list[dict[str, Any]],
    ) -> int:
        """Count hypotheses that have been settled (supported or refuted)."""
        settled_states = {"supported", "refuted"}
        return sum(
            1 for h in hypotheses
            if h.get("result_state") in settled_states
        )

    def count_established_causes(
        self,
        synthesis: dict[str, Any],
    ) -> int:
        """Count causes identified in synthesis (supported_causes)."""
        constraints = synthesis.get("planning_constraints", {})
        causes = constraints.get("supported_causes", [])
        return len(causes) if isinstance(causes, list) else 0

    def count_removed_blockers(
        self,
        goal_gates: list[dict[str, Any]],
    ) -> int:
        """Count blockers that have been removed (status changed from blocked)."""
        return sum(
            1 for gate in goal_gates
            if gate.get("previous_status") == "blocked"
            and gate.get("status") != "blocked"
        )

    def count_measurable_improvement(
        self,
        measurements: list[dict[str, Any]],
    ) -> int:
        """Count measurements that show improvement (delta > 0 or improved direction)."""
        improved = 0
        for m in measurements:
            delta = m.get("delta", 0)
            direction = m.get("improvement_direction", "higher")
            if direction == "higher" and delta > 0:
                improved += 1
            elif direction == "lower" and delta < 0:
                improved += 1
        return improved

    def total_progress(
        self,
        goal_gates: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        previous_findings: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        measurements: list[dict[str, Any]] | None = None,
    ) -> int:
        """Sum all real progress indicators."""
        total = 0
        total += self.count_passing_gates(goal_gates)
        total += self.count_narrowed_findings(findings, previous_findings)
        total += self.count_resolved_uncertainty(hypotheses or [])
        total += self.count_established_causes(synthesis or {})
        total += self.count_removed_blockers(goal_gates)
        total += self.count_measurable_improvement(measurements or [])
        return total


def validate_progress(counter: ProgressCounter, **kwargs: Any) -> list[str]:
    """Ensure progress is real, not just job count. Returns error list."""
    errors: list[str] = []
    jobs_completed = kwargs.pop("jobs_completed", 0)
    kwargs.setdefault("goal_gates", [])
    kwargs.setdefault("findings", [])
    total = counter.total_progress(**kwargs)
    if jobs_completed > 0 and total == 0:
        errors.append(
            "progress validation failed: jobs completed but no real progress indicators"
        )
    return errors


# ---------------------------------------------------------------------------
# Task 12.3: Duplicate detection
# ---------------------------------------------------------------------------

class DuplicateDetector:
    """Detect semantic duplicate hypotheses, jobs, and plans by stable signature
    and reject repeated failed work without new evidence."""

    def __init__(self) -> None:
        self._seen_hypothesis_signatures: dict[str, dict[str, Any]] = {}
        self._seen_job_signatures: dict[str, dict[str, Any]] = {}
        self._seen_plan_signatures: dict[str, dict[str, Any]] = {}
        self._seen_evidence: dict[str, set[str]] = {}

    def detect_duplicate_hypotheses(
        self,
        hypothesis: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if a hypothesis with the same stable signature was already seen.

        Returns detection result with is_duplicate flag and matching record.
        """
        sig = self._stable_hypothesis_signature(hypothesis)
        if sig in self._seen_hypothesis_signatures:
            return {
                "is_duplicate": True,
                "original_signature": sig,
                "original_record": self._seen_hypothesis_signatures[sig],
            }
        return {"is_duplicate": False, "signature": sig}

    def record_hypothesis(self, hypothesis: dict[str, Any]) -> None:
        """Record a hypothesis for future duplicate detection."""
        sig = self._stable_hypothesis_signature(hypothesis)
        self._seen_hypothesis_signatures[sig] = hypothesis

    def detect_duplicate_jobs(
        self,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if a job with the same stable signature was already seen.

        Returns detection result with is_duplicate flag and matching record.
        """
        sig = self._stable_job_signature(job)
        if sig in self._seen_job_signatures:
            return {
                "is_duplicate": True,
                "original_signature": sig,
                "original_record": self._seen_job_signatures[sig],
            }
        return {"is_duplicate": False, "signature": sig}

    def record_job(self, job: dict[str, Any]) -> None:
        """Record a job for future duplicate detection."""
        sig = self._stable_job_signature(job)
        self._seen_job_signatures[sig] = job

    def detect_duplicate_plans(
        self,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if a plan with the same stable signature was already seen.

        Returns detection result with is_duplicate flag and matching record.
        """
        sig = self._stable_plan_signature(plan)
        if sig in self._seen_plan_signatures:
            return {
                "is_duplicate": True,
                "original_signature": sig,
                "original_record": self._seen_plan_signatures[sig],
            }
        return {"is_duplicate": False, "signature": sig}

    def record_plan(self, plan: dict[str, Any]) -> None:
        """Record a plan for future duplicate detection."""
        sig = self._stable_plan_signature(plan)
        self._seen_plan_signatures[sig] = plan

    def reject_without_new_evidence(
        self,
        item: dict[str, Any],
        item_type: str,
        new_evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        """Reject if a duplicate exists and no new evidence is provided.

        Returns rejection result.
        """
        if item_type == "hypothesis":
            detection = self.detect_duplicate_hypotheses(item)
        elif item_type == "job":
            detection = self.detect_duplicate_jobs(item)
        elif item_type == "plan":
            detection = self.detect_duplicate_plans(item)
        else:
            return {"rejected": False, "reason": f"unknown item_type: {item_type}"}

        if not detection.get("is_duplicate"):
            return {"rejected": False, "reason": "not a duplicate"}

        if not new_evidence:
            return {
                "rejected": True,
                "reason": "duplicate detected without new evidence",
                "original_signature": detection.get("original_signature"),
            }

        return {
            "rejected": False,
            "reason": "duplicate but new evidence provided",
            "new_evidence": new_evidence,
        }

    def has_new_evidence(
        self,
        item_id: str,
        evidence_refs: list[str],
    ) -> bool:
        """Check if any evidence references are new for this item."""
        if item_id not in self._seen_evidence:
            return True
        existing = self._seen_evidence[item_id]
        new = set(evidence_refs) - existing
        return len(new) > 0

    def record_evidence(self, item_id: str, evidence_refs: list[str]) -> None:
        """Record evidence references for an item."""
        if item_id not in self._seen_evidence:
            self._seen_evidence[item_id] = set()
        self._seen_evidence[item_id].update(evidence_refs)

    @staticmethod
    def _stable_hypothesis_signature(hypothesis: dict[str, Any]) -> str:
        """Compute stable signature for a hypothesis."""
        payload = {
            "hypothesis_text": hypothesis.get("hypothesis_text", ""),
            "finding_id": hypothesis.get("finding_id", ""),
            "predicted_observations": hypothesis.get("predicted_observations", []),
            "falsifying_observations": hypothesis.get("falsifying_observations", []),
        }
        return content_hash(payload)

    @staticmethod
    def _stable_job_signature(job: dict[str, Any]) -> str:
        """Compute stable signature for a job."""
        payload = {
            "role": job.get("role", ""),
            "purpose_key": job.get("purpose_key", ""),
            "authority_id": job.get("authority_id", ""),
        }
        return content_hash(payload)

    @staticmethod
    def _stable_plan_signature(plan: dict[str, Any]) -> str:
        """Compute stable signature for a work plan."""
        payload = {
            "plan_type": plan.get("plan_type", ""),
            "selected_decision": plan.get("selected_decision", ""),
            "targets": plan.get("targets", []),
        }
        return content_hash(payload)


# ---------------------------------------------------------------------------
# Task 12.4: Stagnation handling
# ---------------------------------------------------------------------------

class StagnationHandler:
    """Require materially different hypothesis, evidence source, enforcement
    boundary, migration strategy, or decomposition after stagnation."""

    DEFAULT_MAX_FAILURES = 3

    def __init__(self, max_failures: int = DEFAULT_MAX_FAILURES) -> None:
        self.max_failures = max_failures
        self._failure_counts: dict[str, int] = {}
        self._failure_history: dict[str, list[dict[str, Any]]] = {}

    def detect_stagnation(
        self,
        item_id: str,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        """Track repeated failures and detect stagnation.

        Returns stagnation status.
        """
        count = self._failure_counts.get(item_id, 0) + 1
        self._failure_counts[item_id] = count

        if item_id not in self._failure_history:
            self._failure_history[item_id] = []
        self._failure_history[item_id].append({
            "failure_count": count,
            "reason": failure_reason,
            "at": utc_now(),
        })

        is_stagnant = count >= self.max_failures
        return {
            "item_id": item_id,
            "failure_count": count,
            "is_stagnant": is_stagnant,
            "max_failures": self.max_failures,
            "requires_alternate_approach": is_stagnant,
        }

    def require_material_difference(
        self,
        original: dict[str, Any],
        proposed: dict[str, Any],
    ) -> dict[str, Any]:
        """Check that a proposed approach is materially different from the original.

        A material difference requires change in at least one of:
        - hypothesis text
        - evidence source
        - enforcement boundary
        - migration strategy
        - decomposition

        Returns validation result.
        """
        differences: list[str] = []

        orig_hyp = original.get("hypothesis_text", "")
        prop_hyp = proposed.get("hypothesis_text", "")
        if prop_hyp != orig_hyp:
            differences.append("hypothesis")

        orig_evidence = original.get("evidence_source", "")
        prop_evidence = proposed.get("evidence_source", "")
        if prop_evidence != orig_evidence:
            differences.append("evidence_source")

        orig_boundary = original.get("enforcement_boundary", "")
        prop_boundary = proposed.get("enforcement_boundary", "")
        if prop_boundary != orig_boundary:
            differences.append("enforcement_boundary")

        orig_migration = original.get("migration_strategy", "")
        prop_migration = proposed.get("migration_strategy", "")
        if prop_migration != orig_migration:
            differences.append("migration_strategy")

        orig_decomp = original.get("decomposition", "")
        prop_decomp = proposed.get("decomposition", "")
        if prop_decomp != orig_decomp:
            differences.append("decomposition")

        is_material = len(differences) > 0
        return {
            "is_materially_different": is_material,
            "differences": differences,
            "reason": (
                "proposed approach is materially different"
                if is_material
                else "proposed approach is not materially different"
            ),
        }

    def promote_to_multi_job(
        self,
        item_id: str,
        failure_count: int,
    ) -> dict[str, Any]:
        """When direct repair fails, promote to multi-job repair.

        Returns promotion decision.
        """
        should_promote = failure_count >= self.max_failures
        return {
            "item_id": item_id,
            "promotion_type": "multi_job_repair",
            "should_promote": should_promote,
            "reason": (
                f"direct repair failed {failure_count} time(s); "
                "promoting to multi-job repair"
                if should_promote
                else "not enough failures for promotion"
            ),
        }

    def promote_to_openspec(
        self,
        item_id: str,
        failure_count: int,
        needs_material_redesign: bool = False,
    ) -> dict[str, Any]:
        """When material redesign is needed, promote to OpenSpec work.

        Returns promotion decision.
        """
        should_promote = failure_count >= self.max_failures and needs_material_redesign
        return {
            "item_id": item_id,
            "promotion_type": "openspec_work",
            "should_promote": should_promote,
            "reason": (
                f"material redesign required after {failure_count} failure(s); "
                "promoting to OpenSpec work"
                if should_promote
                else "conditions not met for OpenSpec promotion"
            ),
        }

    def get_failure_count(self, item_id: str) -> int:
        """Get the current failure count for an item."""
        return self._failure_counts.get(item_id, 0)

    def get_failure_history(self, item_id: str) -> list[dict[str, Any]]:
        """Get the failure history for an item."""
        return list(self._failure_history.get(item_id, []))


# ---------------------------------------------------------------------------
# Task 12.5: Limit outcome emission
# ---------------------------------------------------------------------------

class OutcomeType(str, Enum):
    BLOCKED = "blocked"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INFEASIBLE = "infeasible"
    GOAL_ACHIEVED = "goal_achieved"
    CONTINUE = "continue"


class LimitOutcomeEmitter:
    """Emit typed blocked, no-progress, budget, or infeasible outcomes when
    limits or contradictions prevent continuation, without claiming goal success."""

    def emit_blocked_outcome(
        self,
        graph_revision: int,
        graph_digest: str,
        reason: str,
        blocked_by: str | None = None,
    ) -> dict[str, Any]:
        """Emit a BLOCKED outcome when work cannot proceed."""
        return {
            "outcome_type": OutcomeType.BLOCKED.value,
            "schema_version": SCHEMA_VERSION,
            "graph_revision": graph_revision,
            "graph_digest": graph_digest,
            "reason": reason,
            "blocked_by": blocked_by,
            "recorded_at": utc_now(),
        }

    def emit_no_progress_outcome(
        self,
        graph_revision: int,
        graph_digest: str,
        reason: str,
        cycles_without_progress: int = 1,
    ) -> dict[str, Any]:
        """Emit a BLOCKED_NO_PROGRESS outcome when no real progress is made."""
        return {
            "outcome_type": OutcomeType.NO_PROGRESS.value,
            "schema_version": SCHEMA_VERSION,
            "graph_revision": graph_revision,
            "graph_digest": graph_digest,
            "reason": reason,
            "cycles_without_progress": cycles_without_progress,
            "recorded_at": utc_now(),
        }

    def emit_budget_outcome(
        self,
        graph_revision: int,
        graph_digest: str,
        reason: str,
        budget_type: str = "unknown",
        consumed: float = 0.0,
        limit: float = 0.0,
    ) -> dict[str, Any]:
        """Emit a BUDGET_EXHAUSTED outcome when budget is consumed."""
        return {
            "outcome_type": OutcomeType.BUDGET_EXHAUSTED.value,
            "schema_version": SCHEMA_VERSION,
            "graph_revision": graph_revision,
            "graph_digest": graph_digest,
            "reason": reason,
            "budget_type": budget_type,
            "consumed": consumed,
            "limit": limit,
            "recorded_at": utc_now(),
        }

    def emit_infeasible_outcome(
        self,
        graph_revision: int,
        graph_digest: str,
        reason: str,
        contradictions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Emit an INFEASIBLE outcome when contradictions prevent success."""
        return {
            "outcome_type": OutcomeType.INFEASIBLE.value,
            "schema_version": SCHEMA_VERSION,
            "graph_revision": graph_revision,
            "graph_digest": graph_digest,
            "reason": reason,
            "contradictions": contradictions or [],
            "recorded_at": utc_now(),
        }

    def validate_no_false_success(
        self,
        outcome: dict[str, Any],
        limits_hit: bool,
    ) -> list[str]:
        """Ensure we never claim success when limits are hit.

        Returns error list; empty means valid.
        """
        errors: list[str] = []
        outcome_type = outcome.get("outcome_type")

        if limits_hit and outcome_type == OutcomeType.GOAL_ACHIEVED.value:
            errors.append(
                "false success: GOAL_ACHIEVED claimed while limits are active"
            )

        if limits_hit and outcome_type == OutcomeType.CONTINUE.value:
            errors.append(
                "false continuation: CONTINUE claimed while limits are active"
            )

        terminal_outcomes = {
            OutcomeType.BLOCKED.value,
            OutcomeType.NO_PROGRESS.value,
            OutcomeType.BUDGET_EXHAUSTED.value,
            OutcomeType.INFEASIBLE.value,
        }
        if limits_hit and outcome_type not in terminal_outcomes:
            errors.append(
                f"limits hit but outcome is {outcome_type!r}; "
                f"expected one of {sorted(terminal_outcomes)}"
            )

        return errors


# ---------------------------------------------------------------------------
# Convenience: build a complete progress module
# ---------------------------------------------------------------------------

class ProgressModule:
    """Composes fingerprint computation, progress counting, duplicate detection,
    stagnation handling, and limit outcome emission."""

    def __init__(
        self,
        max_failures: int = StagnationHandler.DEFAULT_MAX_FAILURES,
    ) -> None:
        self.fingerprint_computer = ProgressFingerprintComputer()
        self.progress_counter = ProgressCounter()
        self.duplicate_detector = DuplicateDetector()
        self.stagnation_handler = StagnationHandler(max_failures=max_failures)
        self.limit_outcome_emitter = LimitOutcomeEmitter()

    def compute_cycle_fingerprint(
        self,
        cycle_id: str,
        run_id: str,
        graph_revision: int,
        jobs_completed: int,
        jobs_total: int,
        finding_signatures: list[str] | None = None,
        goal_gates: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        work_plan: dict[str, Any] | None = None,
        verification_findings: list[dict[str, Any]] | None = None,
        measurements: list[dict[str, Any]] | None = None,
        goal_decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compute a complete progress fingerprint for a cycle."""
        record = self.fingerprint_computer.build_fingerprint_record(
            finding_signatures=finding_signatures,
            goal_gates=goal_gates,
            hypotheses=hypotheses,
            synthesis=synthesis,
            work_plan=work_plan,
            verification_findings=verification_findings,
            measurements=measurements,
            goal_decisions=goal_decisions,
        )
        digest = self.fingerprint_computer.compute_fingerprint(record)
        fingerprint_id = stable_id("FP", cycle_id, run_id, digest[:16])

        findings_count = len(finding_signatures or [])
        return self.fingerprint_computer.to_schema_record(
            fingerprint_id=fingerprint_id,
            cycle_id=cycle_id,
            run_id=run_id,
            graph_revision=graph_revision,
            jobs_completed=jobs_completed,
            jobs_total=jobs_total,
            findings_count=findings_count,
            fingerprint_digest=digest,
        )

    def count_real_progress(
        self,
        goal_gates: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        previous_findings: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        measurements: list[dict[str, Any]] | None = None,
    ) -> int:
        """Count all real progress indicators."""
        return self.progress_counter.total_progress(
            goal_gates=goal_gates,
            findings=findings,
            previous_findings=previous_findings,
            hypotheses=hypotheses,
            synthesis=synthesis,
            measurements=measurements,
        )

    def check_and_emit_limit_outcome(
        self,
        graph_revision: int,
        graph_digest: str,
        limits_hit: bool,
        limit_reason: str | None = None,
        budget_type: str | None = None,
        consumed: float = 0.0,
        limit: float = 0.0,
        contradictions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Check if limits prevent continuation and emit appropriate outcome."""
        if not limits_hit:
            return {
                "outcome_type": OutcomeType.CONTINUE.value,
                "limits_hit": False,
            }

        if budget_type:
            outcome = self.limit_outcome_emitter.emit_budget_outcome(
                graph_revision=graph_revision,
                graph_digest=graph_digest,
                reason=limit_reason or "budget exhausted",
                budget_type=budget_type,
                consumed=consumed,
                limit=limit,
            )
        elif contradictions:
            outcome = self.limit_outcome_emitter.emit_infeasible_outcome(
                graph_revision=graph_revision,
                graph_digest=graph_digest,
                reason=limit_reason or "contradictions prevent success",
                contradictions=contradictions,
            )
        else:
            outcome = self.limit_outcome_emitter.emit_blocked_outcome(
                graph_revision=graph_revision,
                graph_digest=graph_digest,
                reason=limit_reason or "limits prevent continuation",
            )

        errors = self.limit_outcome_emitter.validate_no_false_success(
            outcome, limits_hit=True
        )
        if errors:
            raise OrchestratorError(
                f"limit outcome validation failed: {'; '.join(errors)}"
            )

        return outcome
