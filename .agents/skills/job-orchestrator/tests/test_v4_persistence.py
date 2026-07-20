from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    find_v4_temporary_files,
    load_json,
    rebuild_v4_job_index,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4PersistenceTest(unittest.TestCase):
    def run_document(self, revision: int = 1) -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-1",
            "goal": "Complete the request",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": revision,
        }

    def job_document(self, revision: int = 1) -> dict:
        return {
            "schema_version": 4,
            "id": "J001",
            "title": "Apply the change",
            "status": "queued",
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": 1,
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": True,
            "report_path": "jobs/J001/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": revision,
        }

    def test_writes_authoritative_run_and_job_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path = root / "run.json"
            job_path = root / "jobs" / "J001" / "job.json"

            write_v4_document(run_path, "run", self.run_document())
            write_v4_document(job_path, "job", self.job_document())

            self.assertEqual(load_json(run_path), self.run_document())
            self.assertEqual(load_json(job_path), self.job_document())
            self.assertEqual(find_v4_temporary_files(root), [])

    def test_flush_failure_preserves_previous_document_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path = root / "run.json"
            original = self.run_document()
            write_v4_document(run_path, "run", original)

            with (
                patch("orchestrator_core.os.fsync", side_effect=OSError("flush failed")),
                patch("orchestrator_core.os.replace") as replace,
            ):
                with self.assertRaisesRegex(OSError, "flush failed"):
                    write_v4_document(run_path, "run", self.run_document(revision=2))

            replace.assert_not_called()
            self.assertEqual(load_json(run_path), original)
            self.assertEqual(find_v4_temporary_files(root), [])

    def test_replace_failure_preserves_previous_document_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job_path = root / "jobs" / "J001" / "job.json"
            original = self.job_document()
            write_v4_document(job_path, "job", original)

            with patch("orchestrator_core.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_v4_document(job_path, "job", self.job_document(revision=2))

            self.assertEqual(load_json(job_path), original)
            self.assertEqual(find_v4_temporary_files(root), [])

    def test_index_rebuild_is_atomic_and_cleans_temp_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_v4_document(root / "run.json", "run", self.run_document())
            write_v4_document(
                root / "jobs" / "J001" / "job.json", "job", self.job_document()
            )
            index_path = root / "jobs" / "index.json"
            original = {"jobs": ["STALE"]}
            write_json(index_path, original)

            with patch("orchestrator_core.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    rebuild_v4_job_index(root)

            self.assertEqual(load_json(index_path), original)
            self.assertEqual(list(index_path.parent.glob(".index.json.*")), [])

    def test_reports_only_v4_authoritative_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job_root = root / "jobs" / "J001"
            job_root.mkdir(parents=True)
            run_temp = root / ".run.json.abandoned"
            job_temp = job_root / ".job.json.abandoned"
            run_temp.write_bytes(b"partial run")
            job_temp.write_bytes(b"partial job")
            (root / "jobs" / ".index.json.unrelated").write_bytes(b"ignored")
            (job_root / ".report.md.unrelated").write_bytes(b"ignored")

            self.assertEqual(
                find_v4_temporary_files(root),
                sorted([run_temp, job_temp], key=lambda path: path.as_posix()),
            )


if __name__ == "__main__":
    unittest.main()
