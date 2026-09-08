"""v6 prompt rendering for dynamic orchestration jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator_core import content_hash, canonical_bytes


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(canonical_bytes(value))


class PromptRenderer:
    """Renders v6 orchestration prompts from persisted state records."""

    def __init__(self, run_id: str, goal: str) -> None:
        self.run_id = run_id
        self.goal = goal

    # ------------------------------------------------------------------
    # Core context fields
    # ------------------------------------------------------------------

    def render_workflow_context(
        self,
        job_id: str,
        activation_id: str,
        context_snapshot_id: str,
        cycle_id: str,
        graph_revision: int,
        graph_digest: str,
        campaign_envelope_id: str,
        job_ids: list[str],
        expansion_ledger: list[str] | None = None,
    ) -> str:
        """Render all workflow fields required by ordinary dynamic jobs."""
        lines = [
            f"Run: {self.run_id}",
            f"Goal: {self.goal}",
            f"Job: {job_id}",
            f"Activation: {activation_id}",
            f"Context Snapshot: {context_snapshot_id}",
            f"Cycle: {cycle_id}",
            f"Graph Revision: {graph_revision}",
            f"Graph Digest: {graph_digest}",
            f"Campaign Envelope: {campaign_envelope_id}",
            f"Sibling Jobs: {', '.join(job_ids)}",
        ]
        if expansion_ledger:
            lines.append(f"Expansion Ledger: {', '.join(expansion_ledger)}")
        return "\n".join(lines)

    def render_context_snapshot(
        self,
        snapshot_id: str,
        versions: dict[str, int],
        digest: str,
    ) -> str:
        """Render context snapshot with versions and digests."""
        version_parts = []
        for key in ("goal_gates", "findings", "graph"):
            if key in versions:
                version_parts.append(f"{key}={versions[key]}")
        return (
            f"Context Snapshot: {snapshot_id}\n"
            f"Versions: {', '.join(version_parts)}\n"
            f"Digest: {digest}"
        )

    def render_escalation(self, escalation_paths: list[dict[str, str]]) -> str:
        """Render escalation paths for the job."""
        if not escalation_paths:
            return "Escalation: none configured"
        parts = []
        for idx, path in enumerate(escalation_paths, 1):
            target = path.get("target_role", "unknown")
            reason = path.get("reason", "")
            parts.append(f"  {idx}. Target: {target} — {reason}")
        return "Escalation Paths:\n" + "\n".join(parts)

    def render_recovery(self, recovery_record: dict[str, Any] | None) -> str:
        """Render recovery instructions from a recovery record."""
        if recovery_record is None:
            return "Recovery: no active recovery"
        strategy = recovery_record.get("strategy", "unknown")
        status = recovery_record.get("status", "unknown")
        reason = recovery_record.get("reason", "")
        return (
            f"Recovery Strategy: {strategy}\n"
            f"Recovery Status: {status}\n"
            f"Recovery Reason: {reason}"
        )

    def render_authority(
        self,
        authority_id: str,
        role: str,
        scope: dict[str, bool],
        granted_at: str,
        expires_at: str,
    ) -> str:
        """Render authority scope and limits."""
        scope_parts = []
        for key in ("expansion", "repair", "verification"):
            scope_parts.append(f"{key}={scope.get(key, False)}")
        return (
            f"Authority: {authority_id}\n"
            f"Role: {role}\n"
            f"Scope: {', '.join(scope_parts)}\n"
            f"Granted: {granted_at}\n"
            f"Expires: {expires_at}"
        )

    def render_relationships(self, edges: list[dict[str, Any]]) -> str:
        """Render job dependency relationships."""
        if not edges:
            return "Relationships: none"
        parts = []
        for edge in edges:
            source = edge.get("source_job_id", "?")
            target = edge.get("target_job_id", "?")
            etype = edge.get("edge_type", "?")
            parts.append(f"  {source} --[{etype}]--> {target}")
        return "Job Relationships:\n" + "\n".join(parts)

    def render_campaign(
        self,
        envelope_id: str,
        campaign_id: str,
        strategy: str,
        version: int,
        limits: dict[str, int],
    ) -> str:
        """Render campaign envelope."""
        return (
            f"Campaign Envelope: {envelope_id}\n"
            f"Campaign: {campaign_id}\n"
            f"Strategy: {strategy}\n"
            f"Version: {version}\n"
            f"Limits: max_cycles={limits.get('max_cycles', '?')}, "
            f"max_jobs_per_cycle={limits.get('max_jobs_per_cycle', '?')}, "
            f"max_total_jobs={limits.get('max_total_jobs', '?')}"
        )

    def render_cycle(
        self,
        cycle_id: str,
        graph_revision: int,
        jobs_completed: int,
        jobs_total: int,
        findings_count: int,
    ) -> str:
        """Render cycle identity and progress."""
        return (
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n"
            f"Progress: {jobs_completed}/{jobs_total} jobs completed\n"
            f"Findings: {findings_count}"
        )

    def render_graph(
        self,
        graph_revision: int,
        graph_digest: str,
        vertex_count: int,
        edge_count: int,
    ) -> str:
        """Render graph state."""
        return (
            f"Graph Revision: {graph_revision}\n"
            f"Graph Digest: {graph_digest}\n"
            f"Vertices: {vertex_count}\n"
            f"Edges: {edge_count}"
        )

    def render_batch(
        self,
        batch_id: str,
        status: str,
        job_ids: list[str],
    ) -> str:
        """Render batch membership."""
        return (
            f"Batch: {batch_id}\n"
            f"Batch Status: {status}\n"
            f"Batch Members: {', '.join(job_ids)}"
        )

    def render_limits(
        self,
        campaign_limits: dict[str, int],
        graph_limits: dict[str, int],
    ) -> str:
        """Render immutable ceilings."""
        return (
            f"Immutable Ceilings:\n"
            f"  Campaign: max_cycles={campaign_limits.get('max_cycles', '?')}, "
            f"max_jobs_per_cycle={campaign_limits.get('max_jobs_per_cycle', '?')}, "
            f"max_total_jobs={campaign_limits.get('max_total_jobs', '?')}\n"
            f"  Graph: max_vertices={graph_limits.get('max_vertices', '?')}, "
            f"max_edges={graph_limits.get('max_edges', '?')}, "
            f"max_expansion_depth={graph_limits.get('max_expansion_depth', '?')}"
        )

    # ------------------------------------------------------------------
    # Role-specific prompt contracts
    # ------------------------------------------------------------------

    def render_goal_judge_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        goal_gate_id: str,
        gate_key: str,
        requirement: str,
        evidence_requirements: list[str],
        definition_digest: str,
    ) -> str:
        """Render Goal Judge continuation planning prompt."""
        return (
            f"You are the Goal Judge for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Goal Gate: {goal_gate_id}\n"
            f"Gate Key: {gate_key}\n"
            f"Requirement: {requirement}\n"
            f"Evidence Requirements: {', '.join(evidence_requirements)}\n"
            f"Definition Digest: {definition_digest}\n\n"
            f"Evaluate whether the goal has been achieved, is blocked, or "
            f"requires continuation. Record a goal judgment with decision "
            f"of GOAL_ACHIEVED, CONTINUE, BLOCKED, REDIRECT, or ABANDONED."
        )

    def render_hypothesis_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        finding_id: str,
        finding_description: str,
        severity: str,
        confidence: float,
    ) -> str:
        """Render hypothesis investigator prompt."""
        return (
            f"You are a Hypothesis Investigator for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n\n"
            f"Target Finding: {finding_id}\n"
            f"Description: {finding_description}\n"
            f"Severity: {severity}\n"
            f"Confidence: {confidence}\n\n"
            f"Investigate this finding and produce a hypothesis result. "
            f"Confirm, refute, or declare inconclusive. "
            f"Record status as confirmed, refuted, inconclusive, or superseded."
        )

    def render_synthesis_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        hypothesis_result_ids: list[str],
    ) -> str:
        """Render Synthesis Architect prompt."""
        return (
            f"You are the Synthesis Architect for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n\n"
            f"Hypothesis Results to Synthesize: {', '.join(hypothesis_result_ids)}\n\n"
            f"Synthesize findings into a conclusion. Record conclusion as "
            f"root_cause_identified, partial_understanding, "
            f"no_actionable_cause, or needs_further_investigation."
        )

    def render_work_planner_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        plan_type: str,
        target_ids: list[str],
        target_types: list[str],
    ) -> str:
        """Render Work Planner Architect prompt."""
        targets = ", ".join(
            f"{tid} ({ttype})"
            for tid, ttype in zip(target_ids, target_types)
        )
        return (
            f"You are the Work Planner Architect for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n\n"
            f"Plan Type: {plan_type}\n"
            f"Targets: {targets}\n\n"
            f"Design a work plan to address these targets. "
            f"Output a work plan with plan_type, targets, and concrete steps."
        )

    def render_proposal_explore_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
    ) -> str:
        """Render Proposal Explore prompt."""
        return (
            f"You are a Proposal Explore agent for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Explore the current state of the workspace and propose changes. "
            f"Identify what needs to be built or modified to achieve the goal."
        )

    def render_proposal_architect_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
    ) -> str:
        """Render Proposal Architect prompt."""
        return (
            f"You are the Proposal Architect for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Design the implementation architecture for the proposed changes. "
            f"Create a detailed proposal with files, structures, and contracts."
        )

    def render_proposal_finalize_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
    ) -> str:
        """Render Proposal Finalize prompt."""
        return (
            f"You are the Proposal Finalizer for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Finalize the proposal and produce a deterministic role result. "
            f"Ensure all artifacts are complete and valid."
        )

    def render_implementation_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        scope_description: str,
        allowed_paths: list[str],
    ) -> str:
        """Render implementation job prompt."""
        paths = ", ".join(allowed_paths) if allowed_paths else "as specified"
        return (
            f"You are an Implementation Worker for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Scope: {scope_description}\n"
            f"Allowed Paths: {paths}\n\n"
            f"Implement the changes described in the scope. "
            f"Write report.md with your findings and results."
        )

    def render_repair_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        target_job_id: str,
        finding_id: str,
        finding_description: str,
        repair_strategy: str,
    ) -> str:
        """Render repair job prompt."""
        return (
            f"You are a Repair Worker for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Target Job: {target_job_id}\n"
            f"Finding: {finding_id}\n"
            f"Finding Description: {finding_description}\n"
            f"Repair Strategy: {repair_strategy}\n\n"
            f"Apply the repair strategy to address the finding. "
            f"Write report.md documenting the repair."
        )

    def render_verifier_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        assignment_id: str,
        target_job_id: str,
        target_gate_id: str,
        target_gate_revision: int,
        evidence_refs: list[str],
        required_evidence: list[dict[str, str]] | None = None,
        accepted_reports: list[dict[str, str]] | None = None,
        condition_id: str = "",
        graph_generation: int = 0,
    ) -> str:
        """Render Verifier prompt."""
        refs = "\n".join(f"  - {ref}" for ref in evidence_refs)
        parts = [
            f"You are a Verifier for run {self.run_id}.\n",
            f"Goal: {self.goal}",
            f"Job: {job_id}",
            f"Activation: {activation_id}",
            f"Cycle: {cycle_id}",
            f"Graph Revision: {graph_revision}",
            f"Graph Generation: {graph_generation}\n",
            f"Assignment: {assignment_id}",
            f"Target Job: {target_job_id}",
            f"Target Gate: {target_gate_id}",
            f"Target Gate Revision: {target_gate_revision}",
            f"Condition: {condition_id}\n",
            f"Evidence References:\n{refs}\n",
        ]
        if required_evidence:
            contract_refs = [
                f"{a.get('artifact_ref', '?')} (sha256: {a.get('artifact_digest', '?')})"
                for a in required_evidence
            ]
            parts.append(self.render_result_contract(
                ["passed", "failed", "not_run", "unavailable", "unknown"],
                contract_refs,
            ))
            parts.append("")
        if accepted_reports:
            parts.append(self.render_accepted_reports(accepted_reports))
            parts.append("")
        parts.append(
            "Verify the target job's work against its gate requirements. "
            "Record condition results with status passed, failed, "
            "not_run, unavailable, or unknown."
        )
        return "\n".join(parts)

    def render_integration_verifier_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        target_job_ids: list[str],
        integration_requirements: list[str],
    ) -> str:
        """Render integration Verifier prompt."""
        targets = ", ".join(target_job_ids)
        reqs = "\n".join(f"  - {r}" for r in integration_requirements)
        return (
            f"You are an Integration Verifier for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Target Jobs: {targets}\n\n"
            f"Integration Requirements:\n{reqs}\n\n"
            f"Verify that all target jobs integrate correctly. "
            f"Record condition results for each integration requirement."
        )

    def render_implementation_review_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        reviewed_job_id: str,
        review_scope: list[str],
    ) -> str:
        """Render Implementation Review Architect prompt."""
        scope = ", ".join(review_scope) if review_scope else "full"
        return (
            f"You are the Implementation Review Architect for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Reviewed Job: {reviewed_job_id}\n"
            f"Review Scope: {scope}\n\n"
            f"Review the implementation and produce a finding disposition. "
            f"Record status as verified, refuted, superseded, or accepted_risk."
        )

    def render_branch_init_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        branch_name: str,
    ) -> str:
        """Render branch initialization prompt."""
        return (
            f"You are the Branch Initializer for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Branch: {branch_name}\n\n"
            f"Initialize the branch for this work cycle. "
            f"Record a deterministic role result for branch_initializer."
        )

    def render_openspec_finalization_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        spec_files: list[str],
    ) -> str:
        """Render OpenSpec finalization prompt."""
        files = ", ".join(spec_files) if spec_files else "none specified"
        return (
            f"You are the OpenSpec Finalizer for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Spec Files: {files}\n\n"
            f"Finalize the OpenSpec artifacts. "
            f"Record a deterministic role result for openspec_finalizer."
        )

    def render_commit_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        commit_message: str,
        files_to_commit: list[str],
    ) -> str:
        """Render commit worker prompt."""
        files = "\n".join(f"  - {f}" for f in files_to_commit)
        return (
            f"You are the Commit Worker for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Commit Message: {commit_message}\n\n"
            f"Files to Commit:\n{files}\n\n"
            f"Stage and commit the specified files. "
            f"Record a deterministic role result for commit_worker."
        )

    def render_push_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        remote: str,
        branch: str,
    ) -> str:
        """Render push worker prompt."""
        return (
            f"You are the Push Worker for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Remote: {remote}\n"
            f"Branch: {branch}\n\n"
            f"Push the committed changes to the remote. "
            f"Record a deterministic role result for push_worker."
        )

    def render_remote_verification_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        verification_target: str,
        verification_checks: list[str],
    ) -> str:
        """Render remote verification prompt."""
        checks = "\n".join(f"  - {c}" for c in verification_checks)
        return (
            f"You are the Remote Verifier for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Verification Target: {verification_target}\n\n"
            f"Verification Checks:\n{checks}\n\n"
            f"Perform remote verification checks. "
            f"Record a deterministic role result for remote_verifier."
        )

    # ------------------------------------------------------------------
    # Verifier target context, accepted reports, result contract
    # ------------------------------------------------------------------

    def render_verifier_target_context(
        self,
        target_job_id: str,
        target_gate_id: str,
        target_gate_revision: int,
        condition_id: str,
        condition_status: str,
    ) -> str:
        """Render exact target job, condition, and gate revision."""
        return (
            f"Verifier Target Context:\n"
            f"  Target Job: {target_job_id}\n"
            f"  Target Gate: {target_gate_id}\n"
            f"  Target Gate Revision: {target_gate_revision}\n"
            f"  Condition: {condition_id}\n"
            f"  Condition Status: {condition_status}"
        )

    def render_accepted_reports(
        self,
        report_refs: list[dict[str, str]],
    ) -> str:
        """Render accepted report references and current hashes."""
        if not report_refs:
            return "Accepted Reports: none"
        parts = []
        for ref in report_refs:
            ref_str = ref.get("ref", "?")
            digest = ref.get("content_sha256", ref.get("digest", "?"))
            parts.append(f"  - {ref_str} (sha256: {digest})")
        return "Accepted Reports:\n" + "\n".join(parts)

    def render_result_contract(
        self,
        required_statuses: list[str],
        required_evidence: list[str],
    ) -> str:
        """Render target-scoped result requirements."""
        statuses = ", ".join(required_statuses) if required_statuses else "passed"
        evidence = "\n".join(f"  - {e}" for e in required_evidence)
        return (
            f"Result Contract:\n"
            f"  Required Statuses: {statuses}\n"
            f"  Required Evidence:\n{evidence}"
        )

    # ------------------------------------------------------------------
    # Dependency artifact integrity
    # ------------------------------------------------------------------

    @staticmethod
    def rehash_dependency_artifacts(
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rehash dependency artifacts before dispatch.

        Returns a new list with freshly computed content_sha256 for each
        artifact. The input list is not mutated.
        """
        rehashed = []
        for artifact in artifacts:
            entry = dict(artifact)
            content = entry.get("content")
            if content is not None:
                if isinstance(content, str):
                    entry["content_sha256"] = _sha256_bytes(content.encode("utf-8"))
                elif isinstance(content, bytes):
                    entry["content_sha256"] = _sha256_bytes(content)
                else:
                    entry["content_sha256"] = _sha256_json(content)
            elif "content_sha256" not in entry:
                entry["content_sha256"] = "0" * 64
            rehashed.append(entry)
        return rehashed

    @staticmethod
    def validate_dependency_integrity(
        original: list[dict[str, Any]],
        rehashed: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """Validate that rehashed artifacts match originals.

        Returns (valid, errors). If original has content_sha256 and
        rehashed differs, the artifact changed. If an original entry is
        missing entirely, it was lost.
        """
        errors: list[str] = []
        originals_by_id = {
            a.get("artifact_id", a.get("ref", "")): a for a in original
        }
        rehashed_by_id = {
            a.get("artifact_id", a.get("ref", "")): a for a in rehashed
        }

        for aid, orig in originals_by_id.items():
            if aid not in rehashed_by_id:
                errors.append(f"missing artifact: {aid}")
                continue
            orig_hash = orig.get("content_sha256")
            new_hash = rehashed_by_id[aid].get("content_sha256")
            if orig_hash and new_hash and orig_hash != new_hash:
                errors.append(f"changed artifact: {aid} (expected {orig_hash}, got {new_hash})")

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Continuation and replacement prompts
    # ------------------------------------------------------------------

    def render_continuation_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        answers: list[dict[str, str]],
        related_reports: list[dict[str, str]],
    ) -> str:
        """Render continuation prompt with authoritative answers and reports."""
        answer_parts = []
        for ans in answers:
            question = ans.get("question", "?")
            answer = ans.get("answer", "?")
            answer_parts.append(f"  Q: {question}\n  A: {answer}")
        answers_block = "\n".join(answer_parts) if answer_parts else "  (none)"

        report_parts = []
        for rpt in related_reports:
            ref = rpt.get("ref", "?")
            summary = rpt.get("summary", "")
            report_parts.append(f"  - {ref}: {summary}")
        reports_block = "\n".join(report_parts) if report_parts else "  (none)"

        return (
            f"You are continuing work for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Authoritative Answers:\n{answers_block}\n\n"
            f"Related Reports:\n{reports_block}\n\n"
            f"Continue your work using the above context."
        )

    def render_replacement_prompt(
        self,
        job_id: str,
        activation_id: str,
        cycle_id: str,
        graph_revision: int,
        original_prompt_summary: str,
        transport_evidence: dict[str, str],
        checkpoint_ref: str | None,
        workspace_evidence: list[dict[str, str]],
        related_reports: list[dict[str, str]],
        pending_input: list[dict[str, str]] | None,
        recovery_findings: list[dict[str, str]] | None,
    ) -> str:
        """Render replacement prompt with full recovery context."""
        transport_parts = []
        for key, val in transport_evidence.items():
            transport_parts.append(f"  {key}: {val}")
        transport_block = "\n".join(transport_parts) if transport_parts else "  (none)"

        ws_parts = []
        for we in workspace_evidence:
            ref = we.get("ref", "?")
            status = we.get("status", "?")
            ws_parts.append(f"  - {ref} [{status}]")
        ws_block = "\n".join(ws_parts) if ws_parts else "  (none)"

        report_parts = []
        for rpt in related_reports:
            ref = rpt.get("ref", "?")
            summary = rpt.get("summary", "")
            report_parts.append(f"  - {ref}: {summary}")
        reports_block = "\n".join(report_parts) if report_parts else "  (none)"

        input_parts = []
        if pending_input:
            for inp in pending_input:
                question = inp.get("question", "?")
                context = inp.get("context", "")
                input_parts.append(f"  Q: {question}\n  Context: {context}")
        input_block = "\n".join(input_parts) if input_parts else "  (none)"

        recovery_parts = []
        if recovery_findings:
            for rf in recovery_findings:
                strategy = rf.get("strategy", "?")
                reason = rf.get("reason", "")
                recovery_parts.append(f"  Strategy: {strategy} — {reason}")
        recovery_block = "\n".join(recovery_parts) if recovery_parts else "  (none)"

        cp = checkpoint_ref if checkpoint_ref else "(none)"
        return (
            f"You are replacing a failed/interrupted worker for run {self.run_id}.\n\n"
            f"Goal: {self.goal}\n"
            f"Job: {job_id}\n"
            f"Activation: {activation_id}\n"
            f"Cycle: {cycle_id}\n"
            f"Graph Revision: {graph_revision}\n\n"
            f"Original Prompt Summary:\n  {original_prompt_summary}\n\n"
            f"Transport Evidence:\n{transport_block}\n\n"
            f"Checkpoint: {cp}\n\n"
            f"Workspace Evidence:\n{ws_block}\n\n"
            f"Related Reports:\n{reports_block}\n\n"
            f"Pending Input:\n{input_block}\n\n"
            f"Recovery Findings:\n{recovery_block}\n\n"
            f"Resume work using the above context. Do not repeat "
            f"non-idempotent actions."
        )
