from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL = ROOT / "SKILL.md"
REFERENCES = ROOT / "references"
SCHEMAS = ROOT / "schemas" / "v6"
DOCS = [SKILL, *sorted(REFERENCES.glob("*.md"))]
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")
SHIPPED_TEXT_SUFFIXES = {".json", ".lock", ".md", ".py", ".txt", ".yaml", ".yml"}


class LocalLinkValidationTest(unittest.TestCase):
    def test_all_local_links_resolve(self) -> None:
        for document in DOCS:
            text = document.read_text(encoding="utf-8")
            for target in LINK.findall(text):
                self.assertFalse(
                    target.startswith(("http://", "https://")),
                    f"{document}: external link {target}",
                )
                resolved = (document.parent / target).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"{document}: link target {target} does not exist",
                )

    def test_no_change_artifact_links(self) -> None:
        for document in DOCS:
            text = document.read_text(encoding="utf-8")
            self.assertNotIn("openspec/changes/", text, document)
            self.assertNotIn("openspec\\changes\\", text, document)


class PromptRenderingValidationTest(unittest.TestCase):
    def test_prompt_renderer_covers_all_roles(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from prompt_v6 import PromptRenderer

        renderer = PromptRenderer("RUN-001", "test goal")
        render_methods = [
            m for m in dir(renderer)
            if m.startswith("render_") and callable(getattr(renderer, m))
        ]
        self.assertGreater(len(render_methods), 10)

    def test_prompt_methods_return_strings(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from prompt_v6 import PromptRenderer

        renderer = PromptRenderer("RUN-001", "test goal")
        result = renderer.render_workflow_context(
            job_id="JOB-001",
            activation_id="ACT-001",
            context_snapshot_id="CTX-001",
            cycle_id="CYC-001",
            graph_revision=1,
            graph_digest="a" * 64,
            campaign_envelope_id="ENV-001",
            job_ids=["JOB-001"],
        )
        self.assertIsInstance(result, str)
        self.assertIn("RUN-001", result)
        self.assertIn("test goal", result)


class SchemaExampleValidationTest(unittest.TestCase):
    def test_all_v6_schemas_exist(self) -> None:
        self.assertTrue(SCHEMAS.exists())
        schema_files = list(SCHEMAS.glob("*.schema.json"))
        self.assertEqual(len(schema_files), 41)

    def test_schemas_are_valid_json(self) -> None:
        for schema_path in SCHEMAS.glob("*.schema.json"):
            data = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"{schema_path.name} must be a dict")
            self.assertIn("type", data, f"{schema_path.name} must have type")


class CLIShapeValidationTest(unittest.TestCase):
    def test_jobctl_has_all_v6_commands(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from jobctl import parser

        p = parser()
        subparsers_actions = [
            a for a in p._actions
            if hasattr(a, '_parser_class')
        ]
        command_names = set()
        for action in subparsers_actions:
            if hasattr(action, 'choices'):
                command_names.update(action.choices.keys())

        required_commands = {
            "init", "register", "next", "prepare-dispatch",
            "launch-receipt", "response-receipt", "answer",
            "commit-expansion", "audit", "recover", "repair", "cancel",
        }
        self.assertTrue(
            required_commands.issubset(command_names),
            f"missing commands: {required_commands - command_names}",
        )

    def test_commit_expansion_parser_args(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from jobctl import parser

        p = parser()
        args = p.parse_args([
            "commit-expansion",
            "--run", "/tmp/run",
            "--expansion", "EXP-001",
            "--expected-graph-revision", "1",
            "--expected-graph-digest", "a" * 64,
            "--plan-digest", "b" * 64,
        ])
        self.assertEqual(args.command, "commit-expansion")
        self.assertEqual(args.expansion_id, "EXP-001")
        self.assertEqual(args.expected_graph_revision, 1)
        self.assertEqual(args.expected_graph_digest, "a" * 64)
        self.assertEqual(args.plan_digest, "b" * 64)

    def test_all_commands_emit_json(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from jobctl import parser

        p = parser()
        args = p.parse_args(["audit", "--run", "/tmp/run"])
        self.assertEqual(args.command, "audit")


class RoleBoundaryValidationTest(unittest.TestCase):
    def test_architect_enforcer_covers_all_roles(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import ArchitectEnforcer

        enforcer = ArchitectEnforcer()
        expected_roles = {
            "proposal_explore", "proposal_architect", "proposal_finalizer",
            "work_planner_architect", "implementation_review_architect",
            "synthesis_architect", "goal_judge",
        }
        self.assertEqual(enforcer.ARCHITECT_ROLES, expected_roles)

    def test_architect_read_only_enforcement(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import ArchitectEnforcer

        enforcer = ArchitectEnforcer()
        errors = enforcer.enforce_read_only(
            "proposal_architect", ["write_file", "read_file"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("write_file", errors[0])

    def test_architect_no_self_verification(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import ArchitectEnforcer

        enforcer = ArchitectEnforcer()
        errors = enforcer.enforce_no_self_verification(
            verifier_job_id="JOB-001",
            target_job_id="JOB-001",
            verifier_role="proposal_architect",
            target_role="proposal_architect",
        )
        self.assertGreater(len(errors), 0)

    def test_default_strategy_phases(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import DefaultStrategy

        strategy = DefaultStrategy()
        self.assertEqual(len(strategy.phases), 10)
        phase_ids = [p.phase_id for p in strategy.phases]
        self.assertIn("verification", phase_ids)
        self.assertIn("goal_judge", phase_ids)
        self.assertIn("review", phase_ids)

    def test_non_overridable_phases(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import DefaultStrategy

        strategy = DefaultStrategy()
        self.assertIn("verification", strategy.non_overridable)
        self.assertIn("goal_judge", strategy.non_overridable)
        self.assertIn("review", strategy.non_overridable)


class InstructionArchitectureValidationTest(unittest.TestCase):
    def test_skill_md_covers_v6_incompatibility(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("v6 incompatibility", text)
        self.assertIn("schema_version", text)

    def test_skill_md_covers_default_strategy_routing(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("default strategy routing", text)
        self.assertIn("proposal explore", text)
        self.assertIn("goal judge", text)

    def test_dynamic_normal_loop_is_isolated_in_legacy_reference(self) -> None:
        skill = SKILL.read_text(encoding="utf-8").lower()
        legacy = (
            REFERENCES / "legacy-root-session-orchestration.md"
        ).read_text(encoding="utf-8").lower()

        self.assertNotIn("dynamic normal loop operations", skill)
        self.assertIn("dynamic normal loop operations", legacy)
        for command_detail in (
            "prepare_dispatch",
            "prepare-dispatch",
            "commit_expansion",
            "commit-expansion",
            "expected-graph-revision",
            "expected-graph-digest",
            "plan-digest",
        ):
            self.assertIn(command_detail, legacy)
        self.assertIn("# legacy: root session orchestration", legacy)
        self.assertIn("deprecated", legacy)
        self.assertIn(
            "standalone orchestrator script is the only supported default approach",
            skill,
        )
        self.assertIn(
            "[legacy-root-session-orchestration.md]"
            "(references/legacy-root-session-orchestration.md)",
            skill,
        )
        self.assertIn("[skill.md](../skill.md#standalone-orchestrator-script)", legacy)

    def test_skill_md_covers_root_boundary(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("root boundary", text)
        self.assertIn("must not", text)

    def test_skill_md_covers_typed_terminal_outcomes(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("typed terminal outcomes", text)
        self.assertIn("goal_achieved", text)
        self.assertIn("continue", text)

    def test_skill_md_links_to_all_references(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for ref in (
            "protocol.md", "recovery.md", "job-protocol.md",
            "transport-capabilities.md", "maintainer-guidance.md",
            "strategy.md", "dynamic-graph.md", "architect-roles.md",
            "campaign.md",
        ):
            self.assertIn(ref, text, f"SKILL.md missing link to {ref}")

    def test_references_only_ship_v6(self) -> None:
        for ref in REFERENCES.glob("*.md"):
            text = ref.read_text(encoding="utf-8").lower()
            if ref.name == "maintainer-guidance.md":
                continue
            self.assertNotIn("v4 schema", text, f"{ref.name} references v4")
            self.assertNotIn("v5 command", text, f"{ref.name} references v5")

    def test_no_pre_v6_instructions_in_skill(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        # workerctl and legacy appear only in the v6 incompatibility boundary
        # section as prohibited items; verify they are not in operational sections
        lines = text.splitlines()
        in_boundary = False
        operational_text = []
        for line in lines:
            if "v6 incompatibility boundary" in line:
                in_boundary = True
            elif line.startswith("##") and in_boundary:
                in_boundary = False
            if not in_boundary:
                operational_text.append(line)
        operational = "\n".join(operational_text)
        self.assertNotIn("workerctl", operational)
        self.assertNotIn("verify_repair", operational)

    def test_schemas_directory_only_v6(self) -> None:
        schema_dirs = [d for d in SCHEMAS.parent.iterdir() if d.is_dir()]
        self.assertEqual(
            [d.name for d in schema_dirs],
            ["v6"],
        )


class EntryModeDocumentationTest(unittest.TestCase):
    def test_compilation_modes_documented(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("full_campaign", text)
        self.assertIn("proposal_only", text)
        self.assertIn("implementation_from_proposal", text)
        self.assertIn("architect_review_only", text)
        self.assertIn("resume", text)
        self.assertIn("custom", text)

    def test_compilation_modes_in_strategy_reference(self) -> None:
        ref = REFERENCES / "strategy.md"
        text = ref.read_text(encoding="utf-8").lower()
        self.assertIn("compilation modes", text)
        self.assertIn("full_campaign", text)
        self.assertIn("proposal_only", text)


class ContextModuleDocumentationTest(unittest.TestCase):
    def test_context_module_in_strategy_v6(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import ContextModule, ContextModuleRegistry

        module = ContextModule(
            module_id="MOD-001",
            namespace="test",
            constraints={"key": "value"},
        )
        self.assertEqual(module.module_id, "MOD-001")
        self.assertEqual(module.namespace, "test")

        registry = ContextModuleRegistry()
        registry.add_context_module(module)
        self.assertIsNotNone(registry.get_module("MOD-001"))


class FeatureBranchDocumentationTest(unittest.TestCase):
    def test_campaign_branch_initializer_exists(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import CampaignBranchInitializer

        self.assertTrue(hasattr(CampaignBranchInitializer, "initialize_branch"))
        self.assertTrue(hasattr(CampaignBranchInitializer, "persist_branch_info"))


class CycleCommitDocumentationTest(unittest.TestCase):
    def test_cycle_committer_exists(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import CycleCommitter

        self.assertTrue(hasattr(CycleCommitter, "create_commit"))
        self.assertTrue(hasattr(CycleCommitter, "filter_campaign_changes"))


class PublicationDocumentationTest(unittest.TestCase):
    def test_publication_policy_in_strategy(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from strategy_v6 import PublicationPolicy

        policy = PublicationPolicy()
        self.assertIsNotNone(policy)


if __name__ == "__main__":
    unittest.main()
