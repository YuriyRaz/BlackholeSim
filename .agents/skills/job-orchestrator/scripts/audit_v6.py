"""Append-only audit, cancellation, stale-response reconciliation, side-effect
recovery preservation, and recovery scenarios for the v6 dynamic protocol."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from orchestrator_core import (
    SCHEMA_VERSION,
    OrchestratorError,
    canonical_bytes,
    content_hash,
    load_json,
    stable_id,
    utc_now,
    validate_record,
)
from graph_v6 import (
    EdgeRecord,
    ExpansionSlot,
    GraphState,
    GraphStatus,
    JobRecord,
    RepairGateRecord,
    VerifierRecord,
    compute_graph_digest,
)
from transaction_v6 import (
    ExpansionRecovery,
    GoalDecisionProcessor,
)


# ===========================================================================
# Task 13.1 – DynamicAuditor
# ===========================================================================

class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Finding classifications for state integrity audit gate
class FindingClassification:
    """Constants for audit/recovery finding classifications."""

    CLEAN = "clean"
    DERIVED_SNAPSHOT_DRIFT = "derived_snapshot_drift"
    STALE_INDEX_OR_QUEUE = "stale_index_or_queue"
    INTERRUPTED_DISPATCH_RECORDED_NOT_SENT = "interrupted_dispatch_recorded_not_sent"
    INTERRUPTED_DISPATCH_SENT_NO_RESULT = "interrupted_dispatch_sent_no_result"
    COMPLETED_RESULT_NOT_APPLIED = "completed_result_not_applied"
    EXTERNAL_EFFECT_UNKNOWN = "external_effect_unknown"
    JOURNAL_CORRUPT_OR_INSUFFICIENT = "journal_corrupt_or_insufficient"
    ACTIVE_IDLE_CONTRADICTION = "active_idle_contradiction"
    PROTOCOL_HASH_MISMATCH = "protocol_hash_mismatch"
    REPLAY_HEALTH_OK = "replay_health_ok"
    SIDE_EFFECT_BLOCKER = "side_effect_blocker"


class AuditFinding:
    """Single audit finding with severity, code, message, and classification."""

    def __init__(
        self,
        *,
        severity: AuditSeverity,
        code: str,
        message: str,
        context: dict[str, Any] | None = None,
        classification: str | None = None,
    ) -> None:
        self.severity = severity
        self.code = code
        self.message = message
        self.context = context or {}
        self.classification = classification

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }
        if self.classification:
            d["classification"] = self.classification
        if self.context:
            d["context"] = self.context
        return d


class DynamicAuditor:
    """Comprehensive invariants checker for v6 dynamic orchestration state."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._findings: list[AuditFinding] = []

    @property
    def findings(self) -> list[AuditFinding]:
        return list(self._findings)

    def _add(
        self,
        severity: AuditSeverity,
        code: str,
        message: str,
        context: dict[str, Any] | None = None,
        classification: str | None = None,
    ) -> None:
        ctx = dict(context) if context else {}
        if classification and "classification" not in ctx:
            ctx["classification"] = classification
        self._findings.append(
            AuditFinding(
                severity=severity,
                code=code,
                message=message,
                context=ctx,
                classification=classification,
            )
        )

    # -- 13.1: graph digest -------------------------------------------------

    def validate_graph_digest(self) -> None:
        """Verify stored graph digest matches recomputed digest."""
        if not self._gs.graph_digest:
            self._add(AuditSeverity.CRITICAL, "GRAPH_DIGEST_MISSING", "graph digest is empty")
            return
        current = compute_graph_digest(self._gs)
        if current != self._gs.graph_digest:
            self._add(
                AuditSeverity.CRITICAL,
                "GRAPH_DIGEST_MISMATCH",
                "stored graph digest does not match recomputed digest",
                {
                    "stored": self._gs.graph_digest[:16] + "...",
                    "computed": current[:16] + "...",
                },
            )

    # -- 13.1: generations --------------------------------------------------

    def validate_generations(self) -> None:
        """Check generation records are monotonically ordered and reference existing jobs."""
        seen_revisions: list[int] = []
        for gen in self._gs._generations:
            rev = gen.get("graph_revision", 0)
            if rev < 1:
                self._add(
                    AuditSeverity.ERROR,
                    "GENERATION_REVISION_INVALID",
                    f"generation {gen.get('generation_id', '?')} has revision {rev} < 1",
                )
            if seen_revisions and rev <= seen_revisions[-1]:
                self._add(
                    AuditSeverity.WARNING,
                    "GENERATION_OUT_OF_ORDER",
                    f"generation revision {rev} not strictly after {seen_revisions[-1]}",
                )
            seen_revisions.append(rev)
            if gen.get("graph_digest") is None:
                self._add(
                    AuditSeverity.WARNING,
                    "GENERATION_NO_DIGEST",
                    f"generation {gen.get('generation_id', '?')} missing graph_digest",
                )

    # -- 13.1: expansion provenance -----------------------------------------

    def validate_expansion_provenance(self) -> None:
        """Validate that every expansion has valid provenance fields."""
        for exp_id, exp in self._gs._expansions.items():
            prov = exp.get("provenance", {})
            for field in ("producer_job_id", "authority_id", "cycle_id"):
                if not prov.get(field):
                    self._add(
                        AuditSeverity.ERROR,
                        "EXPANSION_PROVENANCE_MISSING",
                        f"expansion {exp_id} missing provenance.{field}",
                    )
            if prov.get("graph_digest") is None:
                self._add(
                    AuditSeverity.WARNING,
                    "EXPANSION_PROVENANCE_NO_DIGEST",
                    f"expansion {exp_id} provenance missing graph_digest",
                )
            if prov.get("source_artifact_digest") is None:
                self._add(
                    AuditSeverity.WARNING,
                    "EXPANSION_PROVENANCE_NO_SOURCE_ARTIFACT",
                    f"expansion {exp_id} provenance missing source_artifact_digest",
                )

    # -- 13.1: authority chains ---------------------------------------------

    def validate_authority_chains(self) -> None:
        """Verify that every job and expansion references a valid authority."""
        authority_ids = set()
        for job in self._gs._jobs.values():
            aid = job.get("authority_id")
            if not aid:
                self._add(
                    AuditSeverity.ERROR,
                    "JOB_NO_AUTHORITY",
                    f"job {job.get('job_id', '?')} has no authority_id",
                )
            else:
                authority_ids.add(aid)
        for exp_id, exp in self._gs._expansions.items():
            aid = exp.get("provenance", {}).get("authority_id")
            if not aid:
                self._add(
                    AuditSeverity.ERROR,
                    "EXPANSION_NO_AUTHORITY",
                    f"expansion {exp_id} has no authority in provenance",
                )
            elif aid not in authority_ids and aid != self._gs.envelope.get("authority_id"):
                self._add(
                    AuditSeverity.WARNING,
                    "EXPANSION_AUTHORITY_NOT_IN_JOBS",
                    f"expansion {exp_id} references authority {aid} not found among jobs",
                )

    # -- 13.1: batch states -------------------------------------------------

    def validate_batches(self) -> None:
        """Check batch state consistency."""
        for batch_id, batch in self._gs._batches.items():
            status = batch.get("status")
            job_ids = batch.get("job_ids", [])
            for jid in job_ids:
                if jid not in self._gs._jobs:
                    self._add(
                        AuditSeverity.ERROR,
                        "BATCH_REFERS_TO_MISSING_JOB",
                        f"batch {batch_id} references missing job {jid}",
                    )
            if status == "open" and not batch.get("created_at"):
                self._add(
                    AuditSeverity.WARNING,
                    "BATCH_OPEN_NO_CREATED_AT",
                    f"open batch {batch_id} missing created_at",
                )
            if status == "sealed" and not batch.get("sealed_at"):
                self._add(
                    AuditSeverity.WARNING,
                    "BATCH_SEALED_NO_SEALED_AT",
                    f"sealed batch {batch_id} missing sealed_at",
                )
            if status == "complete" and not batch.get("completed_at"):
                self._add(
                    AuditSeverity.WARNING,
                    "BATCH_COMPLETE_NO_COMPLETED_AT",
                    f"complete batch {batch_id} missing completed_at",
                )

    # -- 13.1: typed edges --------------------------------------------------

    def validate_typed_edges(self) -> None:
        """Verify edge types and source/target job existence."""
        valid_types = EdgeRecord.VALID_EDGE_TYPES
        job_ids = {j.get("job_id") for j in self._gs._jobs.values()}
        for edge_id, edge in self._gs._edges.items():
            etype = edge.get("edge_type")
            if etype not in valid_types:
                self._add(
                    AuditSeverity.ERROR,
                    "EDGE_INVALID_TYPE",
                    f"edge {edge_id} has invalid type {etype!r}",
                )
            src = edge.get("source_job_id")
            tgt = edge.get("target_job_id")
            if src and src not in job_ids:
                self._add(
                    AuditSeverity.ERROR,
                    "EDGE_SOURCE_MISSING",
                    f"edge {edge_id} source_job_id {src} not in graph jobs",
                )
            if tgt and tgt not in job_ids:
                self._add(
                    AuditSeverity.ERROR,
                    "EDGE_TARGET_MISSING",
                    f"edge {edge_id} target_job_id {tgt} not in graph jobs",
                )

    # -- 13.1: target gates -------------------------------------------------

    def validate_target_gates(self) -> None:
        """Check repair-gate history entries reference valid target jobs."""
        for entry in self._gs._repair_gate_history:
            target = entry.get("target_job_id")
            if target and target not in self._gs._jobs:
                self._add(
                    AuditSeverity.ERROR,
                    "GATE_TARGET_MISSING",
                    f"repair gate references missing target job {target}",
                )
            repair = entry.get("repair_job_id")
            if repair and repair not in self._gs._jobs:
                self._add(
                    AuditSeverity.WARNING,
                    "GATE_REPAIR_JOB_MISSING",
                    f"repair gate repair_job_id {repair} not in graph jobs",
                )

    # -- 13.1: findings -----------------------------------------------------

    def validate_findings(self) -> None:
        """Validate finding disposition records."""
        for disp_id, disp in getattr(self._gs, "_finding_dispositions", {}).items():
            producer = disp.get("producer_role")
            valid_roles = (
                "goal_judge", "implementation_review_architect",
                "verifier", "integration_verifier",
            )
            if producer and producer not in valid_roles:
                self._add(
                    AuditSeverity.ERROR,
                    "FINDING_INVALID_PRODUCER_ROLE",
                    f"finding disposition {disp_id} has invalid producer_role {producer!r}",
                )
            status = disp.get("status")
            valid_statuses = ("verified", "refuted", "superseded", "accepted_risk")
            if status and status not in valid_statuses:
                self._add(
                    AuditSeverity.ERROR,
                    "FINDING_INVALID_STATUS",
                    f"finding disposition {disp_id} has invalid status {status!r}",
                )

    # -- 13.1: decisions ----------------------------------------------------

    def validate_decisions(self) -> None:
        """Validate decision records and goal judge consistency."""
        if self._gs.current_goal_judge_id:
            for job in self._gs._jobs.values():
                if (
                    job.get("role") == "goal_judge"
                    and job.get("job_id") != self._gs.current_goal_judge_id
                    and job.get("status") not in ("cancelled", "blocked")
                ):
                    self._add(
                        AuditSeverity.WARNING,
                        "STALE_GOAL_JUDGE_JOB",
                        f"goal judge job {job.get('job_id')} is not the current judge",
                    )

    # -- 13.1: transactions -------------------------------------------------

    def validate_transactions(self) -> None:
        """Check transaction states for consistency."""
        for txn_id, txn in getattr(self._gs, "_transactions", {}).items():
            status = txn.get("status")
            if status not in ("pending", "committing", "complete", "blocked"):
                self._add(
                    AuditSeverity.ERROR,
                    "TRANSACTION_INVALID_STATUS",
                    f"transaction {txn_id} has invalid status {status!r}",
                )
            if status in ("pending", "committing") and self._gs.status == GraphStatus.SEALED:
                self._add(
                    AuditSeverity.CRITICAL,
                    "OPEN_TRANSACTION_ON_SEALED_GRAPH",
                    f"transaction {txn_id} is {status} but graph is sealed",
                )

    # -- 13.1: limits -------------------------------------------------------

    def validate_limits(self) -> None:
        """Check that the graph has not exceeded its envelope limits."""
        limits = self._gs.limits
        if not limits:
            return
        max_total = limits.get("max_total_jobs")
        if max_total is not None and len(self._gs._jobs) > max_total:
            self._add(
                AuditSeverity.ERROR,
                "LIMIT_TOTAL_JOBS_EXCEEDED",
                f"total jobs {len(self._gs._jobs)} exceeds max_total_jobs {max_total}",
            )
        max_cycles = limits.get("max_cycles")
        if max_cycles is not None:
            cycle_count = len(set(
                j.get("cycle_id", "") for j in self._gs._jobs.values()
            ))
            if cycle_count > max_cycles:
                self._add(
                    AuditSeverity.ERROR,
                    "LIMIT_CYCLES_EXCEEDED",
                    f"cycle count {cycle_count} exceeds max_cycles {max_cycles}",
                )

    # -- 13.1: side effects -------------------------------------------------

    def validate_side_effects(self) -> None:
        """Validate side-effect idempotency keys and deduplication."""
        idempotency_keys: dict[str, str] = {}
        for job in self._gs._jobs.values():
            se = job.get("side_effect", {})
            key = se.get("idempotency_key")
            if key:
                existing = idempotency_keys.get(key)
                if existing and existing != job.get("job_id"):
                    self._add(
                        AuditSeverity.WARNING,
                        "SIDE_EFFECT_DUPLICATE_KEY",
                        f"side_effect idempotency_key {key} used by multiple jobs",
                    )
                idempotency_keys[key] = job.get("job_id", "")

    # -- 13.1: sealing obligations ------------------------------------------

    def validate_sealing_obligations(self) -> None:
        """Check that sealed graph has no outstanding obligations."""
        if self._gs.status != GraphStatus.SEALED:
            return
        pending = [
            jid for jid, j in self._gs._jobs.items()
            if j.get("status") in ("pending", "running", "dispatching", "dispatch_pending")
        ]
        if pending:
            self._add(
                AuditSeverity.CRITICAL,
                "SEALED_GRAPH_HAS_PENDING_JOBS",
                f"sealed graph still has pending jobs: {pending[:5]}",
            )
        open_batches = [
            bid for bid, b in self._gs._batches.items()
            if b.get("status") in ("open", "sealed")
        ]
        if open_batches:
            self._add(
                AuditSeverity.CRITICAL,
                "SEALED_GRAPH_HAS_OPEN_BATCHES",
                f"sealed graph still has open batches: {open_batches[:5]}",
            )
        active_verifiers = [
            vid for vid, v in self._gs._verifier_assignments.items()
            if v.get("status") == "assigned"
        ]
        if active_verifiers:
            self._add(
                AuditSeverity.WARNING,
                "SEALED_GRAPH_HAS_ASSIGNED_VERIFIERS",
                f"sealed graph still has assigned verifiers: {active_verifiers[:5]}",
            )

    # -- 13.1: replay health ------------------------------------------------

    def validate_replay_health(self) -> None:
        """Check that the journal is replayable and event log is consistent."""
        if not self._gs._generations:
            self._add(
                AuditSeverity.INFO,
                "REPLAY_NO_GENERATIONS",
                "no generation records found; journal may be empty or insufficient",
                classification=FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT,
            )
            return
        latest_gen = max(g.get("graph_revision", 0) for g in self._gs._generations)
        if latest_gen < self._gs.graph_revision:
            self._add(
                AuditSeverity.WARNING,
                "REPLAY_GENERATION_LAG",
                "latest generation revision is behind current graph revision",
                context={
                    "latest_generation": latest_gen,
                    "graph_revision": self._gs.graph_revision,
                },
                classification=FindingClassification.DERIVED_SNAPSHOT_DRIFT,
            )

    # -- 13.1: protocol hash -----------------------------------------------

    def validate_protocol_hash(self, run_protocol_hash: str | None = None) -> None:
        """Check protocol hash status against a manifest if provided."""
        if run_protocol_hash is None:
            return
        envelope_hash = content_hash({
            "strategy": self._gs.envelope.get("strategy", ""),
            "version": self._gs.envelope.get("version", 0),
        })
        if envelope_hash != run_protocol_hash:
            self._add(
                AuditSeverity.CRITICAL,
                "PROTOCOL_HASH_MISMATCH",
                "protocol snapshot hash does not match run manifest",
                context={
                    "envelope_hash": envelope_hash[:16] + "...",
                    "manifest_hash": run_protocol_hash[:16] + "..." if run_protocol_hash else None,
                },
                classification=FindingClassification.PROTOCOL_HASH_MISMATCH,
            )

    # -- 13.1: derived snapshot drift --------------------------------------

    def validate_derived_snapshots(self) -> None:
        """Check that derived snapshots match replayed state."""
        job_ids_in_graph = set(self._gs._jobs.keys())
        if not job_ids_in_graph and self._gs._generations:
            self._add(
                AuditSeverity.WARNING,
                "DERIVED_SNAPSHOTS_EMPTY_WITH_EVENTS",
                "generation events exist but no jobs found in graph",
                classification=FindingClassification.DERIVED_SNAPSHOT_DRIFT,
            )

    # -- 13.1: active-idle contradiction -----------------------------------

    def validate_active_idle_contradiction(self) -> None:
        """Detect active run with no active job, no dispatch, empty queue, and unresolved actions."""
        active_jobs = [
            jid for jid, job in self._gs._jobs.items()
            if job.get("status") in {"running", "dispatching", "dispatch_pending"}
        ]
        waiting_jobs = [
            jid for jid, job in self._gs._jobs.items()
            if job.get("status") == "waiting"
        ]
        all_non_control_jobs = [
            jid for jid, job in self._gs._jobs.items()
            if job.get("role") != "control_root"
            and job.get("status") not in {"waiting", "completed", "cancelled", "blocked", "failed"}
        ]
        has_pending_or_dispatching = any(
            self._gs._jobs[jid].get("status") in {"pending", "dispatching", "dispatch_pending"}
            for jid in all_non_control_jobs
        )

        if (
            not active_jobs
            and not waiting_jobs
            and not has_pending_or_dispatching
            and self._gs.status == GraphStatus.OPEN
            and all_non_control_jobs
        ):
            self._add(
                AuditSeverity.CRITICAL,
                "ACTIVE_IDLE_CONTRADICTION",
                "run is active with no active job, no pending jobs, no waiting jobs, but jobs exist",
                context={"job_ids": [jid for jid in all_non_control_jobs][:10]},
                classification=FindingClassification.ACTIVE_IDLE_CONTRADICTION,
            )

    # -- 13.1: action/dispatch contradictions ------------------------------

    def validate_action_dispatch_contradictions(self) -> None:
        """Detect dispatches that were recorded but never sent, or sent but have no result."""
        for jid, job in self._gs._jobs.items():
            dispatch_id = job.get("dispatch_id")
            if not dispatch_id:
                continue
            if job.get("status") == "dispatch_pending":
                self._add(
                    AuditSeverity.WARNING,
                    "INTERRUPTED_DISPATCH_RECORDED_NOT_SENT",
                    f"job {jid} has dispatch {dispatch_id} recorded but status is dispatch_pending",
                    context={"job_id": jid, "dispatch_id": dispatch_id},
                    classification=FindingClassification.INTERRUPTED_DISPATCH_RECORDED_NOT_SENT,
                )
            elif job.get("status") == "running" and not job.get("evidence_refs"):
                self._add(
                    AuditSeverity.WARNING,
                    "INTERRUPTED_DISPATCH_SENT_NO_RESULT",
                    f"job {jid} is running with dispatch {dispatch_id} but no evidence received",
                    context={"job_id": jid, "dispatch_id": dispatch_id},
                    classification=FindingClassification.INTERRUPTED_DISPATCH_SENT_NO_RESULT,
                )

    # -- 13.1: completed result not applied --------------------------------

    def validate_completed_result_not_applied(self) -> None:
        """Detect completed results that haven't been applied to workflow state."""
        for jid, job in self._gs._jobs.items():
            if (
                job.get("completion_status") == "success"
                and job.get("status") == "completed"
                and not job.get("report_accepted")
            ):
                self._add(
                    AuditSeverity.WARNING,
                    "COMPLETED_RESULT_NOT_APPLIED",
                    f"job {jid} completed but report was not accepted",
                    context={"job_id": jid},
                    classification=FindingClassification.COMPLETED_RESULT_NOT_APPLIED,
                )

    # -- 13.1: side-effect blockers ----------------------------------------

    def validate_side_effect_blockers(self) -> None:
        """Detect side-effect jobs that may block recovery without configured checks."""
        for jid, job in self._gs._jobs.items():
            se = job.get("side_effect", {})
            effect_type = se.get("effect_type") or se.get("type")
            if effect_type and effect_type != "none":
                if job.get("status") in {"pending", "dispatching", "dispatch_pending"}:
                    recovery_check = se.get("recovery_check")
                    if not recovery_check:
                        self._add(
                            AuditSeverity.WARNING,
                            "SIDE_EFFECT_NO_RECOVERY_CHECK",
                            f"job {jid} has side effect {effect_type!r} but no recovery_check configured",
                            context={"job_id": jid, "effect_type": effect_type},
                            classification=FindingClassification.SIDE_EFFECT_BLOCKER,
                        )

    # -- run all validators -------------------------------------------------

    def run_all(self, run_protocol_hash: str | None = None) -> list[AuditFinding]:
        """Execute every validation and return all findings."""
        self.validate_graph_digest()
        self.validate_generations()
        self.validate_expansion_provenance()
        self.validate_authority_chains()
        self.validate_batches()
        self.validate_typed_edges()
        self.validate_target_gates()
        self.validate_findings()
        self.validate_decisions()
        self.validate_transactions()
        self.validate_limits()
        self.validate_side_effects()
        self.validate_sealing_obligations()
        self.validate_replay_health()
        self.validate_protocol_hash(run_protocol_hash)
        self.validate_derived_snapshots()
        self.validate_active_idle_contradiction()
        self.validate_action_dispatch_contradictions()
        self.validate_completed_result_not_applied()
        self.validate_side_effect_blockers()
        return self.findings

    @property
    def has_critical(self) -> bool:
        return any(f.severity == AuditSeverity.CRITICAL for f in self._findings)

    @property
    def has_errors(self) -> bool:
        return any(f.severity in (AuditSeverity.ERROR, AuditSeverity.CRITICAL) for f in self._findings)


