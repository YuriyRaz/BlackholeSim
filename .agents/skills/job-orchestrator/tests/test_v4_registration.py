from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    load_v4_state,
    register_v4_jobs,
    render_v4_initial_prompt,
    write_v4_document,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"


def worker_contract_body() -> str:
    contract = (ROOT / "references" / "job-protocol.md").read_text(
        encoding="utf-8"
    ).strip()
    return contract.removeprefix("# Worker Contract").strip()


class Version4RegistrationTest(unittest.TestCase):
    def run_jobctl(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(JOBCTL), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
        )

    def initialize(self, base: Path) -> Path:
        request = base / "request.md"
        request.write_text("Register the requested jobs.\n", encoding="utf-8")
        process = self.run_jobctl(
            "init",
            "--request-file", request,
            "--goal", "Register jobs",
            "--run-id", "RUN-REGISTER",
            "--state-root", base / "state",
            "--workspace", base,
        )
        self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
        return base / "state" / "RUN-REGISTER"

    def snapshot_run(self, run_root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(run_root).as_posix(): path.read_bytes()
            for path in run_root.rglob("*")
            if path.is_file()
        }

    def job_definition(self, job_id: str, **overrides: object) -> dict:
        job = {
            "id": job_id,
            "title": f"Job {job_id}",
            "goal": f"Complete job {job_id}.",
            "completion_conditions": [f"Job {job_id} is complete."],
            "report_required": False,
        }
        job.update(overrides)
        return job

    def test_register_persists_complete_definitions_and_authoritative_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize(base)
            definition = {
                "schema_version": 4,
                "jobs": [
                    {
                        "id": "J001",
                        "title": "Investigate the change",
                        "goal": "Establish the required behavior.",
                        "workflow": None,
                        "requirements": ["Inspect current behavior."],
                        "constraints": ["Do not edit source files."],
                        "completion_conditions": ["Findings are conclusive."],
                        "context": ["Use the initialized workspace."],
                        "escalation": "Return a precise blocking question.",
                        "report_required": False,
                        "priority": 20,
                        "depends_on": [],
                        "parent_job_id": None,
                        "related_reports": [],
                        "recovery_policy": None,
                    },
                    {
                        "id": "J002",
                        "title": "Apply the change",
                        "goal": "Implement the established behavior.",
                        "workflow": "Implement, test, and report.",
                        "requirements": ["Keep the change focused."],
                        "constraints": ["Do not publish artifacts."],
                        "completion_conditions": ["Focused tests pass."],
                        "context": ["Use J001 as the parent investigation."],
                        "escalation": "Return needs_input for blocked decisions.",
                        "report_required": True,
                        "priority": 50,
                        "depends_on": ["J001"],
                        "parent_job_id": "J001",
                        "related_reports": [],
                        "recovery_policy": {
                            "effect": "repository",
                            "check": "Inspect repository state before retrying.",
                        },
                    },
                ],
            }
            definition_path = base / "jobs.json"
            definition_path.write_text(json.dumps(definition), encoding="utf-8")

            process = self.run_jobctl(
                "register", "--run", run_root, "--definition", definition_path
            )

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            self.assertEqual(json.loads(process.stdout), {"registered": ["J001", "J002"]})
            setup = json.loads((run_root / "setup.json").read_text(encoding="utf-8"))
            self.assertEqual(setup["jobs"], definition["jobs"])
            state = load_v4_state(run_root)
            self.assertEqual(state["run"]["job_ids"], ["J001", "J002"])
            self.assertEqual(state["ready_job_ids"], ["J001"])
            first = state["jobs"]["J001"]
            second = state["jobs"]["J002"]
            self.assertEqual(first["creation_sequence"], 1)
            self.assertEqual(second["creation_sequence"], 2)
            self.assertEqual(second["priority"], 50)
            self.assertEqual(second["depends_on"], ["J001"])
            self.assertEqual(second["parent_job_id"], "J001")
            self.assertTrue(second["report_required"])
            self.assertEqual(second["recovery_policy"], definition["jobs"][1]["recovery_policy"])
            self.assertEqual(
                (run_root / second["prompt_path"]).read_text(encoding="utf-8"),
                f"""# Apply the change

Job ID: `J002`

## Worker Contract
{worker_contract_body()}

## Goal
Implement the established behavior.

## Workflow
Implement, test, and report.

## Requirements
- Keep the change focused.

## Constraints
- Do not publish artifacts.
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- Focused tests pass.

## Context
- Workspace: `{base}`
- Use J001 as the parent investigation.

## Escalation
Return needs_input for blocked decisions.

## Report Expectation
Write the final report to `jobs/J002/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

## Recovery Requirements
- Effect: `repository`
- Required recovery check before retry: Inspect repository state before retrying.

Begin the domain work immediately.
""",
            )
            self.assertEqual((run_root / second["report_path"]).read_bytes(), b"")
            self.assertFalse((run_root / "orchestrator.lock").exists())
            self.assertEqual(
                json.loads((run_root / "jobs" / "index.json").read_text(encoding="utf-8")),
                {"jobs": ["J001", "J002"]},
            )

    def test_render_initial_prompt_uses_open_workflow_and_omits_absent_sections(
        self,
    ) -> None:
        definition = {
            "id": "J001",
            "title": "Investigate behavior",
            "goal": "Explain the observed behavior.",
            "completion_conditions": ["The explanation is evidence-based."],
            "report_required": False,
        }

        prompt = render_v4_initial_prompt(
            definition,
            workspace="C:/work/repository",
            report_path="jobs/J001/report.md",
        )

        self.assertEqual(
            prompt,
            f"""# Investigate behavior

Job ID: `J001`

## Worker Contract
{worker_contract_body()}

## Goal
Explain the observed behavior.

## Workflow
Choose an appropriate workflow and methods to achieve the goal within the stated constraints.

## Constraints
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- The explanation is evidence-based.

## Context
- Workspace: `C:/work/repository`

## Escalation
If blocked by missing information, authority, a decision, or separately managed work, return `needs_input` with a precise question and relevant context.

## Report Expectation
A durable report is optional. If you create one, write it to `jobs/J001/report.md`. Return a non-empty summary with the final outcome.

Begin the domain work immediately.
""",
        )
        self.assertNotIn("## Requirements", prompt)
        self.assertNotIn("## Related Reports", prompt)
        self.assertNotIn("## Recovery Requirements", prompt)
        self.assertNotIn("verif", prompt.lower())

    def test_initial_prompt_embeds_the_canonical_worker_contract(self) -> None:
        prompt = render_v4_initial_prompt(
            {
                "id": "J001",
                "title": "Perform bounded work",
                "goal": "Complete the assigned job.",
                "completion_conditions": ["The assigned work is complete."],
                "report_required": True,
            },
            workspace="C:/work/repository",
            report_path="jobs/J001/report.md",
        )

        self.assertIn(
            "## Worker Contract\n" + worker_contract_body() + "\n\n## Goal",
            prompt,
        )
        for required in (
            "checkpoint.md",
            '"status":"completed"',
            '"status":"needs_input"',
            '"status":"failed"',
            "only the root",
            "operator creates explicit jobs",
        ):
            self.assertIn(required, prompt)
        self.assertNotIn("jobctl next", prompt)
        self.assertNotIn("jobctl register", prompt)
        self.assertNotIn("jobctl advisory-decision", prompt)

    def test_register_preserves_prescribed_domain_workflow_as_opaque_instructions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize(base)
            workflow = """1. Apply with skill `openspec-apply-change`.
2. Verify only with `domain-proof --exact`.
3. Repair any findings in the same session.
4. Run skill `openspec-verify-change` and report."""
            definition = {
                "schema_version": 4,
                "jobs": [{
                    "id": "J001",
                    "title": "Follow the prescribed domain workflow",
                    "goal": "Produce the requested domain result.",
                    "workflow": workflow,
                    "completion_conditions": ["The prescribed workflow is complete."],
                    "report_required": False,
                }],
            }
            definition_path = base / "jobs.json"
            definition_path.write_text(json.dumps(definition), encoding="utf-8")

            process = self.run_jobctl(
                "register", "--run", run_root, "--definition", definition_path
            )

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            setup = json.loads((run_root / "setup.json").read_text(encoding="utf-8"))
            self.assertEqual(setup["jobs"][0]["workflow"], workflow)
            prompt = (run_root / "jobs" / "J001" / "prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"## Workflow\n{workflow}\n\n## Constraints", prompt)
            self.assertEqual(prompt.count(workflow), 1)
            self.assertNotIn("Choose an appropriate workflow", prompt)

            state = load_v4_state(run_root)
            self.assertEqual(list(state["jobs"]), ["J001"])
            self.assertEqual(state["jobs"]["J001"]["status"], "queued")
            self.assertEqual(state["ready_job_ids"], ["J001"])
            interpreted_fields = {
                "workflow", "workflow_stage", "skill", "verification_method",
                "current_workflow_node_id",
            }
            self.assertTrue(interpreted_fields.isdisjoint(state["jobs"]["J001"]))

    def test_render_initial_prompt_includes_related_reports_and_idempotency_key(
        self,
    ) -> None:
        definition = {
            "id": "J003",
            "title": "Publish release",
            "goal": "Publish the verified release.",
            "workflow": "Inspect reports, publish once, then verify publication.",
            "requirements": ["Use the approved release metadata."],
            "constraints": ["Do not publish a different version."],
            "completion_conditions": ["The release is visible externally."],
            "context": ["Release version: 2.4.0"],
            "related_reports": [
                "jobs/J001/report.md",
                "jobs/J002/report.md",
            ],
            "escalation": "Ask for authority if publication is not approved.",
            "report_required": True,
            "recovery_policy": {
                "effect": "external_non_idempotent",
                "check": "Query whether release 2.4.0 already exists.",
                "idempotency_key": "release-2.4.0",
            },
        }

        first = render_v4_initial_prompt(
            definition,
            workspace="C:/work/repository",
            report_path="jobs/J003/report.md",
        )
        second = render_v4_initial_prompt(
            definition,
            workspace="C:/work/repository",
            report_path="jobs/J003/report.md",
        )

        self.assertEqual(first, second)
        self.assertIn(
            "## Related Reports\n- `jobs/J001/report.md`\n- `jobs/J002/report.md`",
            first,
        )
        self.assertIn(
            "- Required recovery check before retry: Query whether release 2.4.0 already exists.",
            first,
        )
        self.assertIn("- Idempotency key: `release-2.4.0`", first)

    def test_register_rejects_invalid_definitions_without_any_run_mutation(self) -> None:
        missing_goal = self.job_definition("J001")
        missing_goal.pop("goal")
        cases = (
            (
                "unknown dependency",
                [self.job_definition("J001", depends_on=["UNKNOWN"])],
                "unknown dependencies",
            ),
            (
                "dependency cycle",
                [
                    self.job_definition("J001", depends_on=["J002"]),
                    self.job_definition("J002", depends_on=["J001"]),
                ],
                "dependency cycle",
            ),
            (
                "unknown parent",
                [self.job_definition("J001", parent_job_id="UNKNOWN")],
                "unknown parent",
            ),
            (
                "self parent",
                [self.job_definition("J001", parent_job_id="J001")],
                "parent cycle",
            ),
            (
                "parent cycle",
                [
                    self.job_definition("J001", parent_job_id="J002"),
                    self.job_definition("J002", parent_job_id="J001"),
                ],
                "parent cycle",
            ),
            ("missing goal", [missing_goal], "goal"),
            (
                "blank goal",
                [self.job_definition("J001", goal="  \n")],
                "non-empty goal",
            ),
            (
                "missing external recovery check",
                [self.job_definition(
                    "J001",
                    recovery_policy={"effect": "external_non_idempotent"},
                )],
                "check",
            ),
            (
                "blank external recovery check",
                [self.job_definition(
                    "J001",
                    recovery_policy={
                        "effect": "external_non_idempotent",
                        "check": " \t",
                    },
                )],
                "non-empty recovery check",
            ),
        )

        for name, jobs, expected_error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                run_root = self.initialize(base)
                definition_path = base / "invalid.json"
                definition_path.write_text(json.dumps({
                    "schema_version": 4,
                    "jobs": jobs,
                }), encoding="utf-8")
                before = self.snapshot_run(run_root)

                process = self.run_jobctl(
                    "register", "--run", run_root, "--definition", definition_path
                )

                self.assertEqual(process.returncode, 2, process.stderr or process.stdout)
                self.assertIn(expected_error, json.loads(process.stdout)["error"])
                self.assertEqual(self.snapshot_run(run_root), before)

    def test_register_rolls_back_when_authoritative_run_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize(base)
            definition = {
                "schema_version": 4,
                "jobs": [{
                    "id": "J001",
                    "title": "Rollback probe",
                    "goal": "Verify registration rollback.",
                    "completion_conditions": ["Registration is atomic."],
                    "report_required": False,
                }],
            }
            before_run = (run_root / "run.json").read_bytes()
            before_setup = (run_root / "setup.json").read_bytes()
            before_index = (run_root / "jobs" / "index.json").read_bytes()

            def fail_run_commit(path: Path, kind: str, value: dict) -> None:
                if kind == "run":
                    raise OSError("simulated run commit failure")
                write_v4_document(path, kind, value)

            with patch(
                "orchestrator_core.write_v4_document",
                side_effect=fail_run_commit,
            ):
                with self.assertRaisesRegex(
                    OrchestratorError, "simulated run commit failure"
                ):
                    register_v4_jobs(run_root, definition, controller="test")

            self.assertEqual((run_root / "run.json").read_bytes(), before_run)
            self.assertEqual((run_root / "setup.json").read_bytes(), before_setup)
            self.assertEqual((run_root / "jobs" / "index.json").read_bytes(), before_index)
            self.assertFalse((run_root / "jobs" / "J001").exists())
            self.assertEqual(load_v4_state(run_root)["jobs"], {})


if __name__ == "__main__":
    unittest.main()
