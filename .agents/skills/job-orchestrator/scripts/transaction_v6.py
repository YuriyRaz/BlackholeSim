"""Typed decision and expansion ingestion transactions for v6."""

from __future__ import annotations

import hashlib
import json
import os
import copy
import tempfile
import time
from pathlib import Path
from typing import Any

from orchestrator_core import (
    SCHEMA_VERSION,
    OrchestratorError,
    atomic_write,
    canonical_bytes,
    content_hash,
    load_json,
    stable_id,
    utc_now,
    validate_record,
    write_json,
)


class ResponseNormalizer:
    """Normalize role-specific typed decisions from worker responses."""

    VALID_WORKER_STATUSES = ("received", "normalizing", "visible", "complete", "blocked")

    VALID_GOAL_DECISIONS = (
        "GOAL_ACHIEVED", "CONTINUE", "BLOCKED", "INFEASIBLE",
        "BLOCKED_NO_PROGRESS", "BUDGET_EXHAUSTED",
    )

    VALID_HYPOTHESIS_STATUSES = ("supported", "refuted", "partial", "inconclusive", "blocked")

    VALID_SYNTHESIS_CONCLUSIONS = (
        "root_cause_identified", "partial_understanding",
        "no_actionable_cause", "needs_further_investigation",
    )

    VALID_WORK_PLAN_TYPES = ("direct_repair", "implementation_set", "openspec_batch")

    VALID_FINDING_SEVERITIES = ("critical", "high", "medium", "low", "info")

    VALID_FINDING_DISPOSITION_STATUSES = ("verified", "refuted", "superseded", "accepted_risk")

    VALID_OUTCOME_STATUSES = ("success", "failure", "partial", "cancelled")

    def normalize_execution_status(self, response: dict[str, Any]) -> dict[str, Any]:
        """Normalize a minimal worker execution status from a response."""
        status = response.get("status")
        if status not in self.VALID_WORKER_STATUSES:
            raise OrchestratorError(
                f"invalid execution status {status!r}; "
                f"must be one of {self.VALID_WORKER_STATUSES}"
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "response_id": response["response_id"],
            "status": status,
            "normalized_at": utc_now(),
        }

    def normalize_goal_decision(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Normalize a Goal Judge decision record."""
        decision = judgment.get("decision")
        if decision not in self.VALID_GOAL_DECISIONS:
            raise OrchestratorError(
                f"invalid goal decision {decision!r}; "
                f"must be one of {self.VALID_GOAL_DECISIONS}"
            )
        validate_record("goal-judgment", judgment)
        return {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": judgment["judgment_id"],
            "decision": decision,
            "graph_revision": judgment["graph_revision"],
            "normalized_at": utc_now(),
        }

    def normalize_hypothesis_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Normalize a hypothesis investigation result."""
        status = result.get("status")
        if status not in self.VALID_HYPOTHESIS_STATUSES:
            raise OrchestratorError(
                f"invalid hypothesis status {status!r}; "
                f"must be one of {self.VALID_HYPOTHESIS_STATUSES}"
            )
        validate_record("hypothesis-result", result)
        return {
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": result["hypothesis_result_id"],
            "status": status,
            "normalized_at": utc_now(),
        }

    def normalize_synthesis_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Normalize a synthesis result."""
        conclusion = result.get("conclusion")
        if conclusion not in self.VALID_SYNTHESIS_CONCLUSIONS:
            raise OrchestratorError(
                f"invalid synthesis conclusion {conclusion!r}; "
                f"must be one of {self.VALID_SYNTHESIS_CONCLUSIONS}"
            )
        validate_record("synthesis-result", result)
        return {
            "schema_version": SCHEMA_VERSION,
            "synthesis_id": result["synthesis_id"],
            "conclusion": conclusion,
            "normalized_at": utc_now(),
        }

    def normalize_work_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Normalize a work plan decision."""
        plan_type = plan.get("plan_type")
        if plan_type not in self.VALID_WORK_PLAN_TYPES:
            raise OrchestratorError(
                f"invalid work plan type {plan_type!r}; "
                f"must be one of {self.VALID_WORK_PLAN_TYPES}"
            )
        validate_record("work-plan", plan)
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": plan["plan_id"],
            "plan_type": plan_type,
            "normalized_at": utc_now(),
        }

    def normalize_expansion(self, expansion: dict[str, Any]) -> dict[str, Any]:
        """Normalize an expansion proposal."""
        validate_record("retained-expansion", expansion)
        return {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion["expansion_id"],
            "plan_id": expansion["plan_id"],
            "normalized_at": utc_now(),
        }

    def normalize_verification(self, result: dict[str, Any]) -> dict[str, Any]:
        """Normalize a verification result."""
        status = result.get("status")
        valid_statuses = ("passed", "failed", "unavailable")
        if status not in valid_statuses:
            raise OrchestratorError(
                f"invalid verification status {status!r}; "
                f"must be one of {valid_statuses}"
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "goal_gate_result_id": result.get("goal_gate_result_id"),
            "status": status,
            "normalized_at": utc_now(),
        }