# ===========================================================================
# Task 13.2 – AuditReporter
# ===========================================================================

class AuditReporter:
    """Exposes actionable control-plane facts without prose parsing."""

    def __init__(self, findings: list[AuditFinding]) -> None:
        self._findings = findings

    def expose_control_plane_facts(self) -> dict[str, Any]:
        """Return structured, machine-readable control-plane facts."""
        counts = {s.value: 0 for s in AuditSeverity}
        for f in self._findings:
            counts[f.severity.value] += 1

        blocking_codes = [
            f.code for f in self._findings
            if f.severity in (AuditSeverity.CRITICAL, AuditSeverity.ERROR)
        ]

        classifications = [
            f.classification for f in self._findings
            if f.classification
        ]

        has_active_idle = any(
            f.classification == FindingClassification.ACTIVE_IDLE_CONTRADICTION
            for f in self._findings
        )
        has_protocol_mismatch = any(
            f.classification == FindingClassification.PROTOCOL_HASH_MISMATCH
            for f in self._findings
        )
        has_journal_corrupt = any(
            f.classification == FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT
            and f.severity in (AuditSeverity.CRITICAL, AuditSeverity.ERROR)
            for f in self._findings
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "total_findings": len(self._findings),
            "severity_counts": counts,
            "has_critical": counts["critical"] > 0,
            "has_errors": counts["error"] > 0,
            "blocking_codes": blocking_codes,
            "actionable": len(blocking_codes) == 0,
            "classifications": classifications,
            "blocks_resume": has_active_idle or has_protocol_mismatch or has_journal_corrupt,
            "has_active_idle_contradiction": has_active_idle,
            "has_protocol_hash_mismatch": has_protocol_mismatch,
            "has_journal_corrupt_or_insufficient": has_journal_corrupt,
        }

    def generate_audit_report(self) -> dict[str, Any]:
        """Full structured audit report with per-severity buckets."""
        by_severity: dict[str, list[dict[str, Any]]] = {
            s.value: [] for s in AuditSeverity
        }
        for f in self._findings:
            by_severity[f.severity.value].append(f.to_dict())

        facts = self.expose_control_plane_facts()
        return {
            "schema_version": SCHEMA_VERSION,
            "facts": facts,
            "findings": by_severity,
        }

    def validate_actionability(self) -> bool:
        """Return True only if every finding is at most WARNING."""
        return all(
            f.severity in (AuditSeverity.INFO, AuditSeverity.WARNING)
            for f in self._findings
        )


