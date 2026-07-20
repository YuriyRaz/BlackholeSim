from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from jobctl import parser, recover  # noqa: E402
from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    audit_v4_state,
    load_json,
    recover_v4_job_record,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4CorruptionRecoveryTest(unittest.TestCase):
    def job(self, *, revision: int = 1, status: str = "queued") -> dict:
        return {
            "schema_version": 4,
            "id": "J001",
            "title": "Recover corrupted state",
            "status": status,
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

    def write_state(self, root: Path) -> None:
        write_v4_document(root / "run.json", "run", {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-CORRUPTION",
            "goal": "Recover corrupted state",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        })
        write_v4_document(
            root / "jobs" / "J001" / "job.json", "job", self.job()
        )
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Recover the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            "Recovered report.\n", encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def create_previous_version(self, root: Path) -> None:
        write_v4_document(
            root / "jobs" / "J001" / "job.json",
            "job",
            self.job(revision=2, status="starting"),
            transition_path=["starting"],
        )

    def corrupt(self, root: Path) -> bytes:
        malformed = b'{"schema_version":4,"id":"J001","status":"running"'
        (root / "jobs" / "J001" / "job.json").write_bytes(malformed)
        return malformed

    def snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_job_writes_keep_only_the_last_complete_atomic_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            self.create_previous_version(root)

            running = self.job(revision=3, status="running")
            running["session_ref"] = "session-J001"
            write_v4_document(
                root / "jobs" / "J001" / "job.json",
                "job",
                running,
                transition_path=["running"],
            )

            job_root = root / "jobs" / "J001"
            self.assertEqual(load_json(job_root / "job.previous.json")["revision"], 2)
            self.assertEqual(
                [path.name for path in job_root.glob("job.previous*.json")],
                ["job.previous.json"],
            )

    def test_audit_and_recover_plan_are_read_only_and_never_prescribe_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            self.create_previous_version(root)
            self.corrupt(root)
            before = self.snapshot(root)

            audit = audit_v4_state(root)
            plan = recover(parser().parse_args([
                "recover", "--run", str(root), "--job", "J001",
            ]))

            self.assertFalse(audit["ok"])
            self.assertEqual(len(audit["job_record_recovery"]), 1)
            self.assertTrue(
                audit["job_record_recovery"][0]["previous_version"]["restorable"]
            )
            self.assertEqual(plan["classification"], "malformed_job_record")
            self.assertEqual(
                plan["recommended_action"],
                "restore_previous_atomic_version_and_reconcile_facts",
            )
            rendered = json.dumps({"audit": audit, "plan": plan}).lower()
            for prohibited in ("hand-edit", "manual edit", "targeted edit", "append missing"):
                self.assertNotIn(prohibited, rendered)
            self.assertEqual(self.snapshot(root), before)

    def test_apply_preserves_exact_corruption_and_restores_coherent_previous_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            self.create_previous_version(root)
            malformed = self.corrupt(root)

            result = recover_v4_job_record(
                root, "J001", controller="test", apply=True
            )

            self.assertEqual(
                result["classification"], "recovered_previous_atomic_version"
            )
            self.assertTrue(result["quarantined"])
            self.assertTrue(result["record_restored"])
            self.assertEqual(
                (root / result["quarantine_path"]).read_bytes(), malformed
            )
            restored = load_json(root / "jobs" / "J001" / "job.json")
            self.assertEqual(restored["revision"], 1)
            self.assertEqual(restored["status"], "queued")

    def test_recover_can_reconcile_transport_facts_after_restoring_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "run"
            self.write_state(root)
            self.create_previous_version(root)
            malformed = self.corrupt(root)
            evidence_path = base / "evidence.json"
            write_json(evidence_path, {
                "schema_version": 4,
                "job_id": "J001",
                "session_ref": "session-J001",
                "observed_at": NOW,
                "transport": {
                    "observation": "direct",
                    "status": "returned",
                    "response": {
                        "status": "completed",
                        "summary": "Recovered from direct transport facts.",
                        "report_path": "jobs/J001/report.md",
                    },
                },
            })

            result = recover(parser().parse_args([
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
                "--apply",
            ]))

            self.assertTrue(result["record_restored"])
            self.assertEqual(
                result["fact_reconciliation"]["classification"],
                "unrecorded_transport_response",
            )
            self.assertTrue(result["fact_reconciliation"]["recorded"])
            job = load_json(root / "jobs" / "J001" / "job.json")
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["session_ref"], "session-J001")
            self.assertEqual(
                (root / result["quarantine_path"]).read_bytes(), malformed
            )

    def test_invalid_evidence_cannot_mutate_or_quarantine_corrupt_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "run"
            self.write_state(root)
            self.create_previous_version(root)
            self.corrupt(root)
            evidence_path = base / "evidence.json"
            write_json(evidence_path, {
                "schema_version": 4,
                "job_id": "OTHER",
                "observed_at": NOW,
            })
            before = self.snapshot(root)

            with self.assertRaisesRegex(OrchestratorError, "does not match"):
                recover(parser().parse_args([
                    "recover",
                    "--run",
                    str(root),
                    "--job",
                    "J001",
                    "--evidence",
                    str(evidence_path),
                    "--apply",
                ]))

            self.assertEqual(self.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
