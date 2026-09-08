from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from jobctl import parser  # noqa: E402


class Version5DocumentationTest(unittest.TestCase):
    def test_documents_real_v5_commands_and_trust_boundary(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        prompt = Path("C:/Projects/BlackholeSim/AUTONOMOUS_COMPLETION_PROMPT.md").read_text(encoding="utf-8")
        for text in (skill, prompt):
            self.assertIn("launch-receipt", text)
            self.assertIn("response-receipt", text)
            self.assertIn("adapter", text.lower())
            self.assertIn("run_complete", text)
            self.assertIn("successful", text)
        self.assertNotIn("ai-skills\\skills\\job-orchestrator\\scripts\\jobctl.py", prompt)

    def test_documented_v5_cli_shapes_parse(self) -> None:
        script = r"C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py"
        commands = [
            ["init", "--protocol-version", "5", "--request-file", "request.md", "--goal", "Goal"],
            ["register", "--run", "RUN", "--definition", "jobs.json"],
            ["next", "--run", "RUN"],
            ["launch-receipt", "--run", "RUN", "--receipt", "receipt.json"],
            ["response-receipt", "--run", "RUN", "--receipt", "response.json"],
            ["answer", "--run", "RUN", "--job", "J001", "--answer", "yes", "--source", "user"],
            ["advisory-decision", "--run", "RUN", "--origin", "J001", "--advisory", "J002", "--decision", "keep_waiting"],
            ["audit", "--run", "RUN"],
            ["recover", "--run", "RUN", "--job", "J001", "--evidence", "evidence.json"],
            ["repair", "--run", "RUN", "--job", "J001", "--disposition", "failed", "--reason", "blocked"],
        ]
        for arguments in commands:
            with self.subTest(arguments=arguments):
                parser().parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