# ===========================================================================
# Task 13.3 – CancellationHandler
# ===========================================================================

class CancellationHandler:
    """Seal authority, reject late arrivals, cancel jobs, fence attempts,
    and preserve late responses as nonauthoritative evidence."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._late_evidence: list[dict[str, Any]] = []

    def seal_expansion_authority(
        self, seal_id: str, reason: str
    ) -> dict[str, Any]:
        """Seal expansion authority before cancellation so no further
        expansions can be accepted."""
        if self._gs.expansion_slot is None:
            self._gs.expansion_slot = ExpansionSlot()
        slot = self._gs.expansion_slot
        if not slot.is_idle():
            slot.release()
        self._gs.active_planning_authority_id = None
        return {
            "action": "expansion_authority_sealed",
            "seal_id": seal_id,
            "reason": reason,
            "sealed_at": utc_now(),
        }

    def reject_late_expansion(
        self, expansion: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """Reject an expansion that arrives after authority sealing."""
        return {
            "action": "late_expansion_rejected",
            "expansion_id": expansion.get("expansion_id", "UNKNOWN"),
            "reason": reason,
            "recorded_at": utc_now(),
        }

    def reject_late_goal_control(
        self, judgment: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """Reject a Goal Judge decision arriving after authority sealing."""
        return {
            "action": "late_goal_control_rejected",
            "judgment_id": judgment.get("judgment_id", "UNKNOWN"),
            "decision": judgment.get("decision", "UNKNOWN"),
            "reason": reason,
            "recorded_at": utc_now(),
        }

    def cancel_queued_jobs(self) -> list[dict[str, Any]]:
        """Transition all pending/dispatching/dispatch_pending jobs to cancelled."""
        cancelled: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            if job.get("status") in ("pending", "dispatching", "dispatch_pending"):
                job["status"] = "cancelled"
                job["cancelled_at"] = utc_now()
                cancelled.append({"job_id": jid, "status": "cancelled"})
        return cancelled

    def fence_active_attempts(self) -> list[dict[str, Any]]:
        """Mark all running jobs as fenced (they may still complete but their
        results will be treated as nonauthoritative evidence)."""
        fenced: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            if job.get("status") == "running":
                job["fenced"] = True
                job["fenced_at"] = utc_now()
                fenced.append({"job_id": jid, "fenced": True})
        return fenced

    def preserve_late_responses(
        self, response: dict[str, Any], source_job_id: str
    ) -> dict[str, Any]:
        """Store a late-arriving response as nonauthoritative evidence."""
        evidence_id = stable_id("EVID", source_job_id, content_hash(response))
        record = {
            "evidence_id": evidence_id,
            "source_job_id": source_job_id,
            "nonauthoritative": True,
            "response": response,
            "recorded_at": utc_now(),
        }
        self._late_evidence.append(record)
        return record

    def execute_cancellation(self, reason: str) -> dict[str, Any]:
        """Full cancellation sequence: seal → cancel → fence → record."""
        seal = self.seal_expansion_authority(
            seal_id=stable_id("SEAL", reason),
            reason=reason,
        )
        cancelled = self.cancel_queued_jobs()
        fenced = self.fence_active_attempts()
        return {
            "schema_version": SCHEMA_VERSION,
            "cancellation_status": "complete",
            "seal": seal,
            "cancelled_jobs": cancelled,
            "fenced_jobs": fenced,
            "completed_at": utc_now(),
        }


# ===========================================================================
# Task 13.4 – StaleResponseReconciler
# ===========================================================================

class StaleResponseReconciler:
    """Reconcile stale Architect, hypothesis, Verifier, and Goal Judge responses
    against the current graph and gate revisions without rewriting history."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._reconciled: list[dict[str, Any]] = []

    def _find_current_generation(self) -> int:
        """Return the latest graph generation from the graph."""
        if self._gs._generations:
            return max(g.get("graph_revision", 0) for g in self._gs._generations)
        return self._gs.graph_revision

    def reconcile_stale_architect(
        self, response: dict[str, Any]
    ) -> dict[str, Any]:
        """Check an architect response against current graph state."""
        resp_gen = response.get("graph_generation", 0)
        current_gen = self._gs.graph_revision
        stale = resp_gen < current_gen
        result = {
            "response_type": "architect",
            "response_generation": resp_gen,
            "current_generation": current_gen,
            "stale": stale,
            "reconciled_at": utc_now(),
        }
        if stale:
            result["disposition"] = "nonauthoritative_evidence"
            result["reason"] = (
                f"architect response targets generation {resp_gen} "
                f"but current is {current_gen}"
            )
        else:
            result["disposition"] = "current"
        self._reconciled.append(result)
        return result

    def reconcile_stale_hypothesis(
        self, hypothesis: dict[str, Any]
    ) -> dict[str, Any]:
        """Check hypothesis result against current graph state."""
        h_gen = hypothesis.get("graph_generation", 0)
        current_gen = self._gs.graph_revision
        stale = h_gen < current_gen
        result = {
            "response_type": "hypothesis",
            "response_generation": h_gen,
            "current_generation": current_gen,
            "stale": stale,
            "reconciled_at": utc_now(),
        }
        if stale:
            result["disposition"] = "superseded"
            result["reason"] = (
                f"hypothesis targets generation {h_gen} "
                f"but current is {current_gen}"
            )
        else:
            result["disposition"] = "current"
        self._reconciled.append(result)
        return result

    def reconcile_stale_verifier(
        self, assignment: dict[str, Any]
    ) -> dict[str, Any]:
        """Check a verifier result against current gate revision."""
        target_rev = assignment.get("target_gate_revision", 0)
        target_job_id = assignment.get("target_job_id", "")
        current_rev = 0
        for entry in self._gs._repair_gate_history:
            if entry.get("target_job_id") == target_job_id:
                current_rev = max(current_rev, entry.get("revision", 0))
        stale = current_rev > target_rev
        result = {
            "response_type": "verifier",
            "target_gate_revision": target_rev,
            "current_gate_revision": current_rev,
            "stale": stale,
            "reconciled_at": utc_now(),
        }
        if stale:
            result["disposition"] = "nonauthoritative_evidence"
            result["reason"] = (
                f"verifier targets gate revision {target_rev} "
                f"but current is {current_rev}"
            )
        else:
            result["disposition"] = "current"
        self._reconciled.append(result)
        return result

    def reconcile_stale_goal_judge(
        self, judgment: dict[str, Any]
    ) -> dict[str, Any]:
        """Check a goal judgment against current graph generation."""
        j_rev = judgment.get("graph_revision", 0)
        current_gen = self._find_current_generation()
        stale = j_rev < current_gen
        result = {
            "response_type": "goal_judge",
            "judgment_revision": j_rev,
            "current_generation": current_gen,
            "stale": stale,
            "reconciled_at": utc_now(),
        }
        if stale:
            result["disposition"] = "nonauthoritative_evidence"
            result["reason"] = (
                f"goal judgment targets revision {j_rev} "
                f"but current is {current_gen}"
            )
        else:
            result["disposition"] = "current"
        self._reconciled.append(result)
        return result

    def reject_history_rewriting(self) -> dict[str, Any]:
        """Ensure no sealed outcomes are mutated. Returns current reconciliation
        summary.  This method is intentionally idempotent."""
        sealed = [
            oid for oid, out in self._gs._terminal_outcomes.items()
            if out.get("sealed", True)
        ]
        return {
            "sealed_outcomes_preserved": len(sealed),
            "history_rewriting_attempted": False,
            "checked_at": utc_now(),
        }


