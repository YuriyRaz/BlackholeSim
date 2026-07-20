from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import validate_record  # noqa: E402


TEMPLATE = ROOT / "assets" / "run-template"
JOB_TEMPLATE = Path("jobs") / "{{JOB_ID}}"
EXPECTED_FILES = {
    Path("run.json"),
    Path("request.md"),
    Path("setup.json"),
    Path("orchestrator.lock"),
    Path("jobs/index.json"),
    JOB_TEMPLATE / "job.json",
    JOB_TEMPLATE / "prompt.md",
    JOB_TEMPLATE / "report.md",
    JOB_TEMPLATE / "checkpoint.md",
}
REPLACEMENTS = {
    "{{RUN_ID}}": "RUN-1",
    "{{GOAL}}": "Complete the request",
    "{{JOB_ID}}": "J001",
    "{{JOB_TITLE}}": "Apply the change",
    "{{CREATED_AT}}": "2026-07-14T12:00:00Z",
    "{{WORKSPACE}}": "C:/workspace",
}


def render_json(path: Path) -> dict:
    rendered = path.read_text(encoding="utf-8")
    for placeholder, value in REPLACEMENTS.items():
        rendered = rendered.replace(placeholder, value)
    return json.loads(rendered)


class Version4RunTemplateTest(unittest.TestCase):
    def test_template_has_only_the_v4_run_layout(self) -> None:
        files = {
            path.relative_to(TEMPLATE)
            for path in TEMPLATE.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, EXPECTED_FILES)

    def test_json_templates_match_v4_schemas_and_index(self) -> None:
        run = render_json(TEMPLATE / "run.json")
        setup = render_json(TEMPLATE / "setup.json")
        job = render_json(TEMPLATE / JOB_TEMPLATE / "job.json")

        validate_record("run", run)
        validate_record("setup", setup)
        validate_record("job", job)

        index = render_json(TEMPLATE / "jobs" / "index.json")
        self.assertEqual(index, {"jobs": [job["id"]]})
        self.assertEqual(run["job_ids"], index["jobs"])

    def test_job_artifact_paths_match_the_layout(self) -> None:
        job = render_json(TEMPLATE / JOB_TEMPLATE / "job.json")
        self.assertEqual(job["prompt_path"], "jobs/J001/prompt.md")
        self.assertEqual(job["report_path"], "jobs/J001/report.md")
        self.assertEqual(job["checkpoint_path"], "jobs/J001/checkpoint.md")


if __name__ == "__main__":
    unittest.main()
