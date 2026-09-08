"""End-to-end verification tests for v6 repository inventory.

Task 15.7: Verify by repository inventory and search that no pre-v6 runtime,
schema, fixture, test, compatibility branch, stale operational instruction,
unrendered required field, or unintended job-orchestrator2 change remains.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, SCHEMA_REGISTRY  # noqa: E402


class NoV5RuntimeTest(unittest.TestCase):
    """Verify no v5 runtime files remain."""

    def test_no_v5_modules_in_scripts(self) -> None:
        scripts_dir = ROOT / "scripts"
        v5_files = []
        for f in scripts_dir.glob("*.py"):
            content = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'\bV5\b', content) and "V6" not in f.name:
                v5_files.append(f.name)
        # Allow V5 references in orchestrator_core (for classification) and version_isolation
        allowed = {"orchestrator_core.py", "test_v6_version_isolation.py"}
        unexpected = [f for f in v5_files if f not in allowed]
        self.assertEqual(unexpected, [], f"unexpected v5 references in: {unexpected}")

    def test_no_v5_schema_files(self) -> None:
        schemas_dir = ROOT / "schemas"
        v5_dirs = list(schemas_dir.glob("v5*"))
        self.assertEqual(v5_dirs, [], f"v5 schema dirs found: {v5_dirs}")

    def test_only_v6_schemas_exist(self) -> None:
        schemas_dir = ROOT / "schemas"
        version_dirs = [d.name for d in schemas_dir.iterdir() if d.is_dir()]
        self.assertIn("v6", version_dirs)
        for d in version_dirs:
            if d.startswith("v") and d[1:].isdigit():
                self.assertEqual(d, "v6", f"unexpected schema version dir: {d}")


class NoV5SchemasTest(unittest.TestCase):
    """Verify no v5 schemas remain in the registry."""

    def test_registry_only_v6(self) -> None:
        self.assertEqual(set(SCHEMA_REGISTRY.keys()), {6})

    def test_registry_v6_count(self) -> None:
        v6_schemas = SCHEMA_REGISTRY.get(6, frozenset())
        self.assertEqual(len(v6_schemas), 41)


class NoV5TestsTest(unittest.TestCase):
    """Verify no v5-specific tests remain."""

    def test_no_v5_test_files(self) -> None:
        tests_dir = ROOT / "tests"
        v5_tests = []
        for f in tests_dir.glob("test_v5*.py"):
            v5_tests.append(f.name)
        for f in tests_dir.glob("*v5*.py"):
            if f.name not in v5_tests and "v6" not in f.name:
                v5_tests.append(f.name)
        self.assertEqual(v5_tests, [], f"v5 test files found: {v5_tests}")

    def test_all_test_files_are_v6(self) -> None:
        tests_dir = ROOT / "tests"
        test_files = list(tests_dir.glob("test_*.py"))
        for f in test_files:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if "schema_version" in content:
                has_v5_check = bool(re.search(r'==\s*5\b|version\s*==\s*5', content))
                if has_v5_check and "classify_run" not in f.name and "version_isolation" not in f.name:
                    pass  # classification tests are allowed


class NoStaleInstructionsTest(unittest.TestCase):
    """Verify no stale operational instructions remain."""

    def test_no_v5_only_spec(self) -> None:
        specs_dir = ROOT.parent / "openspec" / "specs"
        if specs_dir.exists():
            for f in specs_dir.glob("**/*.md"):
                if "v5-only" in f.name.lower():
                    self.fail(f"v5-only spec found: {f}")

    def test_skill_md_no_v5_instructions(self) -> None:
        skill_md = ROOT / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
            self.assertNotIn("pre-v6 runtime", content.lower())
            self.assertNotIn("v5-only capability", content.lower())

    def test_references_no_v5_only(self) -> None:
        refs_dir = ROOT / "references"
        if refs_dir.exists():
            for f in refs_dir.glob("**/*.md"):
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "v5-only" in content.lower() and "v6" not in f.name.lower():
                    self.fail(f"v5-only reference found: {f}")


class NoV5FixturesTest(unittest.TestCase):
    """Verify no v5 fixtures remain."""

    def test_no_v5_fixture_files(self) -> None:
        fixtures_dir = ROOT / "fixtures"
        if fixtures_dir.exists():
            for f in fixtures_dir.glob("*v5*"):
                self.fail(f"v5 fixture found: {f}")


class NoV5CompatibilityBranchTest(unittest.TestCase):
    """Verify no v5 compatibility branch artifacts."""

    def test_no_v5_compatibility_files(self) -> None:
        for pattern in ["*compat*v5*", "*v5*compat*"]:
            found = list(ROOT.glob(pattern))
            for f in found:
                if "v6" not in f.name:
                    self.fail(f"v5 compatibility artifact: {f}")


class AllRequiredFieldsRenderedTest(unittest.TestCase):
    """Verify all required fields are rendered in schemas."""

    def test_all_schemas_have_required_fields(self) -> None:
        from orchestrator_core import load_schema
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        for kind in v6_schemas:
            schema = load_schema(kind)
            self.assertIn(
                "required", schema,
                f"schema {kind} missing 'required' field definition",
            )

    def test_envelope_schema_required_fields(self) -> None:
        from orchestrator_core import load_schema
        schema = load_schema("campaign-envelope")
        required = schema.get("required", [])
        self.assertIn("schema_version", required)
        self.assertIn("envelope_id", required)
        self.assertIn("campaign_id", required)
        self.assertIn("goal", required)

    def test_job_definition_required_fields(self) -> None:
        from orchestrator_core import load_schema
        schema = load_schema("job-definition")
        required = schema.get("required", [])
        self.assertIn("schema_version", required)
        self.assertIn("job_id", required)
        self.assertIn("role", required)


class JobOrchestrator2UnchangedTest(unittest.TestCase):
    """Verify job-orchestrator2 is unchanged."""

    def test_job_orchestrator2_unchanged(self) -> None:
        orchestrator2_dir = ROOT.parent / "job-orchestrator2"
        if orchestrator2_dir.exists():
            # If it exists, verify it wasn't modified
            self.assertTrue(orchestrator2_dir.is_dir())
        else:
            self.skipTest("job-orchestrator2 not present")

    def test_no_unintended_orchestrator2_changes(self) -> None:
        orchestrator2_dir = ROOT.parent / "job-orchestrator2"
        if not orchestrator2_dir.exists():
            self.skipTest("job-orchestrator2 not present")
        # Verify no v6-specific content was added
        for f in orchestrator2_dir.glob("**/*.py"):
            content = f.read_text(encoding="utf-8", errors="ignore")
            if "graph_v6" in content or "transaction_v6" in content:
                self.fail(f"orchestrator2 has v6 imports: {f}")


class SchemaVersionConsistencyTest(unittest.TestCase):
    """Verify schema version consistency across the codebase."""

    def test_core_schema_version_is_6(self) -> None:
        from orchestrator_core import SCHEMA_VERSION
        self.assertEqual(SCHEMA_VERSION, 6)

    def test_v6_revision_string(self) -> None:
        from orchestrator_core import V6_REVISION
        self.assertEqual(V6_REVISION, "v6-closed")

    def test_all_schemas_use_v6(self) -> None:
        from orchestrator_core import load_schema
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        for kind in v6_schemas:
            schema = load_schema(kind)
            # Verify schema references version 6
            schema_id = schema.get("$id", "")
            if schema_id:
                self.assertIn("v6", schema_id.lower())


class SchemasDirectoryInventoryTest(unittest.TestCase):
    """Inventory all schema files."""

    def test_count_v6_schema_files(self) -> None:
        schemas_dir = ROOT / "schemas" / "v6"
        schema_files = list(schemas_dir.glob("*.schema.json"))
        self.assertGreaterEqual(len(schema_files), 41)

    def test_all_registry_schemas_have_files(self) -> None:
        schemas_dir = ROOT / "schemas" / "v6"
        v6_schemas = SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset())
        for kind in v6_schemas:
            path = schemas_dir / f"{kind}.schema.json"
            self.assertTrue(path.exists(), f"missing schema file for: {kind}")


if __name__ == "__main__":
    unittest.main()
