from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import jobctl  # noqa: E402
from orchestrator_core import (  # noqa: E402
    OrchestratorError,
    audit_v4_state,
    load_json,
    write_json,
)


JOBCTL = ROOT / "scripts" / "jobctl.py"
NOW = "2026-07-14T12:00:00Z"


class Version4AuditTest(unittest.TestCase):
    def run_document(self, job_ids: list[str]) -> dict:
        return {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-AUDIT",
            "goal": "Audit the run",
            "status": "active",
            "job_ids": job_ids,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }

    def job_document(self, job_id: str, **overrides: object) -> dict:
        job = {
            "schema_version": 4,
            "id": job_id,
            "title": f"Job {job_id}",
            "status": "queued",
            "prompt_path": f"jobs/{job_id}/prompt.md",
            "session_ref": None,
            "priority": 10,
            "creation_sequence": int(job_id[1:]),
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": True,
            "report_path": f"jobs/{job_id}/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": None,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job.update(overrides)
        return job

    def write_state(
        self,
        root: Path,
        jobs: list[dict],
        *,
        write_completed_reports: bool = True,
    ) -> None:
        write_json(root / "run.json", self.run_document([job["id"] for job in jobs]))
        for job in jobs:
            job_root = root / "jobs" / job["id"]
            job_root.mkdir(parents=True)
            write_json(job_root / "job.json", job)
            (job_root / "prompt.md").write_text(
                f"Complete {job['id']}.\n", encoding="utf-8"
            )
            if job["status"] == "completed" and write_completed_reports:
                (job_root / "report.md").write_text("Complete.\n", encoding="utf-8")
        write_json(root / "jobs" / "index.json", {"jobs": sorted(job["id"] for job in jobs)})

    def completed_job(self, job_id: str = "J001") -> dict:
        report_path = f"jobs/{job_id}/report.md"
        return self.job_document(
            job_id,
            status="completed",
            session_ref=f"session-{job_id}",
            outcome={
                "status": "completed",
                "summary": "Complete.",
                "report_path": report_path,
            },
        )

    def snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def transport_evidence(
        self,
        status: str,
        *,
        observation: str = "direct",
        response: dict | None = None,
        cancellation_requested: bool = False,
    ) -> dict:
        transport = {
            "observation": observation,
            "status": status,
            "transcript_ref": "transport://session-J001",
        }
        if response is not None:
            transport["response"] = response
        if cancellation_requested:
            transport["cancellation_requested"] = True
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "session-J001",
            "observed_at": NOW,
            "transport": transport,
        }

    def test_clean_audit_is_read_only_and_uses_v4_cli_handler(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            before = self.snapshot(root)

            result = jobctl.audit(argparse.Namespace(
                run=root,
                rebuild=False,
                rebuild_index=False,
            ))

            self.assertTrue(result["ok"])
            self.assertEqual(result["schema_version"], 4)
            self.assertEqual(result["job_ids"], ["J001"])
            self.assertEqual(result["issues"], [])
            self.assertEqual(self.snapshot(root), before)
            self.assertFalse((root / "events.jsonl").exists())

    def test_audit_reports_run_and_job_schema_failures(self) -> None:
        for document in ("run", "job"):
            with self.subTest(document=document), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_state(root, [self.job_document("J001")])
                path = (
                    root / "run.json"
                    if document == "run"
                    else root / "jobs" / "J001" / "job.json"
                )
                malformed = load_json(path)
                malformed["unexpected"] = True
                write_json(path, malformed)

                result = audit_v4_state(root)

                self.assertFalse(result["ok"])
                self.assertTrue(any("unexpected fields" in issue for issue in result["issues"]))

    def test_audit_reports_noncanonical_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = self.job_document("J001", prompt_path="jobs/OTHER/prompt.md")
            self.write_state(root, [job])

            result = audit_v4_state(root)

            self.assertFalse(result["ok"])
            self.assertTrue(any("prompt_path" in issue for issue in result["issues"]))

    def test_audit_reports_dependency_cycles_and_invalid_parent_links(self) -> None:
        cases = (
            (
                [
                    self.job_document("J001", depends_on=["J002"]),
                    self.job_document("J002", depends_on=["J001"]),
                ],
                "dependency cycle",
            ),
            (
                [self.job_document("J001", parent_job_id="UNKNOWN")],
                "unknown parent",
            ),
            (
                [
                    self.job_document("J001", parent_job_id="J002"),
                    self.job_document("J002", parent_job_id="J001"),
                ],
                "parent cycle",
            ),
        )
        for jobs, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_state(root, jobs)

                result = audit_v4_state(root)

                self.assertFalse(result["ok"])
                self.assertTrue(any(expected in issue for issue in result["issues"]))

    def test_audit_reports_session_question_and_waiting_incoherence(self) -> None:
        cases = (
            (
                [self.job_document("J001", status="running")],
                "requires a session_ref",
            ),
            (
                [self.job_document("J001", session_ref="unexpected")],
                "must not have a session_ref",
            ),
            (
                [
                    self.job_document(
                        "J001",
                        status="waiting_for_input",
                        session_ref="session-J001",
                    )
                ],
                "requires a pending_question",
            ),
            (
                [
                    self.job_document("J001", waiting_on=["J002"]),
                    self.job_document("J002"),
                ],
                "must not have waiting_on jobs",
            ),
            (
                [
                    self.job_document(
                        "J001",
                        status="waiting_for_job",
                        session_ref="session-J001",
                        pending_question={"text": "Need advice?"},
                        outcome={
                            "status": "needs_input",
                            "summary": "Advice required.",
                            "question": "Need advice?",
                        },
                    )
                ],
                "requires waiting_on jobs",
            ),
        )
        for jobs, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_state(root, jobs)

                result = audit_v4_state(root)

                self.assertFalse(result["ok"])
                self.assertTrue(any(expected in issue for issue in result["issues"]))

    def test_audit_requires_terminal_report_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(
                root,
                [self.completed_job()],
                write_completed_reports=False,
            )

            result = audit_v4_state(root)

            self.assertFalse(result["ok"])
            self.assertTrue(any("accessible non-empty report" in issue for issue in result["issues"]))

    def test_optional_checkpoints_may_be_absent_or_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs = [
                self.job_document("J001"),
                self.job_document(
                    "J002", checkpoint_path="jobs/J002/checkpoint.md"
                ),
                self.job_document(
                    "J003", checkpoint_path="jobs/J003/checkpoint.md"
                ),
            ]
            self.write_state(root, jobs)
            (root / "jobs" / "J003" / "checkpoint.md").write_text(
                "Current progress.\n", encoding="utf-8"
            )

            result = audit_v4_state(root)

            self.assertTrue(result["ok"], result["issues"])
            self.assertEqual(result["checkpoints"], [
                {"job_id": "J001", "path": None, "present": False},
                {
                    "job_id": "J002",
                    "path": "jobs/J002/checkpoint.md",
                    "present": False,
                },
                {
                    "job_id": "J003",
                    "path": "jobs/J003/checkpoint.md",
                    "present": True,
                },
            ])

    def test_stale_index_is_read_only_until_explicit_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            index_path = root / "jobs" / "index.json"
            write_json(index_path, {"jobs": ["STALE"]})
            before = self.snapshot(root)

            report = audit_v4_state(root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["index"]["agrees"])
            self.assertFalse(report["index"]["rebuilt"])
            self.assertEqual(self.snapshot(root), before)

            rebuilt = audit_v4_state(root, rebuild_index=True)

            self.assertTrue(rebuilt["ok"], rebuilt["issues"])
            self.assertTrue(rebuilt["index"]["agrees"])
            self.assertTrue(rebuilt["index"]["rebuilt"])
            self.assertEqual(load_json(index_path), {"jobs": ["J001"]})
            after = self.snapshot(root)
            self.assertEqual(
                {path: data for path, data in after.items() if path != "jobs/index.json"},
                {path: data for path, data in before.items() if path != "jobs/index.json"},
            )

    def test_audit_reports_abandoned_authoritative_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            run_temp = root / ".run.json.abandoned"
            job_temp = root / "jobs" / "J001" / ".job.json.abandoned"
            run_temp.write_text("partial", encoding="utf-8")
            job_temp.write_text("partial", encoding="utf-8")

            result = audit_v4_state(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["abandoned_temporary_files"], [
                ".run.json.abandoned",
                "jobs/J001/.job.json.abandoned",
            ])

    def test_transport_liveness_evidence_is_reported_ephemerally(self) -> None:
        cases = (
            ("active", "active_session", False, "none"),
            ("available", "available_session", False, "none"),
            ("returned", "returned_session", True, "retrieve_transport_response"),
            ("canceled", "confirmed_cancellation", True, "recover_canceled_job"),
            (
                "lost",
                "confirmed_session_unavailable",
                True,
                "recover_unavailable_job",
            ),
            (
                "unavailable",
                "confirmed_session_unavailable",
                True,
                "recover_unavailable_job",
            ),
        )
        for status, classification, required, action in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_state(root, [self.job_document(
                    "J001", status="running", session_ref="session-J001"
                )])
                before = self.snapshot(root)

                result = audit_v4_state(
                    root, evidence=self.transport_evidence(status)
                )

                report = result["transport_evidence"]
                self.assertEqual(report["classification"], classification)
                self.assertEqual(report["reconciliation_required"], required)
                self.assertEqual(report["recommended_action"], action)
                self.assertEqual(
                    report["turn_state"],
                    "completed" if status == "returned" else status,
                )
                self.assertEqual(self.snapshot(root), before)
                self.assertFalse(any(
                    "transcript" in path.lower() or "delivery" in path.lower()
                    for path in self.snapshot(root)
                ))

    def test_transport_response_is_reported_but_not_recorded_or_copied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document(
                "J001", status="running", session_ref="session-J001"
            )])
            before = self.snapshot(root)
            response = {
                "status": "completed",
                "summary": "Sensitive authoritative transport response.",
                "report_path": "jobs/J001/report.md",
            }

            result = audit_v4_state(
                root,
                evidence=self.transport_evidence("returned", response=response),
            )

            report = result["transport_evidence"]
            self.assertEqual(
                report["classification"], "unrecorded_transport_response"
            )
            self.assertEqual(report["response_status"], "completed")
            self.assertEqual(
                report["recommended_action"], "record_response_with_jobctl_outcome"
            )
            self.assertNotIn(response["summary"], json.dumps(result))
            self.assertEqual(self.snapshot(root), before)
            self.assertIsNone(load_json(root / "jobs" / "J001" / "job.json")["outcome"])

    def test_unknown_transport_results_do_not_imply_loss_or_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document(
                "J001", status="running", session_ref="session-J001"
            )])
            evidence = self.transport_evidence(
                "unknown",
                observation="unsupported",
                cancellation_requested=True,
            )

            report = audit_v4_state(root, evidence=evidence)["transport_evidence"]

            self.assertEqual(report["classification"], "insufficient_transport_evidence")
            self.assertEqual(
                report["recommended_action"], "confirm_cancellation_or_liveness"
            )
            self.assertNotIn("canceled", report["classification"])
            self.assertNotIn("lost", report["classification"])

    def test_transport_evidence_rejects_invalid_semantics_and_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document(
                "J001", status="running", session_ref="session-J001"
            )])
            before = self.snapshot(root)
            cases = (
                (
                    self.transport_evidence("lost", observation="unknown"),
                    "must use status 'unknown'",
                ),
                (
                    self.transport_evidence(
                        "active",
                        response={"status": "completed", "summary": "Complete."},
                    ),
                    "requires a direct 'returned' observation",
                ),
                (
                    {**self.transport_evidence("active"), "session_ref": "other"},
                    "session_ref does not match",
                ),
                (
                    {**self.transport_evidence("active"), "job_id": "UNKNOWN"},
                    "unknown job",
                ),
            )
            for evidence, expected in cases:
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(OrchestratorError, expected):
                        audit_v4_state(root, evidence=evidence)
                    self.assertEqual(self.snapshot(root), before)

    def test_transport_evidence_contradiction_marks_audit_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.completed_job()])

            result = audit_v4_state(
                root, evidence=self.transport_evidence("active")
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["transport_evidence"]["contradictions"])
            self.assertTrue(any("active turn" in issue for issue in result["issues"]))

    def test_cli_documents_and_enforces_index_only_rebuild(self) -> None:
        help_process = subprocess.run(
            [sys.executable, str(JOBCTL), "audit", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_process.returncode, 0, help_process.stderr)
        self.assertIn("--evidence", help_process.stdout)
        self.assertIn("--rebuild-index", help_process.stdout)
        self.assertIn("rebuild only the derived version-4", help_process.stdout)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_state(root, [self.job_document("J001")])
            write_json(root / "jobs" / "index.json", {"jobs": ["STALE"]})

            rebuilt = subprocess.run(
                [
                    sys.executable,
                    str(JOBCTL),
                    "audit",
                    "--run",
                    str(root),
                    "--rebuild-index",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr or rebuilt.stdout)
            self.assertTrue(json.loads(rebuilt.stdout)["index"]["rebuilt"])


    def test_cli_evidence_is_validated_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "run"
            self.write_state(root, [self.job_document(
                "J001", status="running", session_ref="session-J001"
            )])
            valid_path = base / "valid-evidence.json"
            valid_path.write_text(
                json.dumps(self.transport_evidence("active")), encoding="utf-8"
            )
            before = self.snapshot(root)

            valid = subprocess.run(
                [
                    sys.executable,
                    str(JOBCTL),
                    "audit",
                    "--run",
                    str(root),
                    "--evidence",
                    str(valid_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(valid.returncode, 0, valid.stderr or valid.stdout)
            self.assertEqual(
                json.loads(valid.stdout)["transport_evidence"]["classification"],
                "active_session",
            )
            self.assertEqual(self.snapshot(root), before)

            invalid_path = base / "invalid-evidence.json"
            invalid_path.write_text(json.dumps({
                "schema_version": 4,
                "job_id": "J001",
                "observed_at": NOW,
                "transport": {"observation": "direct", "status": "silent"},
            }), encoding="utf-8")
            invalid = subprocess.run(
                [
                    sys.executable,
                    str(JOBCTL),
                    "audit",
                    "--run",
                    str(root),
                    "--evidence",
                    str(invalid_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("must be one of", json.loads(invalid.stdout)["error"])
            self.assertEqual(self.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
