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

import orchestrator_core  # noqa: E402
from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    load_v4_state,
    register_v4_jobs,
    write_v4_document,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"


class Version4AdvisoryRegistrationTest(unittest.TestCase):
    def run_jobctl(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(JOBCTL), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
        )

    def initialize_waiting_origin(self, base: Path) -> Path:
        request = base / "request.md"
        request.write_text("Resolve an architecture question.\n", encoding="utf-8")
        initialized = self.run_jobctl(
            "init",
            "--request-file", request,
            "--goal", "Resolve the architecture question",
            "--run-id", "RUN-ADVISORY",
            "--state-root", base / "state",
            "--workspace", base,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr or initialized.stdout)
        run_root = base / "state" / "RUN-ADVISORY"
        origin_definition = base / "origin.json"
        origin_definition.write_text(json.dumps({
            "schema_version": 4,
            "jobs": [{
                "id": "J001",
                "title": "Implement the protocol",
                "goal": "Implement the selected relationship model.",
                "completion_conditions": ["The relationship model is implemented."],
                "report_required": False,
            }],
        }), encoding="utf-8")
        registered = self.run_jobctl(
            "register", "--run", run_root, "--definition", origin_definition
        )
        self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)
        session = self.run_jobctl(
            "session", "--run", run_root, "--job", "J001",
            "--session-ref", "session-origin",
        )
        self.assertEqual(session.returncode, 0, session.stderr or session.stdout)
        outcome = base / "question.json"
        outcome.write_text(json.dumps({
            "status": "needs_input",
            "summary": "Architecture guidance is required.",
            "question": "Should waiting relationships use jobs or child requests?",
            "context": "The implementation needs an independent architecture decision.",
        }), encoding="utf-8")
        recorded = self.run_jobctl(
            "outcome", "--run", run_root, "--job", "J001", "--outcome", outcome
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr or recorded.stdout)
        return run_root

    def advisory_definition(self, *job_ids: str) -> dict:
        job_ids = job_ids or ("J002",)
        return {
            "schema_version": 4,
            "jobs": [
                {
                    "id": job_id,
                    "title": f"Advise on the relationship model ({job_id})",
                    "goal": "Recommend a coherent architecture for the pending question.",
                    "completion_conditions": ["A concrete recommendation is reported."],
                    "report_required": True,
                }
                for job_id in job_ids
            ],
        }

    def register_advisories(
        self, base: Path, run_root: Path, *job_ids: str
    ) -> subprocess.CompletedProcess[str]:
        definition_path = base / ("advisory-" + "-".join(job_ids) + ".json")
        definition_path.write_text(
            json.dumps(self.advisory_definition(*job_ids)), encoding="utf-8"
        )
        return self.run_jobctl(
            "register",
            "--run", run_root,
            "--definition", definition_path,
            "--advisory-for", "J001",
        )

    def complete_advisory(
        self, base: Path, run_root: Path, job_id: str, *, write_report: bool = True
    ) -> subprocess.CompletedProcess[str]:
        report_path = f"jobs/{job_id}/report.md"
        if write_report:
            (run_root / report_path).write_text(
                f"Recommendation from {job_id}.\n", encoding="utf-8"
            )
        outcome_path = base / f"outcome-{job_id}.json"
        outcome_path.write_text(json.dumps({
            "status": "completed",
            "summary": f"{job_id} completed its recommendation.",
            "report_path": report_path,
        }), encoding="utf-8")
        return self.run_jobctl(
            "outcome",
            "--run", run_root,
            "--job", job_id,
            "--outcome", outcome_path,
            "--session-ref", f"session-{job_id}",
        )

    def snapshot(self, run_root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(run_root).as_posix(): path.read_bytes()
            for path in run_root.rglob("*")
            if path.is_file()
        }

    def test_cli_registers_ordinary_advisory_and_atomically_links_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            before_origin = load_v4_state(run_root)["jobs"]["J001"]
            definition_path = base / "advisory.json"
            definition_path.write_text(
                json.dumps(self.advisory_definition()), encoding="utf-8"
            )

            process = self.run_jobctl(
                "register",
                "--run", run_root,
                "--definition", definition_path,
                "--advisory-for", "J001",
            )

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            self.assertEqual(json.loads(process.stdout), {
                "registered": ["J002"],
                "advisory_for": "J001",
            })
            state = load_v4_state(run_root)
            origin = state["jobs"]["J001"]
            advisory = state["jobs"]["J002"]
            self.assertEqual(origin["status"], "waiting_for_job")
            self.assertEqual(origin["waiting_on"], ["J002"])
            self.assertEqual(origin["pending_question"], before_origin["pending_question"])
            self.assertEqual(origin["outcome"], before_origin["outcome"])
            self.assertEqual(origin["revision"], before_origin["revision"] + 1)
            self.assertEqual(advisory["status"], "queued")
            self.assertEqual(advisory["parent_job_id"], "J001")
            self.assertEqual(advisory["waiting_on"], [])
            self.assertNotIn("advisory", advisory)
            self.assertNotIn("child_request", advisory)
            self.assertEqual(state["ready_job_ids"], ["J002"])

            paths = {path.relative_to(run_root).as_posix() for path in run_root.rglob("*")}
            self.assertFalse(any("event" in path.lower() for path in paths))
            self.assertFalse(any("child_request" in path.lower() for path in paths))
            persisted = json.dumps({
                "run": state["run"],
                "jobs": state["jobs"],
                "setup": json.loads((run_root / "setup.json").read_text(encoding="utf-8")),
            }).lower()
            self.assertNotIn("child_request", persisted)
            self.assertNotIn("lifecycle_event", persisted)

    def test_advisory_registration_rolls_back_origin_and_jobs_on_commit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            before = self.snapshot(run_root)
            original_write = orchestrator_core.write_v4_document

            def fail_origin_commit(
                path: Path,
                kind: str,
                value: dict,
                *,
                transition_path: list[str] | None = None,
            ) -> None:
                if path == run_root / "jobs" / "J001" / "job.json":
                    original_write(path, kind, value, transition_path=transition_path)
                    raise OSError("simulated origin commit failure")
                original_write(path, kind, value, transition_path=transition_path)

            with patch(
                "orchestrator_core.write_v4_document", side_effect=fail_origin_commit
            ):
                with self.assertRaisesRegex(
                    OrchestratorError, "simulated origin commit failure"
                ):
                    register_v4_jobs(
                        run_root,
                        self.advisory_definition(),
                        controller="advisory-test",
                        advisory_for="J001",
                    )

            self.assertEqual(self.snapshot(run_root), before)
            state = load_v4_state(run_root)
            self.assertEqual(state["run"]["job_ids"], ["J001"])
            self.assertEqual(state["jobs"]["J001"]["status"], "waiting_for_input")
            self.assertEqual(state["jobs"]["J001"]["waiting_on"], [])
            self.assertFalse((run_root / "jobs" / "J002").exists())

    def test_advisory_registration_rejects_incoherent_origin_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            definition = self.advisory_definition()
            definition["jobs"][0]["depends_on"] = ["J001"]
            before = self.snapshot(run_root)

            with self.assertRaisesRegex(OrchestratorError, "dependency/waiting cycle"):
                register_v4_jobs(
                    run_root,
                    definition,
                    controller="advisory-test",
                    advisory_for="J001",
                )

            self.assertEqual(self.snapshot(run_root), before)

    def test_one_completed_advisory_automatically_adds_its_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            registered = self.register_advisories(base, run_root, "J002")
            self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)
            revision = load_v4_state(run_root)["jobs"]["J001"]["revision"]

            completed = self.complete_advisory(base, run_root, "J002")

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            origin = load_v4_state(run_root)["jobs"]["J001"]
            self.assertEqual(origin["status"], "waiting_for_job")
            self.assertEqual(origin["waiting_on"], ["J002"])
            self.assertEqual(origin["related_reports"], ["jobs/J002/report.md"])
            self.assertEqual(origin["revision"], revision + 1)

            repeated = self.complete_advisory(base, run_root, "J002")
            self.assertEqual(repeated.returncode, 0, repeated.stderr or repeated.stdout)
            self.assertFalse(json.loads(repeated.stdout)["recorded"])
            repeated_origin = load_v4_state(run_root)["jobs"]["J001"]
            self.assertEqual(repeated_origin["revision"], origin["revision"])
            self.assertEqual(repeated_origin["related_reports"], origin["related_reports"])

    def test_report_ready_origin_gets_focused_deterministic_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            registered = self.register_advisories(base, run_root, "J002")
            self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)
            origin = load_v4_state(run_root)["jobs"]["J001"]
            write_v4_document(
                run_root / "jobs" / "J001" / "job.json",
                "job",
                {
                    **origin,
                    "answers": [{
                        "source": "user",
                        "question": "Must existing run state remain readable?",
                        "text": "Yes, preserve readable state without broadening this job.",
                    }],
                    "revision": origin["revision"] + 1,
                },
            )
            completed = self.complete_advisory(base, run_root, "J002")
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

            first = self.run_jobctl("next", "--run", run_root)
            second = self.run_jobctl("next", "--run", run_root)

            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            self.assertEqual(first.stdout, second.stdout)
            result = json.loads(first.stdout)
            self.assertEqual(result["operation"], "resume_job")
            self.assertEqual(result["job_id"], "J001")
            self.assertEqual(result["session_ref"], "session-origin")
            self.assertIn(
                "## Original Job Goal\n"
                "Implement the selected relationship model.",
                result["prompt"],
            )
            self.assertIn(
                "Should waiting relationships use jobs or child requests?",
                result["prompt"],
            )
            self.assertIn(
                "## User Answer\n"
                "Yes, preserve readable state without broadening this job.",
                result["prompt"],
            )
            self.assertIn(
                "Answer to: Must existing run state remain readable?",
                result["prompt"],
            )
            self.assertIn("- `jobs/J002/report.md`", result["prompt"])
            self.assertNotIn(
                "Recommend a coherent architecture for the pending question.",
                result["prompt"],
            )
            self.assertNotIn("Recommendation from J002.", result["prompt"])
            self.assertIn("do not adopt or combine", result["prompt"])

    def test_multiple_completed_advisories_add_reports_in_waiting_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            registered = self.register_advisories(base, run_root, "J002", "J003")
            self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)

            first = self.complete_advisory(base, run_root, "J003")
            second = self.complete_advisory(base, run_root, "J002")

            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            origin = load_v4_state(run_root)["jobs"]["J001"]
            self.assertEqual(
                origin["related_reports"],
                ["jobs/J002/report.md", "jobs/J003/report.md"],
            )

    def test_missing_advisory_report_keeps_origin_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            registered = self.register_advisories(base, run_root, "J002")
            self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)
            before = load_v4_state(run_root)["jobs"]["J001"]

            completed = self.complete_advisory(
                base, run_root, "J002", write_report=False
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "accessible non-empty report", completed.stderr or completed.stdout
            )
            state = load_v4_state(run_root)
            self.assertEqual(state["jobs"]["J001"], before)
            self.assertEqual(state["jobs"]["J002"]["status"], "queued")

    def test_partial_advisory_completion_does_not_add_any_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = self.initialize_waiting_origin(base)
            registered = self.register_advisories(base, run_root, "J002", "J003")
            self.assertEqual(registered.returncode, 0, registered.stderr or registered.stdout)
            revision = load_v4_state(run_root)["jobs"]["J001"]["revision"]

            completed = self.complete_advisory(base, run_root, "J002")

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            origin = load_v4_state(run_root)["jobs"]["J001"]
            self.assertEqual(origin["status"], "waiting_for_job")
            self.assertEqual(origin["waiting_on"], ["J002", "J003"])
            self.assertEqual(origin["related_reports"], [])
            self.assertEqual(origin["revision"], revision)


if __name__ == "__main__":
    unittest.main()
