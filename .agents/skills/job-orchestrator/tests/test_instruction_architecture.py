from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")
SHIPPED_TEXT_SUFFIXES = {".json", ".lock", ".md", ".py", ".txt", ".yaml", ".yml"}


class InstructionArchitectureTest(unittest.TestCase):
    def test_local_documentation_links_resolve_and_avoid_change_artifacts(self) -> None:
        for document in DOCS:
            text = document.read_text(encoding="utf-8")
            self.assertNotIn("openspec/changes/", text, document)
            self.assertNotIn("openspec\\changes\\", text, document)
            for target in LINK.findall(text):
                self.assertFalse(target.startswith(("http://", "https://")), target)
                resolved = (document.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"{document}: {target}")

    def test_operator_safety_and_progressive_routing_are_explicit(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        recovery = (ROOT / "references" / "recovery.md").read_text(
            encoding="utf-8"
        ).lower()
        for text in (skill, recovery):
            self.assertIn("never manually", text)
            self.assertIn("authoritative", text)
            self.assertIn("state", text)
        self.assertIn("editable until successful ingestion", skill)
        self.assertIn("interruption", skill)
        for reference in (
            "protocol.md",
            "recovery.md",
            "job-protocol.md",
            "transport-capabilities.md",
            "maintainer-guidance.md",
        ):
            self.assertIn(reference, skill)

    def test_only_v4_assets_and_cli_surface_are_shipped(self) -> None:
        schemas = ROOT / "schemas"
        self.assertEqual([path.name for path in schemas.iterdir() if path.is_dir()], ["v4"])
        self.assertFalse((ROOT / "scripts" / "workerctl.py").exists())
        self.assertFalse((ROOT / "scripts" / "verify_repair.py").exists())

        architecture_test = Path("tests/test_instruction_architecture.py")
        outcome_test = Path("tests/test_v4_outcome.py")
        registration_test = Path("tests/test_v4_registration.py")
        legacy_allowlist = {
            "class Lease:": {architecture_test},
            "def run_lease(": {architecture_test},
            '"lifecycle-event"': {architecture_test},
            "def validate_dispatch(": {architecture_test},
            "def validate_schema(": {architecture_test},
            'add_parser("compile"': {architecture_test},
            'add_parser("migrate-v2"': {architecture_test},
            "workerctl": {architecture_test},
            "next_permitted": {architecture_test},
            "protocol_ack": {architecture_test},
            "contract_revision": {architecture_test, outcome_test},
            "dispatch_id": {architecture_test, outcome_test},
            "work_units": {architecture_test, outcome_test},
            "completed_work_units": {architecture_test, outcome_test},
            "current_workflow_node_id": {architecture_test, registration_test},
            "checkpoint_sha256": {architecture_test},
            "Next permitted:": {architecture_test},
            "Completed units:": {architecture_test},
            "executing a dispatch": {architecture_test},
        }
        violations: list[str] = []
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            self.assertIn(
                path.suffix,
                SHIPPED_TEXT_SUFFIXES,
                f"Classify new shipped file type before excluding it: {path}",
            )
            relative = path.relative_to(ROOT)
            text = path.read_text(encoding="utf-8")
            for forbidden, allowed_paths in legacy_allowlist.items():
                if forbidden in text and relative not in allowed_paths:
                    violations.append(f"{relative}: {forbidden}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
