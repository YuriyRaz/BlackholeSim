"""Real jobctl initialization tests for canonical v6 campaign strategies."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from orchestrator_core import OrchestratorError, canonical_bytes  # noqa: E402
from strategy_v6 import (  # noqa: E402
    CompilationMode,
    ContextModule,
    StrategyCompiler,
    build_default_strategy_registry,
)


class CampaignInitializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = self.root / "request.md"
        self.request.write_text("campaign request\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *arguments: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "jobctl.py"), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def initialize(
        self,
        mode: str,
        run_id: str,
        *extra: str,
        config: dict | None = None,
        expected: int = 0,
    ) -> dict:
        arguments = [
            "init",
            "--request-file", str(self.request),
            "--goal", "deliver a durable feature",
            "--run-id", run_id,
            "--state-root", str(self.root),
            "--workspace", str(ROOT),
            "--mode", mode,
            "--test-harness",
            *extra,
        ]
        if config is not None:
            arguments.extend(("--strategy-config", str(self.write_json(f"{run_id}.json", config))))
        return self.cli(*arguments, expected=expected)

    def load_campaign(self, result: dict) -> tuple[dict, dict, dict]:
        run_root = Path(result["run_root"])
        strategy = json.loads((run_root / "strategy.json").read_text(encoding="utf-8"))
        envelope = json.loads((run_root / "campaign-envelope.json").read_text(encoding="utf-8"))
        graph = json.loads((run_root / "graph" / "graph.json").read_text(encoding="utf-8"))
        return strategy, envelope, graph

    def test_full_campaign_persists_and_schedules_complete_default_graph(self) -> None:
        result = self.initialize("full_campaign", "full")
        strategy, envelope, graph = self.load_campaign(result)
        expected = [
            "branch_init", "proposal_explore", "proposal_architect", "proposal_finalize",
            "proposal_review", "implementation_planning", "implementation",
            "deterministic_checks", "verification", "implementation_review",
            "openspec_sync", "openspec_archive", "cycle_commit", "cycle_push",
            "remote_verification", "goal_judge",
        ]
        self.assertEqual(strategy["phase_sequence"], expected)
        self.assertEqual(envelope["phase_sequence"], expected)
        self.assertTrue(envelope["branch_policy"]["required"])
        self.assertEqual(graph["current_goal_judge_id"], result["job_ids"][-1])
        operation = self.cli("next", "--run", result["run_root"])
        self.assertEqual(operation["operation"], "prepare_dispatch")
        self.assertEqual(graph["jobs"][operation["job_id"]]["role"], "branch_initializer")

    def test_all_partial_and_custom_modes_have_typed_boundaries(self) -> None:
        cases = (
            ("proposal_only", "proposal", (), "reviewed_proposal", True),
            (
                "implementation_from_proposal", "implementation",
                ("--entry-artifact", "reviewed_proposal=openspec/change"),
                "goal_judgment", True,
            ),
            (
                "architect_review_only", "review",
                ("--entry-artifact", "implementation_evidence=report", "--review-target", "HEAD"),
                "implementation_review", False,
            ),
            ("custom", "custom", (), "goal_judgment", True),
        )
        for mode, run_id, extra, exit_name, mutating in cases:
            with self.subTest(mode=mode):
                result = self.initialize(mode, run_id, *extra)
                strategy, envelope, graph = self.load_campaign(result)
                self.assertIn(exit_name, strategy["exit_contract"])
                self.assertEqual(envelope["mutating"], mutating)
                self.assertGreater(len(graph["jobs"]), 1)
        implementation = json.loads(
            (self.root / "implementation" / "strategy.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("proposal_explore", implementation["phase_sequence"])
        planning_id = next(
            job_id for job_id, job in json.loads(
                (self.root / "implementation" / "graph" / "graph.json").read_text(encoding="utf-8")
            )["jobs"].items()
            if job["role"] == "work_planner_architect"
        )
        planning_prompt = (self.root / "implementation" / "jobs" / planning_id / "prompt.md").read_text()
        self.assertIn("Nested OpenSpec promotion remains allowed", planning_prompt)

    def test_partial_modes_reject_missing_entry_contracts(self) -> None:
        result = self.initialize("implementation_from_proposal", "missing-proposal", expected=2)
        self.assertIn("reviewed_proposal", result["error"])
        result = self.initialize(
            "architect_review_only", "missing-review",
            "--entry-artifact", "implementation_evidence=report", expected=2,
        )
        self.assertIn("review_target", result["error"])

    def test_resume_audits_and_reuses_frozen_strategy_without_writes(self) -> None:
        initialized = self.initialize("proposal_only", "resume-source")
        run_root = Path(initialized["run_root"])
        strategy_path = run_root / "strategy.json"
        graph_path = run_root / "graph" / "graph.json"
        before = (strategy_path.read_bytes(), graph_path.read_bytes())
        resumed = self.cli("init", "--mode", "resume", "--resume-run", str(run_root))
        self.assertEqual(resumed["operation"], "resume")
        self.assertEqual(resumed["strategy_mode"], "proposal_only")
        self.assertEqual(resumed["compilation_digest"], initialized["compilation_digest"])
        self.assertEqual(before, (strategy_path.read_bytes(), graph_path.read_bytes()))

    def test_composition_operations_apply_and_safety_cannot_be_weakened(self) -> None:
        replacement = {
            "phase_id": "proposal_explore_v2",
            "role": "proposal_explore",
            "inputs": ["goal"],
            "outputs": ["exploration_report"],
            "prompt": "Explore with an explicit replacement.",
            "read_only": True,
        }
        security = {
            "phase_id": "security_review",
            "role": "verifier",
            "inputs": ["check_results"],
            "outputs": ["security_report"],
            "prompt": "Perform an independent security review.",
            "read_only": True,
        }
        removable = {
            "phase_id": "temporary_observation",
            "role": "verifier",
            "inputs": ["check_results"],
            "outputs": [],
            "prompt": "Temporary observation that is explicitly disabled.",
            "read_only": True,
        }
        config = {
            "operations": [
                {"operation": "replace", "target_phase": "proposal_explore", "phase": replacement},
                {"operation": "extend", "target_phase": "deterministic_checks", "phase": security},
                {"operation": "extend", "target_phase": "deterministic_checks", "phase": removable},
                {"operation": "disable", "target_phase": "temporary_observation"},
                {"operation": "configure", "target_phase": "implementation", "config": {"max_retries": 2}},
            ],
        }
        result = self.initialize("full_campaign", "composed", config=config)
        strategy, _, _ = self.load_campaign(result)
        self.assertIn("proposal_explore_v2", strategy["phase_sequence"])
        self.assertIn("security_review", strategy["phase_sequence"])
        self.assertNotIn("temporary_observation", strategy["phase_sequence"])
        self.assertEqual(strategy["phase_configurations"]["implementation"]["max_retries"], 2)
        rejected = self.initialize(
            "full_campaign", "unsafe",
            config={"operations": [{"operation": "disable", "target_phase": "verification"}]},
            expected=2,
        )
        self.assertIn("non-overridable safety phase", rejected["error"])

    def test_composition_ambiguity_asks_one_focused_question(self) -> None:
        phase = {
            "phase_id": "proposal_explore_v2", "role": "proposal_explore",
            "inputs": ["goal"], "outputs": ["exploration_report"], "prompt": "replacement",
        }
        result = self.initialize(
            "full_campaign", "ambiguous",
            config={"operations": [
                {"operation": "replace", "target_phase": "proposal_explore", "phase": phase},
                {"operation": "disable", "target_phase": "proposal_explore"},
            ]},
            expected=2,
        )
        self.assertIn("requires one user decision", result["error"])
        self.assertIn("Which operation should apply?", result["error"])

    def test_context_modules_are_frozen_rendered_and_authority_free(self) -> None:
        module = {
            "module_id": "security-v1",
            "namespace": "security",
            "version": 3,
            "constraints": {"minimum_tls": "1.3"},
            "applicable_roles": ["implementation_worker", "verifier"],
            "evidence_requirements": ["threat model"],
            "goal_gates": ["security approved"],
        }
        result = self.initialize("full_campaign", "context", config={"context_modules": [module]})
        strategy, _, graph = self.load_campaign(result)
        snapshot = strategy["context_snapshots"][0]
        self.assertEqual(snapshot["version"], 3)
        self.assertEqual(len(snapshot["digest"]), 64)
        implementation_id = next(
            job_id for job_id, job in graph["jobs"].items() if job["role"] == "implementation_worker"
        )
        prompt = (Path(result["run_root"]) / "jobs" / implementation_id / "prompt.md").read_text()
        self.assertIn("security-v1", prompt)
        self.assertIn("minimum_tls", prompt)
        authority = graph["authorities"][graph["jobs"][implementation_id]["authority_id"]]
        self.assertNotIn("expansion", authority["scope"])

        conflict = dict(module, module_id="security-v2", constraints={"minimum_tls": "1.2"})
        rejected = self.initialize(
            "full_campaign", "context-conflict",
            config={"context_modules": [module, conflict]}, expected=2,
        )
        self.assertIn("requires one user decision", rejected["error"])
        authority_module = dict(module, module_id="authority", constraints={"authority": "admin"})
        rejected = self.initialize(
            "full_campaign", "context-authority",
            config={"context_modules": [authority_module]}, expected=2,
        )
        self.assertIn("cannot grant authority", rejected["error"])
        nested_authority = dict(
            module,
            module_id="nested-authority",
            constraints={"policy": {"permissions": ["admin"]}},
        )
        rejected = self.initialize(
            "full_campaign", "nested-context-authority",
            config={"context_modules": [nested_authority]}, expected=2,
        )
        self.assertIn("cannot grant authority", rejected["error"])

    def test_role_jobs_have_fresh_ids_and_architects_are_read_only(self) -> None:
        result = self.initialize("full_campaign", "roles")
        _, _, graph = self.load_campaign(result)
        job_ids = list(graph["jobs"])
        authority_ids = [job["authority_id"] for job in graph["jobs"].values()]
        self.assertEqual(len(job_ids), len(set(job_ids)))
        self.assertEqual(len(authority_ids), len(set(authority_ids)))
        for job_id, job in graph["jobs"].items():
            if "architect" not in job["role"]:
                continue
            authority = graph["authorities"][job["authority_id"]]
            self.assertEqual(authority["scope"]["side_effects"], ["none"])
            prompt = (Path(result["run_root"]) / "jobs" / job_id / "prompt.md").read_text()
            self.assertIn("Read-only Architect boundary", prompt)


class CanonicalCompilerDeterminismTest(unittest.TestCase):
    def test_identical_resolved_inputs_emit_identical_complete_outputs(self) -> None:
        context = ContextModule(
            module_id="physics-v1",
            namespace="physics",
            version=2,
            constraints={"precision": "double"},
            applicable_roles=("implementation_worker", "verifier"),
        )
        compiler = StrategyCompiler(build_default_strategy_registry())
        first = compiler.compile_mode(
            CompilationMode.FULL_CAMPAIGN,
            "default_adaptive", 1, "goal", "run-1", context_modules=(context,),
        )
        second = compiler.compile_mode(
            CompilationMode.FULL_CAMPAIGN,
            "default_adaptive", 1, "goal", "run-1", context_modules=(context,),
        )

        def payload(result) -> bytes:
            return canonical_bytes({
                "envelope": result.envelope.to_dict(),
                "jobs": result.graph.initial_jobs,
                "edges": result.graph.initial_edges,
                "graph_digest": result.graph.graph_digest,
                "prompts": [vars(prompt) for prompt in result.prompts],
                "compilation_digest": result.compilation_digest,
            })

        self.assertEqual(payload(first), payload(second))

    def test_resume_compilation_is_sidelined(self) -> None:
        compiler = StrategyCompiler(build_default_strategy_registry())
        with self.assertRaisesRegex(OrchestratorError, "persisted frozen campaign"):
            compiler.compile_resume("default_adaptive", 1, "goal", "run-1")


if __name__ == "__main__":
    unittest.main()
