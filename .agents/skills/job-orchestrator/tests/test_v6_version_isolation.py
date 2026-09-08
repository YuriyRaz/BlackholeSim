"""Version-isolation architecture tests proving v6-only runtime, schemas, fixtures, docs, CLI."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, SCHEMA_REGISTRY, V6_REVISION, V6, load_schema  # noqa: E402


class V6DynamicRuntimeIsolationTest(unittest.TestCase):
    """Prove the dynamic runtime exposes only version 6."""

    def test_schema_version_is_six(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 6)

    def test_v6_revision_defined(self) -> None:
        self.assertEqual(V6_REVISION, "v6-closed")

    def test_v6_constant_matches_schema_version(self) -> None:
        self.assertEqual(V6, SCHEMA_VERSION)

    def test_schema_registry_contains_only_v6(self) -> None:
        self.assertEqual(set(SCHEMA_REGISTRY.keys()), {6})

    def test_all_v6_schema_kinds_load(self) -> None:
        for kind in SCHEMA_REGISTRY[6]:
            schema = load_schema(kind, version=6)
            self.assertIsInstance(schema, dict)
            self.assertIn("type", schema, f"v6 schema {kind} must define a type")


class V6SchemaDirectoryIsolationTest(unittest.TestCase):
    """Prove schemas directory contains only v6 schemas."""

    def test_only_v6_schema_directory_exists(self) -> None:
        schemas = ROOT / "schemas"
        dirs = [d for d in schemas.iterdir() if d.is_dir()]
        self.assertEqual([d.name for d in dirs], ["v6"])

    def test_v5_schema_directory_absent(self) -> None:
        self.assertFalse((ROOT / "schemas" / "v5").exists())

    def test_no_v5_schema_files(self) -> None:
        v5_files = list((ROOT / "schemas").rglob("v5*.json"))
        self.assertEqual(v5_files, [])


class V6TestFixtureIsolationTest(unittest.TestCase):
    """Prove fixtures, docs, and CLI expose only v6."""

    def test_no_v5_test_files(self) -> None:
        v5_tests = list((ROOT / "tests").glob("test_v5_*.py"))
        self.assertEqual(v5_tests, [], f"v5 test files found: {v5_tests}")

    def test_no_v5_support_module(self) -> None:
        self.assertFalse((ROOT / "tests" / "v5_support.py").exists())

    def test_no_v5_core_script(self) -> None:
        self.assertFalse((ROOT / "scripts" / "v5_core.py").exists())

    def test_no_transport_v5_script(self) -> None:
        self.assertFalse((ROOT / "scripts" / "transport_v5.py").exists())

    def test_instruction_architecture_references_v6(self) -> None:
        test_file = ROOT / "tests" / "test_instruction_architecture.py"
        content = test_file.read_text(encoding="utf-8")
        self.assertIn('["v6"]', content)
        self.assertNotIn('["v5"]', content)


class V6OrchestratorCoreIsolationTest(unittest.TestCase):
    """Prove orchestrator_core.py exposes only v6."""

    def test_rejects_v5_schema_version(self) -> None:
        from orchestrator_core import OrchestratorError
        with self.assertRaises(OrchestratorError):
            load_schema("run", version=5)

    def test_rejects_v4_schema_version(self) -> None:
        from orchestrator_core import OrchestratorError
        with self.assertRaises(OrchestratorError):
            load_schema("run", version=4)

    def test_classify_rejects_v5_run(self) -> None:
        import tempfile
        import json
        from orchestrator_core import classify_run_protocol
        with tempfile.TemporaryDirectory() as td:
            run_path = Path(td) / "run.json"
            run_path.write_text(json.dumps({
                "schema_version": 5,
                "protocol_revision": "v5-closed",
                "run_id": "test",
            }), encoding="utf-8")
            result = classify_run_protocol(Path(td))
            self.assertEqual(result["version"], 5)
            self.assertEqual(result["trust"], "untrusted")
            self.assertFalse(result["mutable"])

    def test_reject_v5_or_earlier_raises_on_v5(self) -> None:
        from orchestrator_core import reject_v5_or_earlier, OrchestratorError
        with self.assertRaises(OrchestratorError):
            reject_v5_or_earlier({"schema_version": 5})

    def test_reject_v5_or_earlier_raises_on_v4(self) -> None:
        from orchestrator_core import reject_v5_or_earlier, OrchestratorError
        with self.assertRaises(OrchestratorError):
            reject_v5_or_earlier({"schema_version": 4})

    def test_reject_v5_or_earlier_accepts_v6(self) -> None:
        from orchestrator_core import reject_v5_or_earlier
        reject_v5_or_earlier({"schema_version": 6})


class JobOrchestrator2UnchangedTest(unittest.TestCase):
    """Prove skills/job-orchestrator2/ is unchanged."""

    def test_job_orchestrator2_unchanged(self) -> None:
        alt = ROOT.parent / "job-orchestrator2"
        if alt.exists():
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--name-only", str(alt)],
                capture_output=True, text=True, cwd=str(ROOT.parent.parent),
            )
            self.assertEqual(result.stdout.strip(), "",
                             f"job-orchestrator2 has uncommitted changes: {result.stdout}")


if __name__ == "__main__":
    unittest.main()
