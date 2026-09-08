"""v6 prompt conformance tests.

Proves dynamically generated prompts contain every required role field
and never expose root mutation instructions to workers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prompt_v6 import PromptRenderer  # noqa: E402

TEST_RUN_ID = "2026-01-15T103000Z-test-run"
TEST_GOAL = "fix the login bug"
TEST_JOB_ID = "J-ABCDEFGHIJKLMNO"
TEST_ACTIVATION_ID = "ACT-ABCDEFGHIJKLMNO"
TEST_CYCLE_ID = "CYC-ABCDEFGHIJKLMNO"
TEST_GRAPH_REVISION = 3
TEST_GRAPH_DIGEST = "a" * 64
TEST_CAMPAIGN_ENVELOPE_ID = "ENV-ABCDEFGHIJKLMNO"
TEST_AUTHORITY_ID = "AUT-ABCDEFGHIJKLMNO"
TEST_SNAPSHOT_ID = "SNP-ABCDEFGHIJKLMNO"
TEST_DISPATCH_ID = "DSP-ABCDEFGHIJKLMNO"

ROOT_MUTATION_KEYWORDS = [
    "init --request-file",
    "register --run",
    "prepare-dispatch",
    "launch-receipt",
    "response-receipt",
    "jobctl ",
    "write_json",
    "atomic_write",
    "load_json",
    "validate_record",
    "load_schema",
]


def _renderer() -> PromptRenderer:
    return PromptRenderer(TEST_RUN_ID, TEST_GOAL)


class WorkflowContextTest(unittest.TestCase):
    """Task 4.1: Every persisted workflow field is rendered."""

    def test_render_workflow_context_includes_all_fields(self) -> None:
        r = _renderer()
        text = r.render_workflow_context(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            context_snapshot_id=TEST_SNAPSHOT_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            graph_digest=TEST_GRAPH_DIGEST,
            campaign_envelope_id=TEST_CAMPAIGN_ENVELOPE_ID,
            job_ids=["J-AAAA", "J-BBBB"],
            expansion_ledger=["EXP-1"],
        )
        self.assertIn(TEST_RUN_ID, text)
        self.assertIn(TEST_GOAL, text)
        self.assertIn(TEST_JOB_ID, text)
        self.assertIn(TEST_ACTIVATION_ID, text)
        self.assertIn(TEST_SNAPSHOT_ID, text)
        self.assertIn(TEST_CYCLE_ID, text)
        self.assertIn(str(TEST_GRAPH_REVISION), text)
        self.assertIn(TEST_GRAPH_DIGEST, text)
        self.assertIn(TEST_CAMPAIGN_ENVELOPE_ID, text)
        self.assertIn("J-AAAA", text)
        self.assertIn("J-BBBB", text)
        self.assertIn("EXP-1", text)

    def test_render_context_snapshot_includes_versions_and_digest(self) -> None:
        r = _renderer()
        text = r.render_context_snapshot(
            snapshot_id=TEST_SNAPSHOT_ID,
            versions={"goal_gates": 2, "findings": 5, "graph": 3},
            digest=TEST_GRAPH_DIGEST,
        )
        self.assertIn(TEST_SNAPSHOT_ID, text)
        self.assertIn("goal_gates=2", text)
        self.assertIn("findings=5", text)
        self.assertIn("graph=3", text)
        self.assertIn(TEST_GRAPH_DIGEST, text)

    def test_render_escalation(self) -> None:
        r = _renderer()
        text = r.render_escalation([
            {"target_role": "repair", "reason": "finding detected"},
        ])
        self.assertIn("repair", text)
        self.assertIn("finding detected", text)

    def test_render_recovery(self) -> None:
        r = _renderer()
        text = r.render_recovery({
            "strategy": "retry",
            "status": "pending",
            "reason": "timeout",
        })
        self.assertIn("retry", text)
        self.assertIn("pending", text)
        self.assertIn("timeout", text)

    def test_render_authority(self) -> None:
        r = _renderer()
        text = r.render_authority(
            authority_id=TEST_AUTHORITY_ID,
            role="verifier",
            scope={"expansion": False, "repair": False, "verification": True},
            granted_at="2026-01-15T10:00:00Z",
            expires_at="2026-01-15T11:00:00Z",
        )
        self.assertIn(TEST_AUTHORITY_ID, text)
        self.assertIn("verifier", text)
        self.assertIn("expansion=False", text)
        self.assertIn("repair=False", text)
        self.assertIn("verification=True", text)

    def test_render_relationships(self) -> None:
        r = _renderer()
        text = r.render_relationships([
            {"source_job_id": "J-AAA", "target_job_id": "J-BBB", "edge_type": "success"},
        ])
        self.assertIn("J-AAA", text)
        self.assertIn("J-BBB", text)
        self.assertIn("success", text)

    def test_render_campaign(self) -> None:
        r = _renderer()
        text = r.render_campaign(
            envelope_id=TEST_CAMPAIGN_ENVELOPE_ID,
            campaign_id="CMP-AAAA",
            strategy="repair",
            version=1,
            limits={"max_cycles": 5, "max_jobs_per_cycle": 10, "max_total_jobs": 50},
        )
        self.assertIn(TEST_CAMPAIGN_ENVELOPE_ID, text)
        self.assertIn("max_cycles=5", text)
        self.assertIn("max_jobs_per_cycle=10", text)
        self.assertIn("max_total_jobs=50", text)

    def test_render_cycle(self) -> None:
        r = _renderer()
        text = r.render_cycle(
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            jobs_completed=3,
            jobs_total=5,
            findings_count=2,
        )
        self.assertIn(TEST_CYCLE_ID, text)
        self.assertIn("3/5", text)
        self.assertIn("2", text)

    def test_render_graph(self) -> None:
        r = _renderer()
        text = r.render_graph(
            graph_revision=TEST_GRAPH_REVISION,
            graph_digest=TEST_GRAPH_DIGEST,
            vertex_count=10,
            edge_count=15,
        )
        self.assertIn(str(TEST_GRAPH_REVISION), text)
        self.assertIn(TEST_GRAPH_DIGEST, text)
        self.assertIn("10", text)
        self.assertIn("15", text)

    def test_render_batch(self) -> None:
        r = _renderer()
        text = r.render_batch(
            batch_id="BAT-AAAA",
            status="sealed",
            job_ids=["J-AAA", "J-BBB"],
        )
        self.assertIn("BAT-AAAA", text)
        self.assertIn("sealed", text)
        self.assertIn("J-AAA", text)
        self.assertIn("J-BBB", text)

    def test_render_limits(self) -> None:
        r = _renderer()
        text = r.render_limits(
            campaign_limits={"max_cycles": 5, "max_jobs_per_cycle": 10, "max_total_jobs": 50},
            graph_limits={"max_vertices": 100, "max_edges": 200, "max_expansion_depth": 5},
        )
        self.assertIn("max_cycles=5", text)
        self.assertIn("max_vertices=100", text)
        self.assertIn("max_expansion_depth=5", text)


class RolePromptContractsTest(unittest.TestCase):
    """Task 4.2: Role-specific prompts contain all required fields."""

    def _assert_no_root_mutation(self, text: str) -> None:
        for kw in ROOT_MUTATION_KEYWORDS:
            self.assertNotIn(kw, text, f"Prompt must not expose root instruction: {kw}")

    def test_goal_judge_prompt(self) -> None:
        r = _renderer()
        text = r.render_goal_judge_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            goal_gate_id="GG-AAAA",
            gate_key="tests_pass",
            requirement="all tests pass",
            evidence_requirements=["test_output", "coverage"],
            definition_digest="b" * 64,
        )
        self.assertIn("Goal Judge", text)
        self.assertIn(TEST_JOB_ID, text)
        self.assertIn(TEST_ACTIVATION_ID, text)
        self.assertIn(TEST_CYCLE_ID, text)
        self.assertIn("GG-AAAA", text)
        self.assertIn("tests_pass", text)
        self.assertIn("all tests pass", text)
        self._assert_no_root_mutation(text)

    def test_hypothesis_prompt(self) -> None:
        r = _renderer()
        text = r.render_hypothesis_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            finding_id="F-AAAA",
            finding_description="login timeout",
            severity="high",
            confidence=0.9,
        )
        self.assertIn("Hypothesis Investigator", text)
        self.assertIn("F-AAAA", text)
        self.assertIn("login timeout", text)
        self.assertIn("high", text)
        self.assertIn("0.9", text)
        self._assert_no_root_mutation(text)

    def test_synthesis_prompt(self) -> None:
        r = _renderer()
        text = r.render_synthesis_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            hypothesis_result_ids=["HR-1", "HR-2"],
        )
        self.assertIn("Synthesis Architect", text)
        self.assertIn("HR-1", text)
        self.assertIn("HR-2", text)
        self._assert_no_root_mutation(text)

    def test_work_planner_prompt(self) -> None:
        r = _renderer()
        text = r.render_work_planner_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            plan_type="implementation_set",
            target_ids=["T-1", "T-2"],
            target_types=["finding", "goal_gate"],
        )
        self.assertIn("Work Planner Architect", text)
        self.assertIn("implementation_set", text)
        self.assertIn("T-1", text)
        self.assertIn("T-2", text)
        self._assert_no_root_mutation(text)

    def test_proposal_explore_prompt(self) -> None:
        r = _renderer()
        text = r.render_proposal_explore_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
        )
        self.assertIn("Proposal Explore", text)
        self.assertIn(TEST_JOB_ID, text)
        self._assert_no_root_mutation(text)

    def test_proposal_architect_prompt(self) -> None:
        r = _renderer()
        text = r.render_proposal_architect_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
        )
        self.assertIn("Proposal Architect", text)
        self.assertIn(TEST_JOB_ID, text)
        self._assert_no_root_mutation(text)

    def test_proposal_finalize_prompt(self) -> None:
        r = _renderer()
        text = r.render_proposal_finalize_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
        )
        self.assertIn("Proposal Finalizer", text)
        self.assertIn(TEST_JOB_ID, text)
        self._assert_no_root_mutation(text)

    def test_implementation_prompt(self) -> None:
        r = _renderer()
        text = r.render_implementation_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            scope_description="fix login form",
            allowed_paths=["src/", "tests/"],
        )
        self.assertIn("Implementation Worker", text)
        self.assertIn("fix login form", text)
        self.assertIn("src/", text)
        self.assertIn("tests/", text)
        self._assert_no_root_mutation(text)

    def test_repair_prompt(self) -> None:
        r = _renderer()
        text = r.render_repair_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            target_job_id="J-TARGET",
            finding_id="F-FINDING",
            finding_description="broken test",
            repair_strategy="retry",
        )
        self.assertIn("Repair Worker", text)
        self.assertIn("J-TARGET", text)
        self.assertIn("F-FINDING", text)
        self.assertIn("broken test", text)
        self.assertIn("retry", text)
        self._assert_no_root_mutation(text)

    def test_verifier_prompt(self) -> None:
        r = _renderer()
        text = r.render_verifier_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            assignment_id="VA-AAAA",
            target_job_id="J-TARGET",
            target_gate_id="GG-AAAA",
            target_gate_revision=2,
            evidence_refs=["run://test/jobs/J001/report"],
        )
        self.assertIn("Verifier", text)
        self.assertIn("VA-AAAA", text)
        self.assertIn("J-TARGET", text)
        self.assertIn("GG-AAAA", text)
        self.assertIn("2", text)
        self.assertIn("run://test/jobs/J001/report", text)
        self._assert_no_root_mutation(text)

    def test_integration_verifier_prompt(self) -> None:
        r = _renderer()
        text = r.render_integration_verifier_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            target_job_ids=["J-1", "J-2"],
            integration_requirements=["build passes", "tests pass"],
        )
        self.assertIn("Integration Verifier", text)
        self.assertIn("J-1", text)
        self.assertIn("J-2", text)
        self.assertIn("build passes", text)
        self._assert_no_root_mutation(text)

    def test_implementation_review_prompt(self) -> None:
        r = _renderer()
        text = r.render_implementation_review_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            reviewed_job_id="J-REVIEWED",
            review_scope=["security", "performance"],
        )
        self.assertIn("Implementation Review Architect", text)
        self.assertIn("J-REVIEWED", text)
        self.assertIn("security", text)
        self.assertIn("performance", text)
        self._assert_no_root_mutation(text)

    def test_branch_init_prompt(self) -> None:
        r = _renderer()
        text = r.render_branch_init_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            branch_name="feature/fix-login",
        )
        self.assertIn("Branch Initializer", text)
        self.assertIn("feature/fix-login", text)
        self._assert_no_root_mutation(text)

    def test_openspec_finalization_prompt(self) -> None:
        r = _renderer()
        text = r.render_openspec_finalization_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            spec_files=["spec1.md", "spec2.md"],
        )
        self.assertIn("OpenSpec Finalizer", text)
        self.assertIn("spec1.md", text)
        self.assertIn("spec2.md", text)
        self._assert_no_root_mutation(text)

    def test_commit_prompt(self) -> None:
        r = _renderer()
        text = r.render_commit_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            commit_message="fix: login timeout",
            files_to_commit=["src/login.py", "tests/test_login.py"],
        )
        self.assertIn("Commit Worker", text)
        self.assertIn("fix: login timeout", text)
        self.assertIn("src/login.py", text)
        self._assert_no_root_mutation(text)

    def test_push_prompt(self) -> None:
        r = _renderer()
        text = r.render_push_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            remote="origin",
            branch="main",
        )
        self.assertIn("Push Worker", text)
        self.assertIn("origin", text)
        self.assertIn("main", text)
        self._assert_no_root_mutation(text)

    def test_remote_verification_prompt(self) -> None:
        r = _renderer()
        text = r.render_remote_verification_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            verification_target="deployment",
            verification_checks=["health_check", "smoke_test"],
        )
        self.assertIn("Remote Verifier", text)
        self.assertIn("deployment", text)
        self.assertIn("health_check", text)
        self.assertIn("smoke_test", text)
        self._assert_no_root_mutation(text)


class VerifierTargetContextTest(unittest.TestCase):
    """Task 4.3: Verifier target, accepted reports, result contract."""

    def test_render_verifier_target_context(self) -> None:
        r = _renderer()
        text = r.render_verifier_target_context(
            target_job_id="J-TARGET",
            target_gate_id="GG-AAAA",
            target_gate_revision=2,
            condition_id="COND-1",
            condition_status="pending",
        )
        self.assertIn("J-TARGET", text)
        self.assertIn("GG-AAAA", text)
        self.assertIn("2", text)
        self.assertIn("COND-1", text)
        self.assertIn("pending", text)

    def test_render_accepted_reports(self) -> None:
        r = _renderer()
        text = r.render_accepted_reports([
            {"ref": "run://test/jobs/J001/report", "content_sha256": "a" * 64},
            {"ref": "run://test/jobs/J002/report", "digest": "b" * 64},
        ])
        self.assertIn("run://test/jobs/J001/report", text)
        self.assertIn("a" * 64, text)
        self.assertIn("run://test/jobs/J002/report", text)
        self.assertIn("b" * 64, text)

    def test_render_result_contract(self) -> None:
        r = _renderer()
        text = r.render_result_contract(
            required_statuses=["passed"],
            required_evidence=["run://test/jobs/J001/report"],
        )
        self.assertIn("passed", text)
        self.assertIn("run://test/jobs/J001/report", text)


class DependencyIntegrityTest(unittest.TestCase):
    """Task 4.4: Rehash and validate dependency artifacts."""

    def test_rehash_adds_sha256_for_content(self) -> None:
        artifacts = [{"artifact_id": "A-1", "content": "hello"}]
        rehashed = PromptRenderer.rehash_dependency_artifacts(artifacts)
        self.assertEqual(len(rehashed), 1)
        self.assertIn("content_sha256", rehashed[0])
        self.assertEqual(len(rehashed[0]["content_sha256"]), 64)

    def test_rehash_preserves_existing_hash(self) -> None:
        orig_hash = "c" * 64
        artifacts = [{"artifact_id": "A-1", "content_sha256": orig_hash}]
        rehashed = PromptRenderer.rehash_dependency_artifacts(artifacts)
        self.assertEqual(rehashed[0]["content_sha256"], orig_hash)

    def test_rehash_does_not_mutate_input(self) -> None:
        artifacts = [{"artifact_id": "A-1", "content": "hello"}]
        original_hash = artifacts[0].get("content_sha256")
        PromptRenderer.rehash_dependency_artifacts(artifacts)
        self.assertIsNone(original_hash)

    def test_validate_dependency_integrity_passes(self) -> None:
        original = [{"artifact_id": "A-1", "content_sha256": "d" * 64}]
        rehashed = [{"artifact_id": "A-1", "content_sha256": "d" * 64}]
        valid, errors = PromptRenderer.validate_dependency_integrity(original, rehashed)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_rejects_changed_artifact(self) -> None:
        original = [{"artifact_id": "A-1", "content_sha256": "d" * 64}]
        rehashed = [{"artifact_id": "A-1", "content_sha256": "e" * 64}]
        valid, errors = PromptRenderer.validate_dependency_integrity(original, rehashed)
        self.assertFalse(valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("changed artifact", errors[0])

    def test_validate_rejects_missing_artifact(self) -> None:
        original = [
            {"artifact_id": "A-1", "content_sha256": "d" * 64},
            {"artifact_id": "A-2", "content_sha256": "e" * 64},
        ]
        rehashed = [{"artifact_id": "A-1", "content_sha256": "d" * 64}]
        valid, errors = PromptRenderer.validate_dependency_integrity(original, rehashed)
        self.assertFalse(valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing artifact", errors[0])


class ContinuationAndReplacementTest(unittest.TestCase):
    """Task 4.5: Continuation and replacement prompts."""

    def test_continuation_includes_answers(self) -> None:
        r = _renderer()
        text = r.render_continuation_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            answers=[{"question": "May I proceed?", "answer": "Yes"}],
            related_reports=[{"ref": "run://test/jobs/J001/report", "summary": "all good"}],
        )
        self.assertIn("May I proceed?", text)
        self.assertIn("Yes", text)
        self.assertIn("run://test/jobs/J001/report", text)
        self.assertIn("all good", text)

    def test_replacement_includes_all_context(self) -> None:
        r = _renderer()
        text = r.render_replacement_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            original_prompt_summary="Implement feature X",
            transport_evidence={"status": "timeout", "session": "sess-123"},
            checkpoint_ref="run://test/checkpoints/CP-1",
            workspace_evidence=[{"ref": "run://test/jobs/J001/report", "status": "stale"}],
            related_reports=[{"ref": "run://test/jobs/J002/report", "summary": "done"}],
            pending_input=[{"question": "Approve?", "context": "needs approval"}],
            recovery_findings=[{"strategy": "retry", "reason": "timeout"}],
        )
        self.assertIn("Implement feature X", text)
        self.assertIn("timeout", text)
        self.assertIn("sess-123", text)
        self.assertIn("CP-1", text)
        self.assertIn("stale", text)
        self.assertIn("done", text)
        self.assertIn("Approve?", text)
        self.assertIn("retry", text)

    def test_replacement_no_mutation_instructions(self) -> None:
        r = _renderer()
        text = r.render_replacement_prompt(
            job_id=TEST_JOB_ID,
            activation_id=TEST_ACTIVATION_ID,
            cycle_id=TEST_CYCLE_ID,
            graph_revision=TEST_GRAPH_REVISION,
            original_prompt_summary="do work",
            transport_evidence={},
            checkpoint_ref=None,
            workspace_evidence=[],
            related_reports=[],
            pending_input=None,
            recovery_findings=None,
        )
        for kw in ROOT_MUTATION_KEYWORDS:
            self.assertNotIn(kw, text, f"Replacement prompt must not expose: {kw}")


if __name__ == "__main__":
    unittest.main()