class ExpansionIngester:
    """Accept expansion artifacts with authority and provenance validation."""

    def __init__(self, authority_store: dict[str, dict[str, Any]]) -> None:
        self._authority_store = authority_store

    def accept_expansion(
        self,
        expansion: dict[str, Any],
        current_authority_id: str,
        producer_job: dict[str, Any],
        response_receipt: dict[str, Any],
        graph_state: dict[str, Any],
        source_artifact_digest: str,
        authority_scope: dict[str, bool],
    ) -> dict[str, Any]:
        """Validate authority and bind provenance to an expansion artifact."""
        authority = self.validate_producer_authority(
            current_authority_id, authority_scope, producer_job, graph_state
        )
        expansion_kind = expansion.get("expansion_kind")
        allowed_kinds = authority["scope"].get("allowed_expansion_kinds", [])
        if expansion_kind is not None and expansion_kind not in allowed_kinds:
            raise OrchestratorError(
                f"expansion kind {expansion_kind!r} is outside authority scope"
            )
        provenance = self.bind_expansion_provenance(
            producer_job=producer_job,
            response_receipt=response_receipt,
            graph_state=graph_state,
            source_artifact_digest=source_artifact_digest,
            authority_id=current_authority_id,
            expansion=expansion,
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "expansion": expansion,
            "provenance": provenance,
            "accepted_at": utc_now(),
        }

    def validate_producer_authority(
        self,
        authority_id: str,
        authority_scope: dict[str, Any],
        producer_job: dict[str, Any] | None = None,
        graph_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check that the authority is current and has expansion scope."""
        authority = self._authority_store.get(authority_id)
        if authority is None:
            raise OrchestratorError(
                f"authority {authority_id!r} not found in authority store"
            )
        persisted_scope = authority.get("scope")
        if not isinstance(persisted_scope, dict):
            raise OrchestratorError(
                f"authority {authority_id!r} has no persisted scope"
            )
        if authority_scope != persisted_scope:
            raise OrchestratorError(
                f"expansion scope for {authority_id!r} does not match persisted authority scope"
            )
        if not persisted_scope.get("expansion", False):
            raise OrchestratorError(
                f"authority {authority_id!r} does not have expansion scope"
            )
        if producer_job is not None and authority.get("job_identity") not in {
            None, producer_job.get("job_id")
        }:
            raise OrchestratorError(
                f"authority {authority_id!r} is bound to another producer job"
            )
        if graph_state is not None:
            current = graph_state.get("active_planning_authority_id")
            if current is not None and current != authority_id:
                raise OrchestratorError(
                    f"authority {authority_id!r} is not current; current authority is {current!r}"
                )
        expires_at = authority.get("expires_at")
        if expires_at and expires_at < utc_now():
            raise OrchestratorError(
                f"authority {authority_id!r} has expired at {expires_at}"
            )
        return authority

    def bind_expansion_provenance(
        self,
        producer_job: dict[str, Any],
        response_receipt: dict[str, Any],
        graph_state: dict[str, Any],
        source_artifact_digest: str,
        authority_id: str,
        expansion: dict[str, Any],
    ) -> dict[str, Any]:
        """Bind job, attempt, receipt, graph revision/digest, artifact digest, and authority scope."""
        return {
            "producer_job_id": producer_job["job_id"],
            "producer_attempt_id": response_receipt.get(
                "attempt_id", producer_job.get("attempt_id", "UNKNOWN")
            ),
            "response_id": response_receipt.get(
                "response_id", response_receipt.get("receipt_id", "UNKNOWN")
            ),
            "authority_id": authority_id,
            "cycle_id": producer_job.get("cycle_id", "UNKNOWN"),
            "response_receipt_digest": content_hash(response_receipt),
            "graph_revision": graph_state.get("graph_revision", 0),
            "graph_digest": graph_state.get("graph_digest", "0" * 64),
            "source_artifact_digest": source_artifact_digest,
            "authority_scope_digest": content_hash(
                self._authority_store[authority_id]["scope"]
            ),
            "validation_result": "accepted",
        }


class ExpansionRetainer:
    """Retain canonical expansion bytes immutably under a control-plane identity."""

    def __init__(self, expansion_store: dict[str, dict[str, Any]] | None = None) -> None:
        self._expansion_store: dict[str, dict[str, Any]] = expansion_store or {}
        self._identity_index: dict[str, str] = {}

    def retain_expansion(self, expansion: dict[str, Any]) -> dict[str, Any]:
        """Store canonical bytes and return the retained expansion record."""
        canonical = canonical_bytes(expansion)
        digest = hashlib.sha256(canonical).hexdigest()
        plan_id = expansion.get("plan_id", "UNKNOWN")
        campaign_id = expansion.get("campaign_id", "UNKNOWN")
        expansion_id = stable_id("EXP", plan_id, campaign_id, digest)
        if expansion_id in self._expansion_store:
            return self.make_idempotent(expansion_id)
        provenance = expansion.get("provenance", {})
        record = {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion_id,
            "plan_id": plan_id,
            "campaign_id": campaign_id,
            "graph_revision": expansion.get("graph_revision", 1),
            "jobs_added": expansion.get("jobs_added", []),
            "edges_added": expansion.get("edges_added", []),
            "provenance": {
                "producer_job_id": provenance.get("producer_job_id", "UNKNOWN"),
                "authority_id": provenance.get("authority_id", "UNKNOWN"),
                "cycle_id": provenance.get("cycle_id", "UNKNOWN"),
            },
            "created_at": utc_now(),
            "canonical_digest": digest,
        }
        self._expansion_store[expansion_id] = record
        self._identity_index[expansion_id] = expansion_id
        return record

    def make_idempotent(self, expansion_id: str) -> dict[str, Any]:
        """Return the existing record if the expansion is a replay."""
        existing = self._expansion_store.get(expansion_id)
        if existing is None:
            raise OrchestratorError(
                f"expansion {expansion_id!r} not found for idempotent replay"
            )
        return existing

    def reject_conflicting_reuse(
        self, expansion_id: str, new_canonical_digest: str
    ) -> None:
        """Reject if a different canonical digest is provided for an existing identity."""
        existing = self._expansion_store.get(expansion_id)
        if existing is not None:
            existing_digest = existing.get("canonical_digest")
            if existing_digest != new_canonical_digest:
                raise OrchestratorError(
                    f"conflicting identity reuse for expansion {expansion_id!r}: "
                    f"expected digest {existing_digest!r}, got {new_canonical_digest!r}"
                )


class GoalDecisionProcessor:
    """Process typed Goal Judge decisions with authority and graph-revision checks."""

    SEALING_DECISIONS = (
        "GOAL_ACHIEVED", "BLOCKED", "INFEASIBLE",
        "BLOCKED_NO_PROGRESS", "BUDGET_EXHAUSTED",
    )
    TERMINAL_DECISIONS = SEALING_DECISIONS

    def __init__(
        self,
        current_judge_id: str | None = None,
        current_graph_revision: int = 0,
    ) -> None:
        self._current_judge_id = current_judge_id
        self._current_graph_revision = current_graph_revision

    def process_goal_achieved(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Validate and seal a GOAL_ACHIEVED decision."""
        self.validate_goal_authority(judgment)
        return self._seal_decision(judgment, "completed")

    def process_continue(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Keep graph open, commit expansion for CONTINUE."""
        self.validate_goal_authority(judgment)
        return {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": judgment["judgment_id"],
            "decision": "CONTINUE",
            "outcome": "graph_open",
            "sealed": False,
            "processed_at": utc_now(),
        }

    def process_blocked(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Seal with blocked outcome."""
        self.validate_goal_authority(judgment)
        return self._seal_decision(judgment, "blocked")

    def process_infeasible(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Seal with infeasible outcome."""
        self.validate_goal_authority(judgment)
        return self._seal_decision(judgment, "infeasible")

    def process_blocked_no_progress(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Seal with no-progress outcome."""
        self.validate_goal_authority(judgment)
        return self._seal_decision(judgment, "blocked_no_progress")

    def process_budget_exhausted(self, judgment: dict[str, Any]) -> dict[str, Any]:
        """Seal with budget outcome."""
        self.validate_goal_authority(judgment)
        return self._seal_decision(judgment, "budget_exhausted")

    def validate_goal_authority(self, judgment: dict[str, Any]) -> None:
        """Check current Judge identity and graph revision match."""
        producer_job_id = judgment.get("producer_job_id")
        graph_revision = judgment.get("graph_revision")
        if self._current_judge_id is not None and producer_job_id != self._current_judge_id:
            raise OrchestratorError(
                f"producer_job_id {producer_job_id!r} does not match "
                f"current judge {self._current_judge_id!r}"
            )
        if (
            self._current_graph_revision > 0
            and graph_revision is not None
            and graph_revision != self._current_graph_revision
        ):
            raise OrchestratorError(
                f"graph_revision {graph_revision} does not match "
                f"current revision {self._current_graph_revision}"
            )

    def _seal_decision(self, judgment: dict[str, Any], outcome: str) -> dict[str, Any]:
        """Create a sealed decision record."""
        return {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": judgment["judgment_id"],
            "decision": judgment["decision"],
            "outcome": outcome,
            "sealed": True,
            "processed_at": utc_now(),
        }


class ResultProcessor:
    """Process typed hypothesis, synthesis, work-plan, finding, progress, and review results."""

    def __init__(self) -> None:
        self._result_store: dict[str, dict[str, Any]] = {}
        self._disposition_log: list[dict[str, Any]] = []

    def process_hypothesis_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Process a hypothesis result with a stable identity."""
        validate_record("hypothesis-result", result)
        stable = stable_id(
            "HYPRES",
            result["finding_id"],
            result["producer_job_id"],
            result["status"],
        ).upper()
        stored = {
            "schema_version": SCHEMA_VERSION,
            "hypothesis_result_id": stable,
            "finding_id": result["finding_id"],
            "producer_job_id": result["producer_job_id"],
            "cycle_id": result["cycle_id"],
            "status": result["status"],
            "evidence_refs": result.get("evidence_refs", []),
            "recorded_at": utc_now(),
        }
        self._result_store[stable] = stored
        return stored

    def process_synthesis_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Process a synthesis result with a stable identity."""
        validate_record("synthesis-result", result)
        stable = stable_id(
            "SYNRES",
            result["producer_job_id"],
            result["conclusion"],
            str(sorted(result.get("hypothesis_result_ids", []))),
        )
        stored = {
            "schema_version": SCHEMA_VERSION,
            "synthesis_id": stable,
            "hypothesis_result_ids": result.get("hypothesis_result_ids", []),
            "producer_job_id": result["producer_job_id"],
            "cycle_id": result["cycle_id"],
            "conclusion": result["conclusion"],
            "evidence_refs": result.get("evidence_refs", []),
            "summary": result.get("summary", ""),
            "recorded_at": utc_now(),
        }
        self._result_store[stable] = stored
        return stored

    def process_work_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Process a work plan with a stable identity."""
        validate_record("work-plan", plan)
        stable = stable_id(
            "WRKPLN",
            plan["plan_type"],
            plan["producer_job_id"],
            str(sorted(
                t.get("target_id", "")
                for t in plan.get("targets", [])
            )),
        )
        stored = {
            "schema_version": SCHEMA_VERSION,
            "plan_id": stable,
            "plan_type": plan["plan_type"],
            "cycle_id": plan["cycle_id"],
            "producer_job_id": plan["producer_job_id"],
            "targets": plan.get("targets", []),
            "recorded_at": utc_now(),
        }
        self._result_store[stable] = stored
        return stored

    def process_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        """Process a finding with an append-only disposition."""
        validate_record("finding", finding)
        disposition = {
            "schema_version": SCHEMA_VERSION,
            "disposition_id": stable_id(
                "FNDISP",
                finding["finding_id"],
                finding["producer_job_id"],
            ),
            "finding_id": finding["finding_id"],
            "producer_job_id": finding["producer_job_id"],
            "producer_role": finding["producer_role"],
            "cycle_id": finding["cycle_id"],
            "status": "accepted_risk",
            "evidence_refs": [
                e.get("ref", "") for e in finding.get("evidence", [])
            ],
            "reason": finding.get("description", ""),
            "recorded_at": utc_now(),
        }
        self._disposition_log.append(disposition)
        return disposition

    def process_progress(self, progress: dict[str, Any]) -> dict[str, Any]:
        """Process a progress record with a stable identity."""
        stable = stable_id(
            "PROG",
            progress.get("run_id", "UNKNOWN"),
            str(progress.get("graph_revision", 0)),
            str(progress.get("jobs_completed", 0)),
        )
        stored = {
            "schema_version": SCHEMA_VERSION,
            "progress_id": stable,
            "run_id": progress.get("run_id", "UNKNOWN"),
            "graph_revision": progress.get("graph_revision", 0),
            "jobs_completed": progress.get("jobs_completed", 0),
            "jobs_total": progress.get("jobs_total", 0),
            "recorded_at": utc_now(),
        }
        self._result_store[stable] = stored
        return stored

    def process_review(self, review: dict[str, Any]) -> dict[str, Any]:
        """Process a review result with a stable identity."""
        stable = stable_id(
            "REVIEW",
            review.get("producer_job_id", "UNKNOWN"),
            review.get("cycle_id", "UNKNOWN"),
            review.get("status", "UNKNOWN"),
        )
        stored = {
            "schema_version": SCHEMA_VERSION,
            "review_id": stable,
            "producer_job_id": review.get("producer_job_id", "UNKNOWN"),
            "cycle_id": review.get("cycle_id", "UNKNOWN"),
            "status": review.get("status", "UNKNOWN"),
            "recorded_at": utc_now(),
        }
        self._result_store[stable] = stored
        return stored


class CorrectionGenerator:
    """Generate same-session correction prompts for invalid decisions."""

    MAX_DECISION_LENGTH = 10000
    MAX_EVIDENCE_REFS = 100

    def generate_correction_prompt(self, errors: list[str], context: str = "") -> str:
        """Generate a correction prompt listing all validation errors."""
        lines = ["CORRECTION_REQUIRED"]
        if context:
            lines.append(f"Context: {context}")
        lines.append("Errors found:")
        for i, error in enumerate(errors, 1):
            lines.append(f"  {i}. {error}")
        lines.append("Please resubmit with corrections. Do not repeat domain side effects.")
        return "\n".join(lines)

    def validate_decision_format(self, decision: dict[str, Any]) -> list[str]:
        """Check the format of a decision record, returning any errors."""
        errors: list[str] = []
        if not isinstance(decision, dict):
            errors.append("decision must be a JSON object")
            return errors
        if "schema_version" not in decision:
            errors.append("missing required field: schema_version")
        elif decision["schema_version"] != SCHEMA_VERSION:
            errors.append(
                f"schema_version must be {SCHEMA_VERSION}, got {decision['schema_version']}"
            )
        for field in ("producer_job_id", "cycle_id", "recorded_at"):
            if field not in decision:
                errors.append(f"missing required field: {field}")
        return errors

    def validate_decision_authority(
        self,
        decision: dict[str, Any],
        expected_producer: str | None = None,
    ) -> list[str]:
        """Check authority of a decision, returning any errors."""
        errors: list[str] = []
        producer = decision.get("producer_job_id")
        if expected_producer is not None and producer != expected_producer:
            errors.append(
                f"unauthorized producer: expected {expected_producer!r}, got {producer!r}"
            )
        return errors

    def validate_decision_staleness(
        self,
        decision: dict[str, Any],
        current_graph_revision: int,
    ) -> list[str]:
        """Check freshness of a decision against current graph revision."""
        errors: list[str] = []
        graph_revision = decision.get("graph_revision")
        if graph_revision is not None and graph_revision < current_graph_revision:
            errors.append(
                f"stale decision: graph_revision {graph_revision} < "
                f"current {current_graph_revision}"
            )
        return errors

    def validate_decision_limits(self, decision: dict[str, Any]) -> list[str]:
        """Check size and count limits of a decision."""
        errors: list[str] = []
        for field in ("reason", "rationale", "summary", "description"):
            value = decision.get(field)
            if isinstance(value, str) and len(value) > self.MAX_DECISION_LENGTH:
                errors.append(
                    f"field {field!r} exceeds maximum length {self.MAX_DECISION_LENGTH}"
                )
        evidence = decision.get("evidence_refs", [])
        if isinstance(evidence, list) and len(evidence) > self.MAX_EVIDENCE_REFS:
            errors.append(
                f"evidence_refs count {len(evidence)} exceeds maximum {self.MAX_EVIDENCE_REFS}"
            )
        return errors

    def validate_decision_semantics(self, decision: dict[str, Any]) -> list[str]:
        """Check semantic validity of a decision."""
        errors: list[str] = []
        decision_type = decision.get("decision") or decision.get("decision_type")
        if decision_type is not None:
            valid_goal_decisions = (
                "GOAL_ACHIEVED", "CONTINUE", "BLOCKED", "INFEASIBLE",
                "BLOCKED_NO_PROGRESS", "BUDGET_EXHAUSTED",
            )
            valid_strategy_decisions = (
                "expand", "repair", "verify", "synthesize", "terminate", "redirect",
            )
            valid_outcome_statuses = ("success", "failure", "partial", "cancelled")
            all_valid = (
                set(valid_goal_decisions)
                | set(valid_strategy_decisions)
                | set(valid_outcome_statuses)
            )
            if decision_type not in all_valid:
                errors.append(
                    f"invalid decision type {decision_type!r}"
                )
        evidence_refs = decision.get("evidence_refs", [])
        if isinstance(evidence_refs, list):
            import re
            pattern = re.compile(r"^run://[^/]+/(jobs|graph|campaign)/.+")
            for ref in evidence_refs:
                if isinstance(ref, str) and not pattern.match(ref):
                    errors.append(
                        f"invalid evidence ref format: {ref!r}"
                    )
        return errors


# ---------------------------------------------------------------------------
# Task 6.2: Expansion staging
# ---------------------------------------------------------------------------

class ExpansionStager:
    """Stage an expansion: assign canonical identities, render prompts,
    construct every prospective record, write exact staged bytes, and
    hash the complete transaction."""

    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = staging_dir
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def stage_expansion(
        self,
        expansion: dict[str, Any],
        graph_state: dict[str, Any],
        plan_digest: str,
        run_id: str,
        decision_id: str,
    ) -> dict[str, Any]:
        """Assign canonical identities, render prompts, construct records.

        Returns a staging manifest with all prospective records, their
        identities, and the staged-bytes digest.
        """
        from graph_v6 import (
            generate_expansion_id,
            generate_global_job_id,
            generate_batch_id,
        )

        expansion_id = generate_expansion_id(run_id, decision_id, plan_digest)
        graph_revision = graph_state.get("graph_revision", 1)

        prospective_jobs: list[dict[str, Any]] = []
        job_id_map: dict[str, str] = {}
        for local_job in expansion.get("jobs_added", []):
            local_id = local_job.get("job_id", stable_id("LJOB", expansion_id, local_job.get("role", "")))
            global_id = generate_global_job_id(run_id, expansion_id, local_id)
            job_id_map[local_id] = global_id
            job_record = {
                "schema_version": SCHEMA_VERSION,
                "job_id": global_id,
                "title": local_job.get("title", f"{local_job.get('role', 'unknown')}-{local_id}"),
                "prompt_path": f"prompts/{global_id}.md",
                "role": local_job.get("role", "implementation"),
                "purpose_key": local_job.get("purpose_key", "unknown"),
                "graph_generation": graph_state.get("graph_generation", 1),
                "expansion_origin": local_job.get("expansion_origin", "ROOT"),
                "authority_id": local_job.get("authority_id", "UNKNOWN"),
                "context_snapshot_id": local_job.get("context_snapshot_id", stable_id("CTX", expansion_id, local_id)),
                "activation_id": local_job.get("activation_id", stable_id("ACT", expansion_id, local_id)),
                "created_at": utc_now(),
            }
            prospective_jobs.append(job_record)

        prospective_edges: list[dict[str, Any]] = []
        for local_edge in expansion.get("edges_added", []):
            source_local = local_edge.get("source_job_id", "")
            target_local = local_edge.get("target_job_id", "")
            source_global = job_id_map.get(source_local, source_local)
            target_global = job_id_map.get(target_local, target_local)
            edge_id = stable_id("EDGE", expansion_id, source_global, target_global).upper()
            edge_record = {
                "schema_version": SCHEMA_VERSION,
                "edge_id": edge_id,
                "source_job_id": source_global,
                "target_job_id": target_global,
                "edge_type": local_edge.get("edge_type", "success"),
                "graph_revision": graph_revision,
                "created_at": utc_now(),
            }
            prospective_edges.append(edge_record)

        staging_manifest = {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion_id,
            "plan_digest": plan_digest,
            "graph_revision": graph_revision,
            "prospective_jobs": prospective_jobs,
            "prospective_edges": prospective_edges,
            "staged_at": utc_now(),
        }
        return staging_manifest

    def write_staged_bytes(
        self,
        staging_manifest: dict[str, Any],
        expansion_id: str,
    ) -> str:
        """Write exact staged bytes to the staging area.

        Returns the SHA-256 digest of the staged bytes.
        """
        canonical = canonical_bytes(staging_manifest)
        digest = hashlib.sha256(canonical).hexdigest()
        staged_path = self._staging_dir / f"{expansion_id}.staged.json"
        atomic_write(staged_path, canonical)
        return digest

    def hash_transaction(self, staging_manifest: dict[str, Any]) -> str:
        """Hash the complete staged transaction."""
        canonical = canonical_bytes(staging_manifest)
        return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Task 6.3: Transaction manifest persistence and visibility commit
# ---------------------------------------------------------------------------

class TransactionManifest:
    """Durable expansion transaction manifest.

    Persisted after staging and before graph visibility commit. The run
    graph revision update is the final graph visibility commit point.
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._manifest_dir = manifest_dir
        self._manifest_dir.mkdir(parents=True, exist_ok=True)

    def persist_manifest(
        self,
        expansion_id: str,
        staging_manifest: dict[str, Any],
        staged_bytes_digest: str,
        transaction_digest: str,
        graph_revision_before: int,
    ) -> dict[str, Any]:
        """Write a durable manifest to disk."""
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion_id,
            "plan_digest": staging_manifest.get("plan_digest", ""),
            "staged_bytes_digest": staged_bytes_digest,
            "transaction_digest": transaction_digest,
            "graph_revision_before": graph_revision_before,
            "staging_manifest": staging_manifest,
            "status": "staged",
            "persisted_at": utc_now(),
        }
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        write_json(manifest_path, manifest)
        return manifest

    def load_manifest(self, expansion_id: str) -> dict[str, Any]:
        """Load a persisted manifest."""
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        return load_json(manifest_path)

    def manifest_exists(self, expansion_id: str) -> bool:
        """Check if a manifest exists for the given expansion."""
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        return manifest_path.exists()

    def commit_visibility(
        self,
        expansion_id: str,
        graph_state_path: Path,
        staging_manifest: dict[str, Any],
    ) -> int:
        """Update graph revision as the final visibility commit point.

        Returns the new graph revision.
        """
        from graph_v6 import GraphState, add_job_to_graph, add_edge_to_graph, advance_graph_revision

        gs = GraphState.load(graph_state_path)

        for job in staging_manifest.get("prospective_jobs", []):
            graph_job = {k: v for k, v in job.items() if k not in ("activation_id", "context_snapshot_id")}
            job_id = graph_job.get("job_id")
            if job_id and job_id not in gs._jobs:
                add_job_to_graph(gs, graph_job)
        for edge in staging_manifest.get("prospective_edges", []):
            edge_id = edge.get("edge_id")
            if edge_id and edge_id not in gs._edges:
                add_edge_to_graph(gs, edge)

        new_revision = advance_graph_revision(gs)
        gs.save(graph_state_path)

        run_path = graph_state_path.parent.parent / "run.json"
        if run_path.exists():
            run = load_json(run_path)
            existing_ids = run.get("job_ids", [])
            for job in staging_manifest.get("prospective_jobs", []):
                job_id = job.get("job_id")
                if job_id and job_id not in existing_ids:
                    existing_ids.append(job_id)
            run["job_ids"] = existing_ids
            run["graph_revision"] = new_revision
            run["graph_digest"] = gs.graph_digest
            run["updated_at"] = utc_now()
            write_json(run_path, run)

        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        if manifest_path.exists():
            manifest = load_json(manifest_path)
            manifest["status"] = "committed"
            manifest["graph_revision_after"] = new_revision
            manifest["committed_at"] = utc_now()
            write_json(manifest_path, manifest)

        return new_revision


# ---------------------------------------------------------------------------
# Task 6.4: Idempotent commit-expansion compare-and-swap
# ---------------------------------------------------------------------------

class ExpansionCommitter:
    """Idempotent compare-and-swap commit for expansion transactions.

    Uses retained plan bytes, expected graph revision/digest,
    expansion identity, and plan digest for the CAS check.
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._manifest_dir = manifest_dir

    def validate_cas(
        self,
        expected_graph_revision: int,
        expected_graph_digest: str,
        actual_graph_revision: int,
        actual_graph_digest: str,
        expansion_id: str,
        plan_digest: str,
        manifest: dict[str, Any],
    ) -> list[str]:
        """Check expected vs actual graph state.

        Returns error list (empty = valid).
        """
        errors: list[str] = []
        if manifest.get("expansion_id") != expansion_id:
            errors.append(
                f"expansion_id mismatch: expected {expansion_id!r}, "
                f"got {manifest.get('expansion_id')!r}"
            )
        if manifest.get("plan_digest") != plan_digest:
            errors.append(
                f"plan_digest mismatch: expected {plan_digest!r}, "
                f"got {manifest.get('plan_digest')!r}"
            )
        if actual_graph_revision != expected_graph_revision:
            errors.append(
                f"graph_revision mismatch: expected {expected_graph_revision}, "
                f"got {actual_graph_revision}"
            )
        if actual_graph_digest != expected_graph_digest:
            errors.append(
                f"graph_digest mismatch: expected {expected_graph_digest[:16]}..., "
                f"got {actual_graph_digest[:16]}..."
            )
        return errors

    def commit_expansion(
        self,
        expansion_id: str,
        plan_digest: str,
        expected_graph_revision: int,
        expected_graph_digest: str,
        graph_state_path: Path,
        staging_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare-and-swap commit. Returns the commit result."""
        from graph_v6 import GraphState, compute_graph_digest

        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        if not manifest_path.exists():
            raise OrchestratorError(
                f"no manifest found for expansion {expansion_id!r}"
            )
        manifest = load_json(manifest_path)

        if manifest.get("status") == "committed":
            return self.idempotent_commit(expansion_id, manifest)

        gs = GraphState.load(graph_state_path)
        actual_revision = gs.graph_revision
        actual_digest = compute_graph_digest(gs)

        errors = self.validate_cas(
            expected_graph_revision=expected_graph_revision,
            expected_graph_digest=expected_graph_digest,
            actual_graph_revision=actual_revision,
            actual_graph_digest=actual_digest,
            expansion_id=expansion_id,
            plan_digest=plan_digest,
            manifest=manifest,
        )
        if errors:
            raise OrchestratorError(
                f"CAS validation failed for {expansion_id!r}: {'; '.join(errors)}"
            )

        from transaction_v6 import TransactionManifest
        tx_manifest = TransactionManifest(self._manifest_dir)
        new_revision = tx_manifest.commit_visibility(
            expansion_id=expansion_id,
            graph_state_path=graph_state_path,
            staging_manifest=staging_manifest,
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion_id,
            "status": "committed",
            "graph_revision": new_revision,
            "committed_at": utc_now(),
        }

    def idempotent_commit(
        self,
        expansion_id: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        """Return existing result on replay."""
        return {
            "schema_version": SCHEMA_VERSION,
            "expansion_id": expansion_id,
            "status": "committed",
            "graph_revision": manifest.get("graph_revision_after", 0),
            "committed_at": manifest.get("committed_at", utc_now()),
            "idempotent_replay": True,
        }


# ---------------------------------------------------------------------------
# Task 6.5: Roll-forward recovery
# ---------------------------------------------------------------------------

class ExpansionRecovery:
    """Recover from crashes at every expansion transaction boundary.

    Handles: before writes, during partial writes, after graph visibility
    commit, and before cleanup. Blocks on contradictory bytes.
    """

    def __init__(
        self,
        staging_dir: Path,
        manifest_dir: Path,
        graph_state_path: Path,
    ) -> None:
        self._staging_dir = staging_dir
        self._manifest_dir = manifest_dir
        self._graph_state_path = graph_state_path

    def recover_from_crash(self, expansion_id: str) -> dict[str, Any]:
        """Roll forward from staged bytes.

        Determines the recovery phase and completes the transaction.
        """
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        staged_path = self._staging_dir / f"{expansion_id}.staged.json"

        has_manifest = manifest_path.exists()
        has_staged = staged_path.exists()

        if not has_manifest and not has_staged:
            return {
                "recovery_action": "nothing_to_recover",
                "expansion_id": expansion_id,
                "reason": "no manifest or staged bytes found",
            }

        if has_staged and not has_manifest:
            staged_bytes = staged_path.read_bytes()
            staged_digest = hashlib.sha256(staged_bytes).hexdigest()
            staging_manifest = json.loads(staged_bytes)
            return {
                "recovery_action": "replay_staging",
                "expansion_id": expansion_id,
                "staged_bytes_digest": staged_digest,
                "staging_manifest": staging_manifest,
                "reason": "staged bytes exist but no manifest",
            }

        manifest = load_json(manifest_path)
        status = manifest.get("status", "unknown")

        if status == "staged":
            return self._recover_after_manifest(expansion_id, manifest)

        if status == "committed":
            return {
                "recovery_action": "cleanup",
                "expansion_id": expansion_id,
                "manifest": manifest,
                "reason": "visibility committed, cleanup pending",
            }

        return {
            "recovery_action": "unknown_status",
            "expansion_id": expansion_id,
            "status": status,
            "reason": f"unknown manifest status: {status!r}",
        }

    def _recover_after_manifest(
        self,
        expansion_id: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        """Complete recovery after manifest was persisted but before commit."""
        from graph_v6 import GraphState, compute_graph_digest
        from transaction_v6 import TransactionManifest

        gs = GraphState.load(self._graph_state_path)
        staging_manifest = manifest.get("staging_manifest", {})

        tx_manifest = TransactionManifest(self._manifest_dir)
        new_revision = tx_manifest.commit_visibility(
            expansion_id=expansion_id,
            graph_state_path=self._graph_state_path,
            staging_manifest=staging_manifest,
        )

        return {
            "recovery_action": "committed",
            "expansion_id": expansion_id,
            "graph_revision": new_revision,
            "reason": "completed commit after manifest persisted",
        }

    def validate_manifest(self, expansion_id: str) -> list[str]:
        """Check manifest integrity. Returns error list."""
        errors: list[str] = []
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        staged_path = self._staging_dir / f"{expansion_id}.staged.json"

        if not manifest_path.exists():
            errors.append(f"manifest not found for {expansion_id!r}")
            return errors

        manifest = load_json(manifest_path)

        if manifest.get("expansion_id") != expansion_id:
            errors.append("expansion_id mismatch in manifest")

        staged_bytes_digest = manifest.get("staged_bytes_digest", "")
        if staged_path.exists():
            staged_bytes = staged_path.read_bytes()
            actual_digest = hashlib.sha256(staged_bytes).hexdigest()
            if staged_bytes_digest != actual_digest:
                errors.append(
                    f"staged bytes digest mismatch: manifest={staged_bytes_digest[:16]}..., "
                    f"actual={actual_digest[:16]}..."
                )
        elif manifest.get("status") != "committed":
            errors.append("staged bytes missing for non-committed manifest")

        return errors

    def block_contradictory(self, expansion_id: str) -> list[str]:
        """Block on contradictory bytes.

        Returns error list if contradictory state detected (empty = clean).
        """
        errors: list[str] = []
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        staged_path = self._staging_dir / f"{expansion_id}.staged.json"

        if not manifest_path.exists() or not staged_path.exists():
            return errors

        manifest = load_json(manifest_path)
        staged_bytes = staged_path.read_bytes()
        staged_digest = hashlib.sha256(staged_bytes).hexdigest()

        manifest_digest = manifest.get("staged_bytes_digest", "")
        if manifest_digest and manifest_digest != staged_digest:
            errors.append(
                f"contradictory staged bytes for {expansion_id!r}: "
                f"manifest says {manifest_digest[:16]}..., "
                f"file says {staged_digest[:16]}..."
            )

        staging_manifest = manifest.get("staging_manifest", {})
        manifest_expansion_id = staging_manifest.get("expansion_id", "")
        if manifest_expansion_id and manifest_expansion_id != expansion_id:
            errors.append(
                f"contradictory expansion_id: manifest={manifest_expansion_id!r}, "
                f"expected={expansion_id!r}"
            )

        return errors

    def cleanup(self, expansion_id: str) -> None:
        """Remove staged bytes and manifest after successful recovery."""
        manifest_path = self._manifest_dir / f"{expansion_id}.manifest.json"
        staged_path = self._staging_dir / f"{expansion_id}.staged.json"
        for path in (manifest_path, staged_path):
            if path.exists():
                path.unlink()


class MutationLock:
    """Cross-platform exclusive process lock for one run's mutations."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stream: Any = None

    def __enter__(self) -> MutationLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self._path.open("a+b")
        self._stream.seek(0)
        if self._stream.read(1) == b"":
            self._stream.seek(0)
            self._stream.write(b"0")
            self._stream.flush()
        self._stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, PermissionError) as exc:
            self._stream.close()
            self._stream = None
            raise OrchestratorError("another control-plane mutation owns the run lock") from exc
        return self

    def __exit__(self, *_args: Any) -> None:
        if self._stream is None:
            return
        self._stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None


def _json_file_bytes(value: Any) -> bytes:
    """Match write_json while allowing exact bytes to be staged and hashed."""
    try:
        return (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OrchestratorError(f"cannot stage non-JSON transaction data: {exc}") from exc


class DurableExpansionTransaction:
    """Production retained-plan expansion transaction used by jobctl.

    Every destination is staged with its exact digest before a durable manifest
    is published. Graph files may be rolled forward safely because run.json is
    written last and is the only scheduling visibility point.
    """

    def __init__(self, run_root: Path, fault_at: str | None = None) -> None:
        self.run_root = run_root
        self.fault_at = fault_at
        self.graph_path = run_root / "graph" / "graph.json"
        self.run_path = run_root / "run.json"

    def commit(
        self,
        expansion_id: str,
        plan_digest: str,
        expected_graph_revision: int,
        expected_graph_digest: str,
    ) -> dict[str, Any]:
        with MutationLock(self.run_root / "control" / "mutation.lock"):
            return self._commit_locked(
                expansion_id,
                plan_digest,
                expected_graph_revision,
                expected_graph_digest,
            )

    def _commit_locked(
        self,
        expansion_id: str,
        plan_digest: str,
        expected_graph_revision: int,
        expected_graph_digest: str,
    ) -> dict[str, Any]:
        from graph_v6 import GraphState, compute_graph_digest

        if not self.run_path.exists() or not self.graph_path.exists():
            raise OrchestratorError(f"run or graph state not found: {self.run_root}")
        run = load_json(self.run_path)
        graph = GraphState.load(self.graph_path)
        retained, plan, exact_plan = self._load_retained(
            expansion_id, plan_digest, expected_graph_revision, expected_graph_digest
        )
        manifest_path = self._manifest_path(expansion_id)
        manifest = load_json(manifest_path) if manifest_path.exists() else None
        if manifest is not None:
            self._validate_manifest_binding(
                manifest, expansion_id, plan_digest, expected_graph_revision, expected_graph_digest
            )

        committed = graph._expansions.get(expansion_id)
        if committed is not None:
            if committed.get("plan_digest") != plan_digest:
                raise OrchestratorError(
                    f"conflicting identity reuse for committed expansion {expansion_id!r}"
                )
            visible = (
                run.get("graph_revision") == graph.graph_revision
                and run.get("graph_digest") == graph.graph_digest
            )
            if not visible:
                if manifest is None:
                    raise OrchestratorError(
                        "committed expansion has no durable manifest for roll-forward"
                    )
                if (
                    run.get("graph_revision") != manifest["expected_graph_revision"]
                    or run.get("graph_digest") != manifest["expected_graph_digest"]
                    or graph.graph_revision != manifest["graph_revision_after"]
                    or graph.graph_digest != manifest["graph_digest_after"]
                ):
                    raise OrchestratorError("partial expansion state contradicts its durable manifest")
                self._verify_staged_files(manifest)
                self._apply_files(manifest, visibility=False)
                self._apply_files(manifest, visibility=True)
                run = load_json(self.run_path)
                visible = (
                    run.get("graph_revision") == graph.graph_revision
                    and run.get("graph_digest") == graph.graph_digest
                )
            if not visible:
                raise OrchestratorError("expansion roll-forward did not reach visibility")
            self._finalize_metadata(expansion_id, retained, graph)
            return self._result(graph, committed.get("job_mapping", []), committed.get("edge_mapping", []), True)

        self._validate_base(
            run,
            graph,
            retained,
            plan,
            exact_plan,
            expected_graph_revision,
            expected_graph_digest,
        )

        if manifest is None:
            manifest = self._stage(
                run, graph, retained, plan, exact_plan, expansion_id, plan_digest
            )
            self._fault("after_staging")
            atomic_write(manifest_path, _json_file_bytes(manifest))
            self._fault("after_manifest")

        self._verify_staged_files(manifest)
        self._apply_files(manifest, visibility=False)
        self._fault("before_visibility")
        self._apply_files(manifest, visibility=True)
        self._fault("after_visibility")

        visible_graph = GraphState.load(self.graph_path)
        self._fault("before_cleanup")
        self._finalize_metadata(expansion_id, retained, visible_graph)
        return self._result(
            visible_graph,
            manifest["job_mapping"],
            manifest["edge_mapping"],
            False,
        )

    def _load_retained(
        self,
        expansion_id: str,
        plan_digest: str,
        expected_graph_revision: int,
        expected_graph_digest: str,
    ) -> tuple[dict[str, Any], dict[str, Any], bytes]:
        retained_dir = self.run_root / "transactions" / "retained"
        record_path = retained_dir / f"{expansion_id}.json"
        plan_path = retained_dir / f"{expansion_id}.plan.json"
        if not record_path.exists() or not plan_path.exists():
            raise OrchestratorError(
                f"retained provenance or exact plan bytes not found for expansion {expansion_id}"
            )
        retained = load_json(record_path)
        exact = plan_path.read_bytes()
        if retained.get("expansion_id") != expansion_id:
            raise OrchestratorError("retained expansion identity mismatch")
        if retained.get("plan_digest") != plan_digest or retained.get("canonical_digest") != plan_digest:
            raise OrchestratorError("retained plan digest mismatch")
        if retained.get("base_graph_revision") != expected_graph_revision:
            raise OrchestratorError("retained graph revision mismatch")
        if retained.get("base_graph_digest") != expected_graph_digest:
            raise OrchestratorError("retained graph digest mismatch")
        if content_hash(exact) != plan_digest:
            raise OrchestratorError("retained exact plan bytes digest mismatch")
        try:
            plan = json.loads(exact)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OrchestratorError("retained canonical plan bytes are invalid JSON") from exc
        if canonical_bytes(plan) != exact:
            raise OrchestratorError("retained plan bytes are not canonical")
        return retained, plan, exact

    def _validate_base(
        self,
        run: dict[str, Any],
        graph: Any,
        retained: dict[str, Any],
        plan: dict[str, Any],
        exact_plan: bytes,
        expected_revision: int,
        expected_digest: str,
    ) -> None:
        from graph_v6 import GraphStatus, compute_graph_digest, validate_identity_format

        if run.get("status") != "active":
            raise OrchestratorError("expansion commit requires an active run")
        if graph.status != GraphStatus.OPEN:
            raise OrchestratorError(f"expansion commit requires open graph state, got {graph.status!r}")
        if retained.get("status") != "pending":
            raise OrchestratorError(f"retained expansion is not pending: {retained.get('status')!r}")
        if run.get("graph_revision") != graph.graph_revision or run.get("graph_digest") != graph.graph_digest:
            raise OrchestratorError("run and graph disagree before expansion commit")
        if compute_graph_digest(graph) != graph.graph_digest:
            raise OrchestratorError("persisted graph digest is invalid before expansion commit")
        if graph.graph_revision != expected_revision:
            raise OrchestratorError(
                f"stale graph compare-and-swap: expected revision {expected_revision}, got {graph.graph_revision}"
            )
        if graph.graph_digest != expected_digest:
            raise OrchestratorError(
                f"stale graph compare-and-swap: expected digest {expected_digest[:16]}..., got {graph.graph_digest[:16]}..."
            )
        if len(exact_plan) != retained.get("canonical_size"):
            raise OrchestratorError("retained canonical plan size mismatch")
        provenance = retained.get("provenance", {})
        authority_id = provenance.get("authority_id", "")
        authority = graph._authorities.get(authority_id)
        if authority is None or authority.get("status", "active") != "active":
            raise OrchestratorError("retained producer authority is missing or inactive")
        try:
            from orchestrator_core import parse_time

            if parse_time(authority.get("expires_at", "")) < parse_time(utc_now()):
                raise OrchestratorError("retained producer authority has expired")
        except OrchestratorError:
            raise
        if graph.active_planning_authority_id != authority_id:
            raise OrchestratorError("retained producer is no longer the active planning authority")
        producer_job = graph._jobs.get(provenance.get("producer_job_id", ""))
        if producer_job is None or producer_job.get("authority_id") != authority_id:
            raise OrchestratorError("retained producer job no longer owns the authority")
        if (
            authority.get("job_identity") != provenance.get("producer_job_id")
            or authority.get("role") != producer_job.get("role")
        ):
            raise OrchestratorError("retained producer authority identity or role is stale")
        if content_hash(authority.get("scope", {})) != provenance.get("authority_scope_digest"):
            raise OrchestratorError("retained authority scope digest is stale")
        response_path = (
            self.run_root
            / "receipts"
            / "response"
            / f"{provenance.get('response_id', '')}.json"
        )
        if not response_path.exists():
            raise OrchestratorError("authenticated source response evidence is missing")
        response_bytes = response_path.read_bytes()
        if content_hash(response_bytes) != provenance.get("response_receipt_digest"):
            raise OrchestratorError("authenticated source response evidence is contradictory")
        response = json.loads(response_bytes)
        if canonical_bytes(response.get("expansion_plan")) != exact_plan:
            raise OrchestratorError("retained plan differs from its authenticated source response")
        if provenance.get("source_artifact_digest") != retained.get("plan_digest"):
            raise OrchestratorError("retained source artifact digest is contradictory")
        expected = {
            "campaign_id": graph.envelope.get("campaign_id"),
            "source_job_id": provenance.get("producer_job_id"),
            "source_attempt_id": provenance.get("producer_attempt_id"),
            "source_response_id": provenance.get("response_id"),
            "authority_id": authority_id,
            "authority_scope_digest": provenance.get("authority_scope_digest"),
            "base_graph_revision": expected_revision,
            "base_graph_digest": expected_digest,
        }
        for name, value in expected.items():
            if plan.get(name) != value:
                raise OrchestratorError(f"retained plan {name} does not match accepted provenance")
        expected_id = stable_id(
            "EXP", run.get("run_id", ""), provenance.get("response_id", "")
        ).upper()
        retained_expansion_id = retained.get("expansion_id")
        if retained_expansion_id:
            if retained_expansion_id != expected_id:
                raise OrchestratorError("expansion identity does not match retained response identity")
        pending = []
        retained_dir = self.run_root / "transactions" / "retained"
        for path in retained_dir.glob("EXP-*.json"):
            if path.name.endswith(".plan.json"):
                continue
            record = load_json(path)
            if record.get("status") == "pending":
                pending.append(record.get("expansion_id"))
        if pending != [retained["expansion_id"]]:
            raise OrchestratorError(f"single pending expansion slot violated: {sorted(pending)}")

    def _stage(
        self,
        run: dict[str, Any],
        graph: Any,
        retained: dict[str, Any],
        plan: dict[str, Any],
        exact_plan: bytes,
        expansion_id: str,
        plan_digest: str,
    ) -> dict[str, Any]:
        from graph_v6 import (
            GraphState,
            add_batch,
            add_edge_to_graph,
            add_expansion,
            add_generation,
            add_job_to_graph,
            add_repair_gate,
            add_verifier_assignment,
            advance_graph_revision,
            compute_graph_digest,
            generate_batch_id,
            generate_global_job_id,
            validate_identity_format,
            validate_limits,
            validate_prospective_graph,
        )

        now = utc_now()
        run_id = run["run_id"]
        campaign_id = graph.envelope.get("campaign_id", "")
        cycle_id = str(plan.get("cycle_id") or run.get("current_cycle_id") or "")
        validate_identity_format(cycle_id)
        new_revision = graph.graph_revision + 1
        targets = plan.get("target_jobs")
        if not isinstance(targets, list) or not targets:
            raise OrchestratorError("expansion target_jobs must be a non-empty array")

        local_ids: list[str] = []
        job_mapping: list[dict[str, str]] = []
        mapped_jobs: dict[str, str] = {}
        for target in targets:
            if not isinstance(target, dict):
                raise OrchestratorError("each target job must be an object")
            local_id = target.get("local_job_id", "")
            validate_identity_format(local_id)
            if local_id in mapped_jobs:
                raise OrchestratorError(f"duplicate plan-local job identity {local_id!r}")
            global_id = generate_global_job_id(run_id, expansion_id, local_id)
            mapped_jobs[local_id] = global_id
            local_ids.append(local_id)
            job_mapping.append({"local_job_id": local_id, "global_job_id": global_id})

        def map_job(value: str, label: str) -> str:
            mapped = mapped_jobs.get(value, value)
            validate_identity_format(mapped)
            if mapped not in graph._jobs and mapped not in mapped_jobs.values():
                raise OrchestratorError(f"{label} references unknown job {value!r}")
            return mapped

        parent_authority = graph._authorities[retained["provenance"]["authority_id"]]
        scope = parent_authority.get("scope", {})
        allowed_roles = set(scope.get("allowed_child_roles", []))
        allowed_effects = set(scope.get("side_effects", []))
        if plan.get("expansion_kind") not in scope.get("allowed_expansion_kinds", []):
            raise OrchestratorError("expansion kind is outside current authority scope")

        prospective_jobs: list[dict[str, Any]] = []
        runtime_jobs: list[dict[str, Any]] = []
        authorities: list[dict[str, Any]] = []
        activations: list[dict[str, Any]] = []
        prompt_bytes: dict[str, bytes] = {}
        total_prompt_size = 0
        external_effects = 0
        hypothesis_count = 0
        max_depth = parent_authority.get("depth", 0)
        for target in targets:
            local_id = target["local_job_id"]
            global_id = mapped_jobs[local_id]
            role = target.get("role", "")
            purpose = target.get("purpose_key", "")
            if role not in allowed_roles:
                raise OrchestratorError(f"child role {role!r} is outside authority scope")
            if not purpose:
                raise OrchestratorError(f"job {local_id!r} has no purpose_key")
            effect = target.get("side_effect_class", "none")
            if effect not in allowed_effects:
                raise OrchestratorError(f"child side effect {effect!r} is outside authority scope")
            external_effects += effect.startswith("external")
            hypothesis_count += role == "hypothesis_investigator"
            authority_id = target.get("authority_id", "")
            context_id = target.get("context_snapshot_id", "")
            activation_id = target.get("activation_id", "")
            for identity in (authority_id, context_id, activation_id):
                validate_identity_format(identity)
            parent_job = target.get("parent_job_id", plan["source_job_id"])
            parent_job = map_job(parent_job, f"job {local_id} parent")
            repair = copy.deepcopy(target.get("repair_relationship"))
            if repair:
                repair["target_job_id"] = map_job(
                    repair.get("target_job_id", ""), f"job {local_id} repair relationship"
                )
            prompt_path = f"jobs/{global_id}/prompt.md"
            graph_job = {
                "schema_version": SCHEMA_VERSION,
                "job_id": global_id,
                "title": target.get("title") or f"{role}: {purpose}",
                "prompt_path": prompt_path,
                "role": role,
                "purpose_key": purpose,
                "graph_generation": new_revision,
                "expansion_origin": parent_job,
                "authority_id": authority_id,
                "context_snapshot_id": context_id,
                "activation_id": activation_id,
                "created_at": now,
            }
            if repair:
                graph_job["repair_relationship"] = repair
            validate_record("job-definition", graph_job)
            prospective_jobs.append(graph_job)
            runtime = {
                "schema_version": SCHEMA_VERSION,
                "job_id": global_id,
                "run_id": run_id,
                "title": graph_job["title"],
                "status": "pending",
                "activation_id": activation_id,
                "context_snapshot_id": context_id,
                "prompt_path": prompt_path,
                "created_at": now,
                "updated_at": now,
            }
            if repair:
                runtime["repair_relationship"] = repair
            validate_record("job", runtime)
            runtime_jobs.append(runtime)
            activation = {
                "schema_version": SCHEMA_VERSION,
                "activation_id": activation_id,
                "job_id": global_id,
                "run_id": run_id,
                "cycle_id": cycle_id,
                "graph_revision": new_revision,
                "context_snapshot_id": context_id,
                "status": "activated",
                "created_at": now,
            }
            validate_record("activation", activation)
            activations.append(activation)
            child_scope = copy.deepcopy(target.get("authority_scope")) or None
            if child_scope is None:
                from orchestrator_core import _authority_scope_for_role
                child_scope = _authority_scope_for_role(role, graph)
            if not child_scope:
                child_scope = {
                    "allowed_expansion_kinds": [],
                    "allowed_child_roles": [],
                    "owned_batch_ids": [],
                    "side_effects": [effect],
                    "max_child_jobs": 0,
                    "max_child_depth": 0,
                    "limits": {},
                }
            child_depth = target.get("authority_depth", parent_authority.get("depth", 0) + 1)
            max_depth = max(max_depth, child_depth)
            authority = {
                "schema_version": SCHEMA_VERSION,
                "authority_id": authority_id,
                "campaign_id": campaign_id,
                "job_identity": global_id,
                "role": role,
                "depth": child_depth,
                "parent_authority_id": parent_authority["authority_id"],
                "status": "active",
                "scope": child_scope,
                "granted_at": now,
                "expires_at": parent_authority["expires_at"],
            }
            validate_record("authority", authority)
            if authority_id in graph._authorities or any(a["authority_id"] == authority_id for a in authorities):
                raise OrchestratorError(f"authority identity collision: {authority_id!r}")
            authorities.append(authority)
            prompt = self._render_prompt(run, graph, plan, graph_job, target)
            prompt_bytes[prompt_path] = prompt
            total_prompt_size += len(prompt)

        prospective_edges: list[dict[str, Any]] = []
        edge_mapping: list[dict[str, str]] = []
        for index, edge in enumerate(plan.get("edges", [])):
            local_edge_id = edge.get("local_edge_id") or f"EDGE-{index + 1}"
            validate_identity_format(local_edge_id)
            edge_id = stable_id("EDGE", expansion_id, local_edge_id)
            edge_id = edge_id[:5] + edge_id[5:].upper()
            source = map_job(edge.get("source_job_id", ""), f"edge {local_edge_id} source")
            target = map_job(edge.get("target_job_id", ""), f"edge {local_edge_id} target")
            record = {
                "schema_version": SCHEMA_VERSION,
                "edge_id": edge_id,
                "source_job_id": source,
                "target_job_id": target,
                "edge_type": edge.get("edge_type", ""),
                "graph_revision": new_revision,
                "created_at": now,
            }
            if edge.get("metadata"):
                record["metadata"] = copy.deepcopy(edge["metadata"])
            validate_record("typed-dependency-edge", record)
            prospective_edges.append(record)
            edge_mapping.append({"local_edge_id": local_edge_id, "global_edge_id": edge_id})

        new_batches: list[dict[str, Any]] = []
        batch_additions: dict[str, list[str]] = {}
        for index, batch in enumerate(plan.get("batches", [])):
            local_batch_id = batch.get("batch_id") or f"BATCH-{index + 1}"
            validate_identity_format(local_batch_id)
            members = [map_job(job_id, f"batch {local_batch_id}") for job_id in batch.get("job_ids", [])]
            if local_batch_id in graph._batches:
                batch_additions[local_batch_id] = members
                owned = scope.get("owned_batch_ids", [])
                if owned and local_batch_id not in owned:
                    raise OrchestratorError(f"authority does not own batch {local_batch_id!r}")
                continue
            batch_id = generate_batch_id(expansion_id, index)
            batch_id = batch_id[:6] + batch_id[6:].upper()
            record = {
                "schema_version": SCHEMA_VERSION,
                "batch_id": batch_id,
                "campaign_id": campaign_id,
                "cycle_id": cycle_id,
                "status": batch.get("status", "open"),
                "job_ids": members,
                "created_at": now,
                "updated_at": now,
            }
            validate_record("dynamic-batch", record)
            new_batches.append(record)

        verifier_assignments = self._map_verifier_assignments(
            plan.get("verifier_assignments", []), map_job, run_id, cycle_id, new_revision, now
        )
        repair_gates = self._map_repair_gates(plan.get("repair_gates", []), map_job, now)
        graph_errors = validate_prospective_graph(
            graph,
            prospective_jobs,
            prospective_edges,
            new_batches,
            batch_additions,
            verifier_assignments,
            repair_gates,
        )
        graph_limits = {**graph.envelope.get("limits", {}), **graph.limits}
        max_expansions = graph_limits.get("max_expansions")
        if max_expansions is not None and len(graph.expansion_ledger) + 1 > max_expansions:
            graph_errors.append("expansion count limit exceeded")
        max_batches = graph_limits.get("max_batches_per_expansion")
        if max_batches is not None and len(plan.get("batches", [])) > max_batches:
            graph_errors.append("batches per expansion limit exceeded")
        max_jobs_per_expansion = graph_limits.get("max_jobs_per_expansion")
        if (
            max_jobs_per_expansion is not None
            and len(prospective_jobs) > max_jobs_per_expansion
        ):
            graph_errors.append("jobs per expansion limit exceeded")
        estimated_time = plan.get("estimated_time_seconds", 0)
        estimated_cost = plan.get("estimated_cost", 0)
        if not isinstance(estimated_time, (int, float)) or isinstance(estimated_time, bool):
            graph_errors.append("estimated_time_seconds must be numeric")
            estimated_time = 0
        if not isinstance(estimated_cost, (int, float)) or isinstance(estimated_cost, bool):
            graph_errors.append("estimated_cost must be numeric")
            estimated_cost = 0
        limit_errors = validate_limits(
            graph,
            proposed_expansion_depth=max_depth,
            proposed_hypothesis_count=hypothesis_count,
            proposed_concurrency=len(prospective_jobs),
            proposed_external_effects=external_effects,
            proposed_prompt_size=total_prompt_size,
            proposed_plan_size=len(exact_plan),
            estimated_time_seconds=estimated_time,
            estimated_cost=estimated_cost,
            proposed_jobs=prospective_jobs,
            proposed_edges=prospective_edges,
            proposed_batches=new_batches,
        )
        if graph_errors or limit_errors:
            raise OrchestratorError(
                "prospective graph validation failed: " + "; ".join(graph_errors + limit_errors)
            )

        prospective = GraphState.from_dict(graph.to_dict())
        for job in prospective_jobs:
            add_job_to_graph(prospective, job)
        for edge in prospective_edges:
            add_edge_to_graph(prospective, edge)
        for authority in authorities:
            prospective._authorities[authority["authority_id"]] = authority
        for batch in new_batches:
            add_batch(prospective, batch)
        for batch_id, members in batch_additions.items():
            prospective._batches[batch_id]["job_ids"].extend(members)
            prospective._batches[batch_id]["updated_at"] = now
        for assignment in verifier_assignments:
            add_verifier_assignment(prospective, assignment)
        for gate in repair_gates:
            add_repair_gate(prospective, gate)
        prospective.active_planning_authority_id = None
        prospective.status = "open"
        expansion_record = {
            "expansion_id": expansion_id,
            "status": "committed",
            "plan_digest": plan_digest,
            "job_mapping": job_mapping,
            "edge_mapping": edge_mapping,
            "base_graph_revision": graph.graph_revision,
            "committed_at": now,
        }
        add_expansion(prospective, expansion_record)
        advance_graph_revision(prospective)
        generation = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": stable_id("GEN", expansion_id, str(prospective.graph_revision)).upper(),
            "campaign_id": campaign_id,
            "graph_revision": prospective.graph_revision,
            "parent_revision": graph.graph_revision,
            "vertex_count": len(prospective._jobs),
            "edge_count": len(prospective._edges),
            "graph_digest": prospective.graph_digest,
            "created_at": now,
        }
        validate_record("graph-generation", generation)
        add_generation(prospective, generation)
        if compute_graph_digest(prospective) != prospective.graph_digest:
            raise OrchestratorError("prospective graph digest is inconsistent")

        visible_run = copy.deepcopy(run)
        visible_run["job_ids"] = [*visible_run.get("job_ids", []), *[j["job_id"] for j in prospective_jobs]]
        visible_run["graph_revision"] = prospective.graph_revision
        visible_run["graph_digest"] = prospective.graph_digest
        visible_run["updated_at"] = now

        files: dict[str, tuple[bytes, bool]] = {
            "graph/graph.json": (_json_file_bytes(prospective.to_dict()), False),
            f"graph/generations/{generation['generation_id']}.json": (_json_file_bytes(generation), False),
            f"graph/expansions/{expansion_id}.json": (_json_file_bytes(expansion_record), False),
            "run.json": (_json_file_bytes(visible_run), True),
        }
        for graph_job, runtime, activation in zip(prospective_jobs, runtime_jobs, activations):
            job_id = graph_job["job_id"]
            files[f"jobs/{job_id}/definition.json"] = (_json_file_bytes(graph_job), False)
            files[f"jobs/{job_id}/job.json"] = (_json_file_bytes(runtime), False)
            files[f"jobs/{job_id}/activation.json"] = (_json_file_bytes(activation), False)
            files[graph_job["prompt_path"]] = (prompt_bytes[graph_job["prompt_path"]], False)

        stage_root = self._stage_root(expansion_id)
        descriptors = []
        for relative, (data, visibility) in sorted(files.items(), key=lambda item: (item[1][1], item[0])):
            self._safe_relative(relative)
            staged_relative = f"files/{relative}"
            atomic_write(stage_root / staged_relative, data)
            descriptors.append({
                "path": relative,
                "staged_path": staged_relative,
                "sha256": content_hash(data),
                "size": len(data),
                "visibility": visibility,
            })
        transaction_digest = content_hash(descriptors)
        return {
            "schema_version": SCHEMA_VERSION,
            "transaction_id": stable_id("TX", expansion_id, plan_digest).upper(),
            "expansion_id": expansion_id,
            "campaign_id": campaign_id,
            "plan_digest": plan_digest,
            "expected_graph_revision": graph.graph_revision,
            "expected_graph_digest": graph.graph_digest,
            "graph_revision_after": prospective.graph_revision,
            "graph_digest_after": prospective.graph_digest,
            "transaction_digest": transaction_digest,
            "status": "prepared",
            "files": descriptors,
            "job_mapping": job_mapping,
            "edge_mapping": edge_mapping,
            "created_at": now,
        }

    def _render_prompt(
        self,
        run: dict[str, Any],
        graph: Any,
        plan: dict[str, Any],
        job: dict[str, Any],
        target: dict[str, Any],
    ) -> bytes:
        lines = [
            f"# {job['title']}",
            "",
            f"Run: {run['run_id']}",
            f"Campaign: {graph.envelope.get('campaign_id', '')}",
            f"Cycle: {plan.get('cycle_id', '')}",
            f"Graph generation: {job['graph_generation']}",
            f"Role: {job['role']}",
            f"Purpose: {job['purpose_key']}",
            f"Context snapshot: {job['context_snapshot_id']}",
            f"Authority: {job['authority_id']}",
            f"Expansion origin: {job['expansion_origin']}",
            f"Side effect class: {target.get('side_effect_class', 'none')}",
            f"Prompt input digest: {target.get('prompt_input_digest', '')}",
            "",
            "Perform only this persisted job contract. Do not mutate orchestrator state.",
        ]
        return ("\n".join(lines) + "\n").encode("utf-8")

    def _map_verifier_assignments(
        self,
        values: Any,
        map_job: Any,
        run_id: str,
        cycle_id: str,
        generation: int,
        now: str,
    ) -> list[dict[str, Any]]:
        records = []
        for index, value in enumerate(values or []):
            record = copy.deepcopy(value)
            record.setdefault("schema_version", SCHEMA_VERSION)
            record.setdefault("assignment_id", stable_id("VASS", run_id, cycle_id, str(index)))
            record["target_job_id"] = map_job(record.get("target_job_id", ""), "verifier target")
            record["verifier_job_id"] = map_job(record.get("verifier_job_id", ""), "verifier job")
            record.setdefault("run_id", run_id)
            record.setdefault("cycle_id", cycle_id)
            record.setdefault("graph_generation", generation)
            record.setdefault("status", "assigned")
            record.setdefault("assigned_at", now)
            validate_record("verifier-assignment", record)
            records.append(record)
        return records

    def _map_repair_gates(self, values: Any, map_job: Any, now: str) -> list[dict[str, Any]]:
        records = []
        for value in values or []:
            record = copy.deepcopy(value)
            record.setdefault("schema_version", SCHEMA_VERSION)
            record["target_job_id"] = map_job(record.get("target_job_id", ""), "repair target")
            record["repair_job_id"] = map_job(record.get("repair_job_id", ""), "repair job")
            record.setdefault("recorded_at", now)
            validate_record("repair-gate-history", record)
            records.append(record)
        return records

    def _verify_staged_files(self, manifest: dict[str, Any]) -> None:
        if content_hash(manifest.get("files", [])) != manifest.get("transaction_digest"):
            raise OrchestratorError("transaction manifest digest is contradictory")
        stage_root = self._stage_root(manifest["expansion_id"])
        for descriptor in manifest.get("files", []):
            self._safe_relative(descriptor["path"])
            staged = stage_root / descriptor["staged_path"]
            if not staged.exists():
                raise OrchestratorError(f"staged transaction file is missing: {descriptor['path']}")
            data = staged.read_bytes()
            if len(data) != descriptor["size"] or content_hash(data) != descriptor["sha256"]:
                raise OrchestratorError(f"staged transaction file is contradictory: {descriptor['path']}")

    def _apply_files(self, manifest: dict[str, Any], visibility: bool) -> None:
        stage_root = self._stage_root(manifest["expansion_id"])
        written = 0
        for descriptor in manifest["files"]:
            if descriptor["visibility"] is not visibility:
                continue
            destination = self.run_root / descriptor["path"]
            data = (stage_root / descriptor["staged_path"]).read_bytes()
            if destination.exists():
                existing = destination.read_bytes()
                if existing == data:
                    continue
                if descriptor["path"] not in {"graph/graph.json", "run.json"}:
                    raise OrchestratorError(
                        f"authoritative destination contradicts transaction: {descriptor['path']}"
                    )
                if descriptor["path"] == "run.json":
                    current = load_json(destination)
                    if current.get("graph_revision") != manifest["expected_graph_revision"]:
                        raise OrchestratorError("run visibility state contradicts transaction base")
                elif descriptor["path"] == "graph/graph.json":
                    from graph_v6 import GraphState, compute_graph_digest

                    current = load_json(destination)
                    revision = current.get("graph_revision")
                    if revision != manifest["expected_graph_revision"]:
                        raise OrchestratorError("graph destination contradicts transaction base")
                    current_graph = GraphState.from_dict(current)
                    if (
                        current_graph.graph_digest != manifest["expected_graph_digest"]
                        or compute_graph_digest(current_graph) != manifest["expected_graph_digest"]
                    ):
                        raise OrchestratorError("graph destination bytes contradict transaction base")
            atomic_write(destination, data)
            written += 1
            if not visibility and written == 1:
                self._fault("after_file_write")

    def _finalize_metadata(self, expansion_id: str, retained: dict[str, Any], graph: Any) -> None:
        retained_path = self.run_root / "transactions" / "retained" / f"{expansion_id}.json"
        if retained.get("status") != "committed":
            retained = copy.deepcopy(retained)
            retained["status"] = "committed"
            retained["committed_at"] = graph._expansions[expansion_id]["committed_at"]
            atomic_write(retained_path, _json_file_bytes(retained))
        manifest_path = self._manifest_path(expansion_id)
        if manifest_path.exists():
            manifest = load_json(manifest_path)
            if manifest.get("status") != "committed":
                manifest["status"] = "committed"
                manifest["committed_at"] = graph._expansions[expansion_id]["committed_at"]
                atomic_write(manifest_path, _json_file_bytes(manifest))

    def _validate_manifest_binding(
        self,
        manifest: dict[str, Any],
        expansion_id: str,
        plan_digest: str,
        expected_revision: int,
        expected_digest: str,
    ) -> None:
        expected = {
            "expansion_id": expansion_id,
            "plan_digest": plan_digest,
            "expected_graph_revision": expected_revision,
            "expected_graph_digest": expected_digest,
        }
        for name, value in expected.items():
            if manifest.get(name) != value:
                raise OrchestratorError(f"transaction manifest {name} conflicts with commit request")

    def _result(
        self,
        graph: Any,
        job_mapping: list[dict[str, str]],
        edge_mapping: list[dict[str, str]],
        replay: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "idempotent_replay" if replay else "committed",
            "expansion_id": next(
                expansion_id
                for expansion_id, record in graph._expansions.items()
                if record.get("job_mapping") == job_mapping and record.get("edge_mapping", []) == edge_mapping
            ),
            "canonical_job_mapping": job_mapping,
            "canonical_edge_mapping": edge_mapping,
            "recorded": True,
            "graph_revision": graph.graph_revision,
            "graph_digest": graph.graph_digest,
            "committed_at": next(
                record["committed_at"]
                for record in graph._expansions.values()
                if record.get("job_mapping") == job_mapping and record.get("edge_mapping", []) == edge_mapping
            ),
        }

    def _manifest_path(self, expansion_id: str) -> Path:
        return self.run_root / "transactions" / "manifests" / f"{expansion_id}.manifest.json"

    def _stage_root(self, expansion_id: str) -> Path:
        return self.run_root / "transactions" / "staging" / expansion_id

    @staticmethod
    def _safe_relative(value: str) -> None:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise OrchestratorError(f"unsafe transaction path {value!r}")

    def _fault(self, boundary: str) -> None:
        if self.fault_at == boundary:
            raise OrchestratorError(f"fault injection at expansion transaction boundary {boundary}")
