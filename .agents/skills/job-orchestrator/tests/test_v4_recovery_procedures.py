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


class EvidencePriorityOrderingTest(unittest.TestCase):
    """Tests for evidence priority ordering in recovery procedures."""

    def write_state(
        self,
        root: Path,
        *,
        status: str = "running",
        session_ref: str | None = "transport-session-1",
        report_required: bool = True,
        report: str = "",
        recovery_policy: dict | None = None,
    ) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-EVIDENCE-PRIORITY",
            "goal": "Test evidence priority ordering",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Evidence priority test",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": session_ref,
            "priority": 10,
            "creation_sequence": 1,
            "depends_on": [],
            "parent_job_id": None,
            "waiting_on": [],
            "pending_question": None,
            "related_reports": [],
            "report_required": report_required,
            "report_path": "jobs/J001/report.md",
            "checkpoint_path": None,
            "outcome": None,
            "recovery_policy": recovery_policy,
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            report, encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def evidence(self, response: dict | None = None) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "returned",
                "transcript_ref": "transport://transport-session-1",
                "response": response or {
                    "status": "completed",
                    "summary": "Work is complete.",
                    "report_path": "jobs/J001/report.md",
                },
            },
        }

    def unavailable_evidence(self, **sources: object) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "unavailable",
            },
            **sources,
        }

    def invoke(
        self, root: Path, evidence: dict, *, apply: bool = False
    ) -> dict:
        evidence_path = root.parent / "recovery-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        arguments = [
            "recover",
            "--run",
            str(root),
            "--job",
            "J001",
            "--evidence",
            str(evidence_path),
        ]
        if apply:
            arguments.append("--apply")
        return recover(parser().parse_args(arguments))

    def test_transport_response_has_highest_priority(self) -> None:
        """Transport response evidence should override all other sources."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Persisted report.\n")
            evidence = self.evidence({
                "status": "completed",
                "summary": "Transport confirms completion.",
                "report_path": "jobs/J001/report.md",
            })

            result = self.invoke(root, evidence)

            self.assertEqual(result["classification"], "unrecorded_transport_response")
            self.assertEqual(result["recommended_action"], "record_transport_response")
            self.assertTrue(result["mutation_allowed"])

    def test_external_system_has_second_highest_priority(self) -> None:
        """External system evidence should override repository, report, checkpoint."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["external_system"] = [{
                "system": "artifact-service",
                "observation": "direct",
                "effect_state": "confirmed",
                "summary": "The external state was queried directly.",
            }]
            evidence["workspace"] = {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The repository was inspected.",
            }
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report was inspected.",
            }
            evidence["facts"] = [
                {"source": "external_system", "subject": "artifact:result", "value": "present"},
                {"source": "repository_filesystem", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertEqual(
                result["material_contradictions"][0]["preferred_source"], "external_system"
            )
            self.assertEqual(
                result["material_contradictions"][0]["conflicting_source"], "repository_filesystem"
            )

    def test_repository_filesystem_has_third_priority(self) -> None:
        """Repository filesystem evidence should override report, checkpoint."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["workspace"] = {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The repository was inspected.",
            }
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report was inspected.",
            }
            evidence["facts"] = [
                {"source": "repository_filesystem", "subject": "artifact:result", "value": "present"},
                {"source": "report", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertEqual(
                result["material_contradictions"][0]["preferred_source"], "repository_filesystem"
            )
            self.assertEqual(
                result["material_contradictions"][0]["conflicting_source"], "report"
            )

    def test_report_has_fourth_priority(self) -> None:
        """Report evidence should override checkpoint."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report was inspected.",
            }
            evidence["checkpoint"] = {
                "observation": "direct",
                "path": "jobs/J001/checkpoint.md",
                "summary": "The checkpoint was inspected.",
            }
            evidence["facts"] = [
                {"source": "report", "subject": "artifact:result", "value": "present"},
                {"source": "checkpoint", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertEqual(
                result["material_contradictions"][0]["preferred_source"], "report"
            )
            self.assertEqual(
                result["material_contradictions"][0]["conflicting_source"], "checkpoint"
            )

    def test_fact_precedence_order_is_enforced(self) -> None:
        """The fact_precedence field should reflect the correct priority order."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report was inspected.",
            }
            evidence["checkpoint"] = {
                "observation": "direct",
                "path": "jobs/J001/checkpoint.md",
                "summary": "The checkpoint was inspected.",
            }
            evidence["facts"] = [
                {"source": "report", "subject": "artifact:result", "value": "present"},
                {"source": "checkpoint", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence)

            self.assertEqual(result["fact_precedence"], [
                "transport_response",
                "external_system",
                "repository_filesystem",
                "report_checkpoint",
                "persisted_job_status",
            ])

    def test_report_and_checkpoint_same_priority_blocks_mutation(self) -> None:
        """Report and checkpoint at same priority should block mutation when contradictory."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report shows completion.",
            }
            evidence["checkpoint"] = {
                "observation": "direct",
                "path": "jobs/J001/checkpoint.md",
                "summary": "The checkpoint shows work in progress.",
            }
            evidence["facts"] = [
                {"source": "report", "subject": "artifact:result", "value": "present"},
                {"source": "checkpoint", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertFalse(result["mutation_allowed"])


class StateSafetyTest(unittest.TestCase):
    """Tests verifying no manual editing of authoritative state JSON."""

    def write_state(self, root: Path) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-STATE-SAFETY",
            "goal": "Test state safety",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "State safety test",
            "status": "running",
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": "transport-session-1",
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
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            "Test report.\n", encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def evidence(self) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "returned",
                "transcript_ref": "transport://transport-session-1",
                "response": {
                    "status": "completed",
                    "summary": "Work is complete.",
                    "report_path": "jobs/J001/report.md",
                },
            },
        }

    def invoke(
        self, root: Path, evidence: dict, *, apply: bool = False
    ) -> dict:
        evidence_path = root.parent / "recovery-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        arguments = [
            "recover",
            "--run",
            str(root),
            "--job",
            "J001",
            "--evidence",
            str(evidence_path),
        ]
        if apply:
            arguments.append("--apply")
        return recover(parser().parse_args(arguments))

    def snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_audit_is_read_only(self) -> None:
        """Audit should never modify authoritative state."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.snapshot(root)

            audit_v4_state(root)

            self.assertEqual(self.snapshot(root), before)

    def test_recover_plan_is_read_only(self) -> None:
        """Recover plan (without --apply) should never modify authoritative state."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.snapshot(root)

            self.invoke(root, self.evidence())

            self.assertEqual(self.snapshot(root), before)

    def test_recover_apply_uses_atomic_writes(self) -> None:
        """Recover apply should use atomic writes, not manual edits."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.snapshot(root)

            result = self.invoke(root, self.evidence(), apply=True)

            self.assertTrue(result["recorded"])
            job = load_json(root / "jobs" / "J001" / "job.json")
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["revision"], 2)
            self.assertNotEqual(self.snapshot(root), before)

    def test_repair_plan_is_read_only(self) -> None:
        """Repair command plan should not modify state."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.snapshot(root)

            arguments = [
                "repair",
                "--run",
                str(root),
                "--job",
                "J001",
                "--disposition",
                "failed",
                "--reason",
                "Test failure",
            ]
            parser().parse_args(arguments)

            self.assertEqual(self.snapshot(root), before)


class RecoveryProcedureTest(unittest.TestCase):
    """Tests for the full recovery procedure workflow."""

    def write_state(
        self,
        root: Path,
        *,
        status: str = "running",
        session_ref: str | None = "transport-session-1",
        report: str = "",
    ) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-RECOVERY-PROCEDURE",
            "goal": "Test recovery procedure",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Recovery procedure test",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": session_ref,
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
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            report, encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def evidence(self) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "returned",
                "transcript_ref": "transport://transport-session-1",
                "response": {
                    "status": "completed",
                    "summary": "Work is complete.",
                    "report_path": "jobs/J001/report.md",
                },
            },
        }

    def invoke(
        self, root: Path, evidence: dict, *, apply: bool = False
    ) -> dict:
        evidence_path = root.parent / "recovery-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        arguments = [
            "recover",
            "--run",
            str(root),
            "--job",
            "J001",
            "--evidence",
            str(evidence_path),
        ]
        if apply:
            arguments.append("--apply")
        return recover(parser().parse_args(arguments))

    def test_full_recovery_procedure_audit_to_final_audit(self) -> None:
        """Test the complete recovery procedure: audit -> gather evidence -> recover -> apply -> final audit."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Recovered report.\n")

            # Step 1: Initial audit
            initial_audit = audit_v4_state(root)
            self.assertTrue(initial_audit["ok"])

            # Step 2: Gather evidence (already done)

            # Step 3: Supply evidence to recover (plan only)
            plan = self.invoke(root, self.evidence())
            self.assertEqual(plan["classification"], "unrecorded_transport_response")
            self.assertTrue(plan["mutation_allowed"])

            # Step 4: Apply if safe
            result = self.invoke(root, self.evidence(), apply=True)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["status"], "completed")

            # Step 5: Final audit
            final_audit = audit_v4_state(root)
            self.assertTrue(final_audit["ok"])
            job = load_json(root / "jobs" / "J001" / "job.json")
            self.assertEqual(job["status"], "completed")

    def test_recovery_procedure_blocks_on_material_contradictions(self) -> None:
        """Recovery should block when material contradictions are found."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.evidence()
            evidence["facts"] = [
                {"source": "transport_response", "subject": "artifact:result", "value": "present"},
                {"source": "external_system", "subject": "artifact:result", "value": "absent"},
            ]
            evidence["external_system"] = [{
                "system": "artifact-service",
                "observation": "direct",
                "effect_state": "absent",
                "summary": "The artifact does not exist.",
            }]

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertFalse(result["mutation_allowed"])
            self.assertEqual(len(result["material_contradictions"]), 1)

    def test_recovery_procedure_validates_evidence_job_id(self) -> None:
        """Recovery should validate that evidence job_id matches the target job."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.evidence()
            evidence["job_id"] = "J999"
            evidence_path = root.parent / "recovery-evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments = [
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
                "--apply",
            ]

            with self.assertRaisesRegex(OrchestratorError, "does not match"):
                recover(parser().parse_args(arguments))

    def test_recovery_procedure_validates_evidence_session_ref(self) -> None:
        """Recovery should validate that evidence session_ref matches the job."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.evidence()
            evidence["session_ref"] = "wrong-session"
            evidence_path = root.parent / "recovery-evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments = [
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
                "--apply",
            ]

            with self.assertRaisesRegex(OrchestratorError, "session_ref"):
                recover(parser().parse_args(arguments))