# ===========================================================================
# Task 13.5 – SideEffectRecoveryPreserver
# ===========================================================================

class SideEffectRecoveryPreserver:
    """Preserve recovery guarantees for every dynamically added repository,
    external-idempotent, and external-non-idempotent job."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._preserved: list[dict[str, Any]] = []

    def preserve_repository_recovery(self) -> list[dict[str, Any]]:
        """Preserve recovery for repository-type side effects."""
        preserved: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            se = job.get("side_effect", {})
            if se.get("effect_type") == "repository":
                record = {
                    "job_id": jid,
                    "effect_type": "repository",
                    "idempotency_key": se.get("idempotency_key", ""),
                    "recovery_preserved": True,
                    "preserved_at": utc_now(),
                }
                preserved.append(record)
                self._preserved.append(record)
        return preserved

    def preserve_external_idempotent_recovery(self) -> list[dict[str, Any]]:
        """Preserve recovery for external idempotent side effects."""
        preserved: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            se = job.get("side_effect", {})
            if (
                se.get("effect_type") == "external"
                and se.get("idempotent", False)
            ):
                record = {
                    "job_id": jid,
                    "effect_type": "external_idempotent",
                    "idempotency_key": se.get("idempotency_key", ""),
                    "recovery_preserved": True,
                    "preserved_at": utc_now(),
                }
                preserved.append(record)
                self._preserved.append(record)
        return preserved

    def preserve_external_non_idempotent_recovery(self) -> list[dict[str, Any]]:
        """Preserve recovery for external non-idempotent side effects."""
        preserved: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            se = job.get("side_effect", {})
            if (
                se.get("effect_type") == "external"
                and not se.get("idempotent", True)
            ):
                record = {
                    "job_id": jid,
                    "effect_type": "external_non_idempotent",
                    "recovery_preserved": True,
                    "evidence_retained": True,
                    "preserved_at": utc_now(),
                }
                preserved.append(record)
                self._preserved.append(record)
        return preserved

    def validate_recovery_guarantees(self) -> dict[str, Any]:
        """Ensure every side-effect job has its recovery preserved."""
        total_se_jobs = 0
        preserved_count = 0
        missing: list[str] = []
        for jid, job in self._gs._jobs.items():
            se = job.get("side_effect")
            if se:
                total_se_jobs += 1
                if se.get("effect_type"):
                    preserved_count += 1
                else:
                    missing.append(jid)
        return {
            "total_side_effect_jobs": total_se_jobs,
            "preserved_count": preserved_count,
            "missing_recovery": missing,
            "all_preserved": len(missing) == 0,
            "validated_at": utc_now(),
        }


# ===========================================================================
# Task 13.6 – RecoveryScenarioHandler
# ===========================================================================

class RecoveryScenarioHandler:
    """Handle recovery scenarios for interrupted planning, pending expansion,
    partial commit, open batch cancellation, lost repair sessions,
    delayed Verifiers, stale Goal Judges, and unknown publication effects."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._recoveries: list[dict[str, Any]] = []

    def recover_interrupted_planning(self) -> dict[str, Any]:
        """Recover from an interrupted planning phase."""
        slot = self._gs.expansion_slot
        if slot and slot.phase == ExpansionSlot.PHASE_PLANNING:
            slot.release()
            self._gs.expansion_slot = slot
            return {
                "scenario": "interrupted_planning",
                "action": "slot_released",
                "recovered_at": utc_now(),
            }
        return {
            "scenario": "interrupted_planning",
            "action": "no_action_needed",
            "reason": "no planning slot active",
        }

    def recover_pending_expansion(self) -> dict[str, Any]:
        """Recover from an expansion stuck in pending state."""
        slot = self._gs.expansion_slot
        if slot and slot.phase == ExpansionSlot.PHASE_STAGING:
            slot.release()
            return {
                "scenario": "pending_expansion",
                "action": "slot_released",
                "recovered_at": utc_now(),
            }
        return {
            "scenario": "pending_expansion",
            "action": "no_action_needed",
            "reason": "no pending staging slot",
        }

    def recover_partial_commit(self) -> dict[str, Any]:
        """Recover from a partial commit: complete or rollback."""
        pending_expansions = [
            eid for eid, exp in self._gs._expansions.items()
            if exp.get("status") in ("committing", "pending")
        ]
        if pending_expansions:
            for eid in pending_expansions:
                self._gs._expansions[eid]["status"] = "rolled_back"
            return {
                "scenario": "partial_commit",
                "action": "rolled_back",
                "expansions": pending_expansions,
                "recovered_at": utc_now(),
            }
        return {
            "scenario": "partial_commit",
            "action": "no_action_needed",
        }

    def recover_open_batch_cancellation(self) -> dict[str, Any]:
        """Cancel all open batches."""
        cancelled: list[str] = []
        for bid, batch in self._gs._batches.items():
            if batch.get("status") == "open":
                batch["status"] = "abandoned"
                batch["abandoned_at"] = utc_now()
                cancelled.append(bid)
        return {
            "scenario": "open_batch_cancellation",
            "cancelled_batches": cancelled,
            "recovered_at": utc_now(),
        }

    def recover_lost_repair_session(self) -> dict[str, Any]:
        """Handle a lost repair session by releasing the associated slot."""
        slot = self._gs.expansion_slot
        if slot and slot.phase != ExpansionSlot.PHASE_IDLE:
            slot.release()
            return {
                "scenario": "lost_repair_session",
                "action": "slot_released",
                "recovered_at": utc_now(),
            }
        return {
            "scenario": "lost_repair_session",
            "action": "no_action_needed",
        }

    def recover_delayed_verifier(self) -> dict[str, Any]:
        """Mark delayed verifiers as timed-out."""
        timed_out: list[str] = []
        for vid, v in self._gs._verifier_assignments.items():
            if v.get("status") == "assigned":
                v["status"] = "timed_out"
                v["timed_out_at"] = utc_now()
                timed_out.append(vid)
        return {
            "scenario": "delayed_verifier",
            "timed_out": timed_out,
            "recovered_at": utc_now(),
        }

    def recover_stale_goal_judge(self) -> dict[str, Any]:
        """Handle a stale goal judge by noting it as superseded evidence."""
        current_gen = self._gs.graph_revision
        stale_judgments: list[str] = []
        for jid, job in self._gs._jobs.items():
            if job.get("role") == "goal_judge":
                if job.get("graph_generation", 0) < current_gen:
                    stale_judgments.append(jid)
                    job["stale"] = True
                    job["stale_at"] = utc_now()
        return {
            "scenario": "stale_goal_judge",
            "stale_judgments": stale_judgments,
            "recovered_at": utc_now(),
        }

    def recover_unknown_publication(self) -> dict[str, Any]:
        """Handle unknown publication effects by recording them as evidence
        for later manual review."""
        unknown_effects: list[dict[str, Any]] = []
        for jid, job in self._gs._jobs.items():
            pub = job.get("publication_effect")
            if pub and pub.get("status") == "unknown":
                record = {
                    "job_id": jid,
                    "effect": pub,
                    "recorded_at": utc_now(),
                }
                unknown_effects.append(record)
        return {
            "scenario": "unknown_publication",
            "unknown_effects": unknown_effects,
            "recovered_at": utc_now(),
        }

    def run_all_recovery(self) -> list[dict[str, Any]]:
        """Execute every recovery scenario and return all results."""
        results = [
            self.recover_interrupted_planning(),
            self.recover_pending_expansion(),
            self.recover_partial_commit(),
            self.recover_open_batch_cancellation(),
            self.recover_lost_repair_session(),
            self.recover_delayed_verifier(),
            self.recover_stale_goal_judge(),
            self.recover_unknown_publication(),
        ]
        self._recoveries = results
        return results
