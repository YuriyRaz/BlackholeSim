"""Tests for Group 11: Campaign Branch, Finalization, and Publication."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError
from strategy_v6 import (
    BranchInitWorker,
    CampaignBranchInitializer,
    CampaignStrategyOrchestrator,
    CycleCommitter,
    CycleFinalizer,
    CyclePusher,
    PostCommitGoalJudge,
    RemoteVerifier,
    stable_id,
    utc_now,
)


class CampaignBranchInitializerTest(unittest.TestCase):
    """Tests for CampaignBranchInitializer (Task 11.1)."""

    def test_generate_cycle_id_format(self) -> None:
        init = CampaignBranchInitializer(Path("."))
        cycle_id = init.generate_cycle_id("test-campaign")
        self.assertTrue(cycle_id.startswith("CYC-"))
        self.assertGreater(len(cycle_id), 4)

    def test_initialize_branch_returns_required_fields(self) -> None:
        init = CampaignBranchInitializer(Path("."))
        result = init.initialize_branch("campaign-123", "default_adaptive")
        self.assertIn("branch_name", result)
        self.assertIn("baseline_commit", result)
        self.assertIn("cycle_id", result)
        self.assertIn("campaign_id", result)
        self.assertEqual(result["branch_name"], "campaign/campaign-123")
        self.assertEqual(result["campaign_id"], "campaign-123")

    def test_persist_branch_info_updates_envelope(self) -> None:
        init = CampaignBranchInitializer(Path("."))
        envelope = {"schema_version": SCHEMA_VERSION, "envelope_id": "E-123"}
        branch_info = {
            "branch_name": "campaign/test",
            "baseline_commit": "abc123",
            "cycle_id": "CYC-test",
        }
        updated = init.persist_branch_info(envelope, branch_info)
        self.assertIn("branch", updated)
        self.assertEqual(updated["branch"]["branch_name"], "campaign/test")

    def test_persist_branch_info_rejects_non_v6_envelope(self) -> None:
        init = CampaignBranchInitializer(Path("."))
        envelope = {"schema_version": 5}
        branch_info = {"branch_name": "test", "baseline_commit": "abc", "cycle_id": "CYC"}
        with self.assertRaises(OrchestratorError):
            init.persist_branch_info(envelope, branch_info)


class BranchInitWorkerTest(unittest.TestCase):
    """Tests for BranchInitWorker (Task 11.2)."""

    def test_execute_branch_init_returns_status(self) -> None:
        worker = BranchInitWorker(Path("."))
        envelope = {"schema_version": SCHEMA_VERSION, "envelope_id": "E-123"}
        result = worker.execute_branch_init("test-campaign", "default", envelope)
        self.assertIn("status", result)
        self.assertIn("recovery_state", result)
        self.assertIn("baseline_report", result)

    def test_report_baseline_commit_format(self) -> None:
        worker = BranchInitWorker(Path("."))
        branch_info = {
            "campaign_id": "test",
            "branch_name": "campaign/test",
            "baseline_commit": "abc123",
            "cycle_id": "CYC-test",
        }
        report = worker.report_baseline_commit(branch_info)
        self.assertEqual(report["report_type"], "baseline_commit")
        self.assertEqual(report["campaign_id"], "test")


class CycleFinalizerTest(unittest.TestCase):
    """Tests for CycleFinalizer (Task 11.3)."""

    def test_resolve_openspec_stores(self) -> None:
        finalizer = CycleFinalizer(Path("."))
        result = finalizer.resolve_openspec_stores("CYC-123", "test")
        self.assertIn("stores", result)
        self.assertEqual(result["cycle_id"], "CYC-123")

    def test_sync_required_specs(self) -> None:
        finalizer = CycleFinalizer(Path("."))
        result = finalizer.sync_required_specs("CYC-123", ["spec1", "spec2"])
        self.assertEqual(len(result["spec_results"]), 2)
        self.assertIn("all_synced", result)

    def test_archive_completed_changes(self) -> None:
        finalizer = CycleFinalizer(Path("."))
        result = finalizer.archive_completed_changes("CYC-123", ["change-1"])
        self.assertIn("archive_results", result)
        self.assertEqual(len(result["archive_results"]), 1)

    def test_verify_final_artifacts(self) -> None:
        finalizer = CycleFinalizer(Path("."))
        result = finalizer.verify_final_artifacts("CYC-123", ["file1.txt"])
        self.assertIn("verification_results", result)
        self.assertIn("all_present", result)


class CycleCommitterTest(unittest.TestCase):
    """Tests for CycleCommitter (Task 11.4)."""

    def test_validate_commit_contents_empty(self) -> None:
        committer = CycleCommitter(Path("."))
        result = committer.validate_commit_contents([])
        self.assertFalse(result["valid"])
        self.assertIn("no campaign-owned files", result["reason"])

    def test_validate_commit_contents_valid(self) -> None:
        committer = CycleCommitter(Path("."))
        result = committer.validate_commit_contents([
            "openspec/changes/test.md",
            "docs/readme.md",
        ])
        self.assertTrue(result["valid"])

    def test_validate_commit_contents_invalid(self) -> None:
        committer = CycleCommitter(Path("."))
        result = committer.validate_commit_contents(["src/main.py"])
        self.assertFalse(result["valid"])
        self.assertIn("not campaign-owned", result["reason"])

    def test_filter_campaign_changes_returns_list(self) -> None:
        committer = CycleCommitter(Path("."))
        result = committer.filter_campaign_changes()
        self.assertIsInstance(result, list)


class CyclePusherTest(unittest.TestCase):
    """Tests for CyclePusher (Task 11.5)."""

    def test_idempotency_check_format(self) -> None:
        pusher = CyclePusher(Path("."))
        result = pusher.idempotency_check("campaign/test", "CYC-123", "abc123")
        self.assertIn("already_pushed", result)
        self.assertIn("branch_name", result)
        self.assertIn("cycle_id", result)

    def test_observable_remote_ref_recovery_format(self) -> None:
        pusher = CyclePusher(Path("."))
        result = pusher.observable_remote_ref_recovery("campaign/test", "abc123")
        self.assertIn("recoverable", result)


class RemoteVerifierTest(unittest.TestCase):
    """Tests for RemoteVerifier (Task 11.6)."""

    def test_default_publication_disabled(self) -> None:
        verifier = RemoteVerifier(Path("."))
        policy = verifier.default_publication_disabled()
        self.assertFalse(policy["pr_creation"])
        self.assertFalse(policy["mainline_merge"])
        self.assertFalse(policy["release"])
        self.assertFalse(policy["deploy"])

    def test_require_explicit_authority_none(self) -> None:
        verifier = RemoteVerifier(Path("."))
        result = verifier.require_explicit_authority(["pr_creation"], "none")
        self.assertFalse(result["authorized"])

    def test_require_explicit_authority_no_effects(self) -> None:
        verifier = RemoteVerifier(Path("."))
        result = verifier.require_explicit_authority([], "none")
        self.assertTrue(result["authorized"])

    def test_require_explicit_authority_valid(self) -> None:
        verifier = RemoteVerifier(Path("."))
        result = verifier.require_explicit_authority(["pr_creation"], "deploy")
        self.assertTrue(result["authorized"])


class PostCommitGoalJudgeTest(unittest.TestCase):
    """Tests for PostCommitGoalJudge (Task 11.7).."""

    def test_schedule_goal_judge_after_commit_not_verified(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.schedule_goal_judge_after_commit(
            "campaign", "CYC-123", "abc", False
        )
        self.assertFalse(result["scheduled"])
        self.assertIn("remote verification not complete", result["reason"])

    def test_schedule_goal_judge_after_commit_verified(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.schedule_goal_judge_after_commit(
            "campaign", "CYC-123", "abc", True
        )
        self.assertTrue(result["scheduled"])
        self.assertIn("judgment_id", result)

    def test_handle_continue(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.handle_continue(
            {"decision": "CONTINUE", "judgment_id": "J-123"},
            "campaign",
            1,
        )
        self.assertEqual(result["action"], "new_cycle")
        self.assertEqual(result["previous_cycle"], 1)

    def test_handle_continue_wrong_decision(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.handle_continue(
            {"decision": "GOAL_ACHIEVED"},
            "campaign",
            1,
        )
        self.assertEqual(result["action"], "none")

    def test_handle_goal_achieved(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.handle_goal_achieved(
            {"decision": "GOAL_ACHIEVED", "judgment_id": "J-123"},
            "campaign",
        )
        self.assertEqual(result["action"], "seal_campaign")
        self.assertFalse(result["publication_policy"]["pr_creation"])

    def test_handle_goal_achieved_wrong_decision(self) -> None:
        judge = PostCommitGoalJudge(Path("."))
        result = judge.handle_goal_achieved(
            {"decision": "CONTINUE"},
            "campaign",
        )
        self.assertEqual(result["action"], "none")


class CampaignStrategyOrchestratorTest(unittest.TestCase):
    """Tests for CampaignStrategyOrchestrator (Group 11 composite)."""

    def test_run_cycle_completes(self) -> None:
        orch = CampaignStrategyOrchestrator(Path("."))
        envelope = {"schema_version": SCHEMA_VERSION, "envelope_id": "E-123"}
        result = orch.run_cycle("test-campaign", envelope, 1)
        self.assertIn("status", result)
        self.assertIn("cycle_id", result)
        self.assertIn("steps", result)


if __name__ == "__main__":
    unittest.main()