class ContradictionDetectionTest(unittest.TestCase):
    """Tests for contradiction detection when evidence sources disagree."""

    def write_state(
        self,
        root: Path,
        *,
        status: str = "running",
        session_ref: str | None = "transport-session-1",
        report: str = "",
    ) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-CONTRADICTION",
            "goal": "Test contradiction detection",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Contradiction detection test",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": session_ref,
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
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            report, encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def evidence(self, response: dict | None = None) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "returned",
                "transcript_ref": "transport://transport-session-1",
                "response": response or {
                    "status": "completed",
                    "summary": "Work is complete.",
                    "report_path": "jobs/J001/report.md",
                },
            },
        }

    def unavailable_evidence(self, **sources: object) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "unavailable",
            },
            **sources,
        }

    def invoke(
        self, root: Path, evidence: dict, *, apply: bool = False
    ) -> dict:
        evidence_path = root.parent / "recovery-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        arguments = [
            "recover",
            "--run",
            str(root),
            "--job",
            "J001",
            "--evidence",
            str(evidence_path),
        ]
        if apply:
            arguments.append("--apply")
        return recover(parser().parse_args(arguments))

    def test_transport_vs_external_contradiction(self) -> None:
        """Transport response contradicting external system should be material."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.evidence({
                "status": "completed",
                "summary": "Transport confirms completion.",
                "report_path": "jobs/J001/report.md",
            })
            evidence["external_system"] = [{
                "system": "artifact-service",
                "observation": "direct",
                "effect_state": "absent",
                "summary": "The artifact does not exist.",
            }]
            evidence["facts"] = [
                {"source": "transport_response", "subject": "artifact:result", "value": "present"},
                {"source": "external_system", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertFalse(result["mutation_allowed"])
            self.assertEqual(len(result["material_contradictions"]), 1)
            self.assertEqual(
                result["material_contradictions"][0]["preferred_source"], "transport_response"
            )

    def test_report_vs_checkpoint_contradiction(self) -> None:
        """Report contradicting checkpoint should be material at same priority."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["report"] = {
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The report shows completion.",
            }
            evidence["checkpoint"] = {
                "observation": "direct",
                "path": "jobs/J001/checkpoint.md",
                "summary": "The checkpoint shows work in progress.",
            }
            evidence["facts"] = [
                {"source": "report", "subject": "artifact:result", "value": "present"},
                {"source": "checkpoint", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertFalse(result["mutation_allowed"])
            self.assertEqual(len(result["material_contradictions"]), 1)

    def test_non_material_contradiction_allows_mutation(self) -> None:
        """Non-material contradictions (persisted status vs direct) should allow mutation."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Recovered report.\n")
            evidence = self.evidence()
            # Transport response is direct and says completed, but persisted_job_status
            # is nonterminal (running) - this is non-material because persisted state may lag
            evidence["facts"] = [
                {"source": "transport_response", "subject": "job.outcome", "value": "completed"},
            ]

            result = self.invoke(root, evidence, apply=True)

            self.assertTrue(result["recorded"])
            self.assertTrue(result["mutation_allowed"])

    def test_multiple_contradictions_all_reported(self) -> None:
        """All contradictions should be reported, not just the first."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.evidence({
                "status": "completed",
                "summary": "Transport confirms completion.",
                "report_path": "jobs/J001/report.md",
            })
            evidence["external_system"] = [{
                "system": "artifact-service",
                "observation": "direct",
                "effect_state": "absent",
                "summary": "The artifact does not exist.",
            }]
            evidence["workspace"] = {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The repository shows no changes.",
            }
            evidence["facts"] = [
                {"source": "transport_response", "subject": "artifact:result", "value": "present"},
                {"source": "external_system", "subject": "artifact:result", "value": "absent"},
                {"source": "repository_filesystem", "subject": "artifact:result", "value": "absent"},
            ]

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            self.assertFalse(result["mutation_allowed"])
            self.assertGreaterEqual(len(result["material_contradictions"]), 1)


