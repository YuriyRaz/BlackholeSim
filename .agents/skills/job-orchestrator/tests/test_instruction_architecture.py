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

    def test_only_current_protocol_assets_are_shipped(self) -> None:
        legacy_reference = Path("references/legacy-root-session-orchestration.md")
        schemas = ROOT / "schemas"
        self.assertEqual(
            sorted(
                path.name
                for path in schemas.iterdir()
                if path.is_dir() and any(path.iterdir())
            ),
            ["v6"],
        )
        self.assertFalse((ROOT / "scripts" / "workerctl.py").exists())
        self.assertFalse((ROOT / "scripts" / "verify_repair.py").exists())
        for obsolete_assets in ("run-template", "prompts"):
            root = ROOT / "assets" / obsolete_assets
            self.assertFalse(root.exists() and any(path.is_file() for path in root.rglob("*")))
        self.assertEqual([], list((ROOT / "tests").glob("test_v[0-4]_*.py")))
        self.assertEqual([], list((ROOT / "tests").glob("test_v5_*.py")))

        old_version_violations: list[str] = []
        legacy_assets: set[Path] = set()
        obsolete_label = "lega" + "cy"
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or any(p.startswith(".") for p in path.parts):
                continue
            self.assertIn(
                path.suffix,
                SHIPPED_TEXT_SUFFIXES,
                f"Classify new shipped file type before excluding it: {path}",
            )
            relative = path.relative_to(ROOT)
            if relative.parts[0] == "tests":
                continue
            text = path.read_text(encoding="utf-8").lower()
            if obsolete_label in text:
                legacy_assets.add(relative)
            if re.search(r"\bv[0-4]\b", text):
                old_version_violations.append(str(relative))
        self.assertEqual([], old_version_violations)
        self.assertEqual({Path("SKILL.md"), legacy_reference}, legacy_assets)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        legacy = (ROOT / legacy_reference).read_text(encoding="utf-8").lower()
        self.assertIn(
            "[legacy-root-session-orchestration.md]"
            "(references/legacy-root-session-orchestration.md)",
            skill,
        )
        self.assertIn("only supported default approach", skill)
        self.assertIn("# legacy: root session orchestration", legacy)
        self.assertIn("deprecated", legacy)
        self.assertIn("protocol version 6", skill)


if __name__ == "__main__":
    unittest.main()
