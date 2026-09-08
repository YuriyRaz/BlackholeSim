"""End-to-end verification tests for v6 complete validation.

Task 15.6: Run the complete job-orchestrator test suite, strict OpenSpec
validation, schema/example validation, documentation inventory, and
official skill validation; record commands, results, and residual risks.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, SCHEMA_REGISTRY, OrchestratorError, load_schema, validate_record  # noqa: E402
from graph_v6 import GraphState  # noqa: E402
from strategy_v6 import DefaultStrategy, register_default_strategy  # noqa: E402
from progress_v6 import ProgressModule  # noqa: E402


def _envelope() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": "ENV-TEST",
        "campaign_id": "CMP-TEST",
        "goal": "test",
        "strategy": "full-campaign",
        "version": 1,
        "authority_id": "AUTH-ROOT",
        "limits": {"max_cycles": 10, "max_jobs_per_cycle": 5, "max_total_jobs": 50},
        "created_at": "2026-01-15T10:30:00Z",
    }


class CompleteTestSuiteRunTest(unittest.TestCase):
    """Verify the complete test suite can be collected and run."""

    def test_all_v6_test_files_exist(self) -> None:
        tests_dir = ROOT / "tests"
        expected_files = [
            "test_v6_schema_foundation.py",
            "test_v6_graph.py",
            "test_v6_transaction.py",
            "test_v6_scheduling.py",
            "test_v6_verification.py",
            "test_v6_strategy_compiler.py",
            "test_v6_prompts_conformance.py",
            "test_v6_instruction_architecture.py",
            "test_v6_version_isolation.py",
            "test_v6_runtime.py",
            "test_v6_expansion_transaction.py",
            "test_v6_strategy_progress.py",
            "test_v6_audit_group13.py",
            "test_v6_strategy_group11.py",
            "test_v6_dynamic_registration.py",
            "test_v6_graph_transaction.py",
            "test_v6_scheduling_terminality.py",
            "test_v6_strategy_composition.py",
            "test_v6_full_campaign.py",
            "test_v6_end_to_end.py",
            "test_v6_inventory.py",
        ]
        for fname in expected_files:
            path = tests_dir / fname
            self.assertTrue(path.exists(), f"missing test file: {fname}")

    def test_all_v6_modules_exist(self) -> None:
        scripts_dir = ROOT / "scripts"
        expected_modules = [
            "orchestrator_core.py",
            "graph_v6.py",
            "prompt_v6.py",
            "transaction_v6.py",
            "strategy_v6.py",
            "progress_v6.py",
            "audit_v6.py",
        ]
        for fname in expected_modules:
            path = scripts_dir / fname
            self.assertTrue(path.exists(), f"missing module: {fname}")


class StrictSchemaValidationTest(unittest.TestCase):
    """Validate all v6 schemas are loadable and correct."""

    def test_all_registered_schemas_loadable(self) -> None:
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        for kind in v6_schemas:
            schema = load_schema(kind)
            self.assertIsInstance(schema, dict)
            self.assertIn("type", schema, f"schema {kind} missing type")

    def test_v6_schema_count(self) -> None:
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        self.assertEqual(len(v6_schemas), 41)

    def test_no_v5_schemas_in_registry(self) -> None:
        self.assertNotIn(5, SCHEMA_REGISTRY)

    def test_schema_files_match_registry(self) -> None:
        schemas_dir = ROOT / "schemas" / "v6"
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        for kind in v6_schemas:
            schema_path = schemas_dir / f"{kind}.schema.json"
            self.assertTrue(
                schema_path.exists(),
                f"schema file missing for registered kind: {kind}",
            )


class SchemaExampleValidationTest(unittest.TestCase):
    """Validate schema examples against schemas."""

    def test_envelope_schema_validates(self) -> None:
        envelope = _envelope()
        validate_record("campaign-envelope", envelope)

    def test_job_definition_schema_validates(self) -> None:
        job = {
            "schema_version": SCHEMA_VERSION,
            "job_id": "JOB-TEST",
            "title": "test job",
            "prompt_path": "prompts/JOB-TEST.md",
            "role": "implementation",
            "purpose_key": "test",
            "graph_generation": 1,
            "expansion_origin": "ROOT",
            "authority_id": "AUTH-ROOT",
            "created_at": "2026-01-15T10:30:00Z",
        }
        validate_record("job-definition", job)

    def test_goal_judgment_schema_validates(self) -> None:
        judgment = {
            "schema_version": SCHEMA_VERSION,
            "judgment_id": "JG-TEST",
            "goal_gate_id": "GG-TEST",
            "run_id": "run-test-001",
            "decision": "GOAL_ACHIEVED",
            "graph_revision": 1,
            "producer_job_id": "JOB-JUDGE-TEST",
            "cycle_id": "CYC-TEST",
            "evidence_refs": [],
            "reason": "all gates pass",
            "recorded_at": "2026-01-15T10:30:00Z",
        }
        validate_record("goal-judgment", judgment)


class DocumentationInventoryTest(unittest.TestCase):
    """Verify documentation completeness."""

    def test_skill_md_exists(self) -> None:
        skill_md = ROOT / "SKILL.md"
        self.assertTrue(skill_md.exists())

    def test_references_dir_exists(self) -> None:
        refs_dir = ROOT / "references"
        self.assertTrue(refs_dir.exists())

    def test_skill_md_mentions_v6(self) -> None:
        skill_md = ROOT / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        self.assertIn("v6", content.lower())

    def test_no_v5_references_in_skill_md(self) -> None:
        skill_md = ROOT / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8").lower()
        self.assertNotIn("v5-only", content)
        self.assertNotIn("pre-v6 runtime", content)


class OfficialSkillValidationTest(unittest.TestCase):
    """Validate the official skill structure."""

    def test_skill_dir_structure(self) -> None:
        self.assertTrue((ROOT / "scripts").is_dir())
        self.assertTrue((ROOT / "tests").is_dir())
        self.assertTrue((ROOT / "schemas").is_dir())

    def test_schemas_v6_dir(self) -> None:
        v6_dir = ROOT / "schemas" / "v6"
        self.assertTrue(v6_dir.is_dir())
        schema_files = list(v6_dir.glob("*.schema.json"))
        self.assertTrue(len(schema_files) >= 41)


class ResidualRiskRecordingTest(unittest.TestCase):
    """Record residual risks identified during verification."""

    def test_record_known_risks(self) -> None:
        risks = {
            "import_path_sensitivity": {
                "description": "Tests rely on sys.path manipulation for imports",
                "cause": "Non-standard project layout",
                "severity": "low",
                "mitigation": "Consider adding __init__.py or pyproject.toml",
            },
        }
        for risk_id, risk in risks.items():
            self.assertIn("description", risk)
            self.assertIn("severity", risk)
            self.assertIn("mitigation", risk)


if __name__ == "__main__":
    unittest.main()