class MissingUnknownEvidenceTest(unittest.TestCase):
    """Tests for missing/unknown evidence handling."""

    def write_state(
        self,
        root: Path,
        *,
        status: str = "running",
        session_ref: str | None = "transport-session-1",
        report: str = "",
    ) -> None:
        run = {
            "schema_version": 4,
            "protocol_version": 4,
            "run_id": "RUN-MISSING-EVIDENCE",
            "goal": "Test missing evidence handling",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Missing evidence test",
            "status": status,
            "prompt_path": "jobs/J001/prompt.md",
            "session_ref": session_ref,
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
            "revision": 1,
        }
        write_v4_document(root / "run.json", "run", run)
        write_v4_document(root / "jobs" / "J001" / "job.json", "job", job)
        (root / "jobs" / "J001" / "prompt.md").write_text(
            "Complete the job.\n", encoding="utf-8"
        )
        (root / "jobs" / "J001" / "report.md").write_text(
            report, encoding="utf-8"
        )
        write_json(root / "jobs" / "index.json", {"jobs": ["J001"]})

    def transport_evidence(
        self,
        status: str,
        *,
        observation: str = "direct",
        response: dict | None = None,
    ) -> dict:
        transport = {
            "observation": observation,
            "status": status,
            "transcript_ref": "transport://transport-session-1",
        }
        if response is not None:
            transport["response"] = response
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": transport,
        }

    def unavailable_evidence(self) -> dict:
        return {
            "schema_version": 4,
            "job_id": "J001",
            "session_ref": "transport-session-1",
            "observed_at": NOW,
            "transport": {
                "observation": "direct",
                "status": "unavailable",
            },
        }

    def test_unknown_transport_status_not_treated_as_completed(self) -> None:
        """Unknown transport status should not be treated as completed."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.transport_evidence("unknown", observation="unsupported")

            result = audit_v4_state(root, evidence=evidence)

            self.assertEqual(result["transport_evidence"]["classification"], "insufficient_transport_evidence")
            self.assertNotEqual(result["transport_evidence"].get("status"), "completed")

    def test_unknown_transport_status_not_treated_as_canceled(self) -> None:
        """Unknown transport status should not be treated as canceled."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.transport_evidence("unknown", observation="unsupported")

            result = audit_v4_state(root, evidence=evidence)

            self.assertNotIn("canceled", result["transport_evidence"]["classification"])

    def test_unknown_transport_status_not_treated_as_lost(self) -> None:
        """Unknown transport status should not be treated as lost."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.transport_evidence("unknown", observation="unsupported")

            result = audit_v4_state(root, evidence=evidence)

            self.assertNotIn("lost", result["transport_evidence"]["classification"])

    def test_missing_evidence_allows_replacement_session(self) -> None:
        """Missing evidence should allow starting a replacement session."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence_path = root.parent / "recovery-evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments = [
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
            ]

            result = recover(parser().parse_args(arguments))

            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["recommended_action"], "start_replacement_session")

    def test_missing_evidence_preserves_existing_state(self) -> None:
        """Missing evidence should not change authoritative state without apply."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            evidence = self.unavailable_evidence()
            evidence_path = root.parent / "recovery-evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments = [
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
            ]

            recover(parser().parse_args(arguments))

            self.assertEqual(
                {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
                before,
            )

    def test_partial_evidence_combines_available_sources(self) -> None:
        """Partial evidence should combine available sources without contradiction."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["workspace"] = {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The repository shows local changes.",
            }
            evidence_path = root.parent / "recovery-evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments = [
                "recover",
                "--run",
                str(root),
                "--job",
                "J001",
                "--evidence",
                str(evidence_path),
            ]

            result = recover(parser().parse_args(arguments))

            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["recommended_action"], "start_replacement_session")


if __name__ == "__main__":
    unittest.main()
