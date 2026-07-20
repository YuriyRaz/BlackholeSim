from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    load_v4_state,
    rebuild_v4_job_index,
    load_json,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4LoadingTest(unittest.TestCase):
    def run_document(self, job_ids: list[str]) -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-1",
            "goal": "Complete the request",
            "status": "active",
            "job_ids": job_ids,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def job_document(
        self,
        job_id: str,
        *,
        depends_on: list[str] | None = None,
        parent_job_id: str | None = None,
        priority: int = 10,
        creation_sequence: int = 1,
        status: str = "queued",
    ) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": status,
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": priority,
            "creation_sequence": creation_sequence,
            "depends_on": depends_on or [],
            "parent_job_id": parent_job_id,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": True,
            "report_path": f"jobs/{job_id}/report.md",
            "checkpoint_path": f"jobs/{job_id}/checkpoint.md",
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        if status in {"running", "waiting_for_input", "waiting_for_job", "completed"}:
            job["session_ref"] = f"session-{job_id}"
        if status in {"waiting_for_input", "waiting_for_job"}:
            question = f"What input does {job_id} require?"
            job["pending_question"] = {"text": question}
            job["outcome"] = {
                "status": "needs_input",
                "summary": "Input is required.",
                "question": question,
            }
        if status == "waiting_for_job":
            job["waiting_on"] = ["J001"]
        if status == "completed":
            job["outcome"] = {
                "status": "completed",
                "summary": "Job complete.",
                "report_path": job["report_path"],
            }
        if status == "failed":
            job["outcome"] = {
                "status": "failed",
                "summary": "Job failed.",
            }
        return job

    def write_state(
        self, root: Path, jobs: list[dict], *, run_job_ids: list[str] | None = None
    ) -> None:
        job_ids = run_job_ids if run_job_ids is not None else [job["id"] for job in jobs]
        write_v4_document(root / "run.json", "run", self.run_document(job_ids))
        (root / "jobs").mkdir()
        for job in jobs:
            write_v4_document(
                root / "jobs" / job["id"] / "job.json", "job", job
            )
            if job["status"] == "completed" and job["report_required"]:
                (root / job["report_path"]).write_text(
                    f"Report for {job['id']}\n", encoding="utf-8"
                )

    def test_stale_index_data_never_overrides_authoritative_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001"),
                self.job_document("J002", depends_on=["J001"], parent_job_id="J001"),
            ]
            self.write_state(root, jobs)
            write_json(root / "jobs" / "index.json", {
                "jobs": [
                    {"id": "J001", "status": "completed"},
                    {"id": "STALE", "status": "running"},
                ]
            })

            state = load_v4_state(root)

            self.assertEqual(state["run"]["job_ids"], ["J001", "J002"])
            self.assertEqual(list(state["jobs"]), ["J001", "J002"])
            self.assertEqual(state["jobs"]["J001"]["status"], "queued")

    def test_corrupt_index_does_not_prevent_loading_authoritative_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            (root / "jobs" / "index.json").write_text("{corrupt", encoding="utf-8")

            state = load_v4_state(root)

            self.assertEqual(list(state["jobs"]), ["J001"])

    def test_rebuilds_stale_index_from_authoritative_job_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [self.job_document("J002"), self.job_document("J001")]
            self.write_state(root, jobs, run_job_ids=["J002", "J001"])
            write_json(root / "jobs" / "index.json", {"jobs": ["STALE"]})

            rebuilt = rebuild_v4_job_index(root)

            self.assertEqual(rebuilt, {"jobs": ["J001", "J002"]})
            self.assertEqual(load_json(root / "jobs" / "index.json"), rebuilt)

    def test_rebuild_replaces_corrupt_index_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            index_path = root / "jobs" / "index.json"
            index_path.write_text("not valid JSON", encoding="utf-8")

            rebuilt = rebuild_v4_job_index(root)

            self.assertEqual(rebuilt, {"jobs": ["J001"]})
            self.assertEqual(load_json(index_path), rebuilt)

    def test_derives_ready_jobs_by_priority_and_creation_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001", priority=20, creation_sequence=4),
                self.job_document("J002", priority=50, creation_sequence=3),
                self.job_document("J003", priority=50, creation_sequence=2),
                self.job_document("J004", priority=50, creation_sequence=2),
                self.job_document("J005", priority=100, status="running"),
            ]
            self.write_state(root, jobs)

            state = load_v4_state(root)

            self.assertEqual(
                state["ready_job_ids"], ["J003", "J004", "J002", "J001"]
            )

    def test_only_completed_dependencies_make_a_queued_job_ready(self) -> None:
        non_successful_statuses = [
            "queued",
            "starting",
            "running",
            "waiting_for_input",
            "waiting_for_job",
            "recovering",
            "failed",
            "canceled",
        ]
        for status in non_successful_statuses:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                jobs = [
                    self.job_document("J001", status="completed"),
                    self.job_document("J002", status=status),
                    self.job_document(
                        "J003",
                        depends_on=["J001", "J002"],
                        creation_sequence=3,
                    ),
                ]
                self.write_state(root, jobs)

                state = load_v4_state(root)

                self.assertNotIn("J003", state["ready_job_ids"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001", status="completed"),
                self.job_document("J002", status="completed"),
                self.job_document(
                    "J003", depends_on=["J001", "J002"], creation_sequence=3
                ),
            ]
            self.write_state(root, jobs)

            self.assertIn("J003", load_v4_state(root)["ready_job_ids"])

    def test_does_not_read_authoritative_queue_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001", priority=10),
                self.job_document("J002", priority=20, creation_sequence=2),
            ]
            self.write_state(root, jobs)
            (root / "queue.json").write_text("not valid JSON", encoding="utf-8")

            state = load_v4_state(root)

            self.assertEqual(state["ready_job_ids"], ["J002", "J001"])
            self.assertNotIn("queue", state)

    def test_rejects_invalid_run_and_job_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            run = self.run_document(["J001"])
            run["unexpected"] = True
            write_json(root / "run.json", run)
            with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                load_v4_state(root)

            write_v4_document(root / "run.json", "run", self.run_document(["J001"]))
            job = self.job_document("J001")
            job["unexpected"] = True
            write_json(root / "jobs" / "J001" / "job.json", job)
            with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
                load_v4_state(root)

    def test_rejects_missing_and_unlisted_authoritative_job_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(
                root,
                [self.job_document("J001"), self.job_document("J002")],
                run_job_ids=["J001", "J003"],
            )
            with self.assertRaisesRegex(
                OrchestratorError, "missing job directories: J003; unlisted job directories: J002"
            ):
                load_v4_state(root)

    def test_rejects_duplicate_job_document_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            duplicate = self.job_document("J001")
            write_v4_document(
                root / "jobs" / "ALIAS" / "job.json", "job", duplicate
            )
            run = self.run_document(["J001", "ALIAS"])
            write_v4_document(root / "run.json", "run", run)

            with self.assertRaisesRegex(OrchestratorError, "duplicate authoritative job identity"):
                load_v4_state(root)

    def test_rejects_job_identity_that_disagrees_with_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            mismatched = self.job_document("J002")
            write_json(root / "jobs" / "J001" / "job.json", mismatched)

            with self.assertRaisesRegex(OrchestratorError, "contains identity 'J002'"):
                load_v4_state(root)

    def test_rejects_unsafe_job_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_v4_document(
                root / "run.json", "run", self.run_document(["../J001"])
            )
            (root / "jobs").mkdir()

            with self.assertRaisesRegex(OrchestratorError, "safe authoritative directory"):
                load_v4_state(root)

    def test_rejects_noncanonical_job_artifact_paths(self) -> None:
        fields = {
            "prompt_path": ("jobs/OTHER/prompt.md", "prompt_path"),
            "report_path": ("jobs/OTHER/report.md", "report_path"),
            "checkpoint_path": ("jobs/OTHER/checkpoint.md", "checkpoint_path"),
            "related_reports": (["../J002/report.md"], "related report path"),
        }
        for field, (invalid_value, message) in fields.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                job = self.job_document("J001")
                job[field] = invalid_value
                self.write_state(root, [job])

                with self.assertRaisesRegex(OrchestratorError, message):
                    load_v4_state(root)

    def test_rejects_outcome_report_path_that_is_not_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = self.job_document("J001")
            job["status"] = "completed"
            job["outcome"] = {
                "status": "completed",
                "summary": "Complete.",
                "report_path": "jobs/OTHER/report.md",
            }
            self.write_state(root, [job])

            with self.assertRaisesRegex(OrchestratorError, "outcome report_path"):
                load_v4_state(root)

    def test_rejects_unknown_dependencies_and_parents(self) -> None:
        cases = (
            (self.job_document("J001", depends_on=["UNKNOWN"]), "unknown dependencies"),
            (self.job_document("J001", parent_job_id="UNKNOWN"), "unknown parent"),
        )
        for job, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_state(root, [job])
                with self.assertRaisesRegex(OrchestratorError, message):
                    load_v4_state(root)

    def test_rejects_dependency_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001", depends_on=["J002"]),
                self.job_document("J002", depends_on=["J001"]),
            ]
            self.write_state(root, jobs)

            with self.assertRaisesRegex(OrchestratorError, "dependency cycle"):
                load_v4_state(root)

    def test_rejects_parent_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001", parent_job_id="J002"),
                self.job_document("J002", parent_job_id="J001"),
            ]
            self.write_state(root, jobs)

            with self.assertRaisesRegex(OrchestratorError, "parent cycle"):
                load_v4_state(root)


if __name__ == "__main__":
    unittest.main()
