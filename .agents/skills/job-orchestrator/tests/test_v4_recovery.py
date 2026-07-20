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
    load_json,
    write_json,
    write_v4_document,
)


NOW = "2026-07-14T12:00:00Z"


class Version4RecoveryReconciliationTest(unittest.TestCase):
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
            "run_id": "RUN-RECOVERY",
            "goal": "Reconcile completed transport work",
            "status": "active",
            "job_ids": ["J001"],
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        }
        job = {
            "schema_version": 4,
            "id": "J001",
            "title": "Recover the completed response",
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
                    "summary": "  Recovered work is complete.  ",
                    "report_path": "jobs/J001/report.md",
                },
            },
        }

    def session_evidence(self, status: str) -> dict:
        evidence = self.evidence()
        evidence["transport"] = {
            "observation": "direct",
            "status": status,
            "transcript_ref": "transport://transport-session-1",
        }
        return evidence

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

    def external_recovery_policy(self) -> dict:
        return {
            "effect": "external_non_idempotent",
            "check": "Query whether release 2.4.0 already exists.",
        }

    def recovery_check(self, result: str) -> dict:
        summaries = {
            "positive": "Release 2.4.0 exists in the provider.",
            "negative": "Release 2.4.0 does not exist in the provider.",
            "unknown": "The provider cannot determine whether release 2.4.0 exists.",
        }
        return {
            "check": "Query whether release 2.4.0 already exists.",
            "result": result,
            "summary": summaries[result],
            "reference": "release-service://releases/2.4.0",
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

    def authoritative_bytes(self, root: Path) -> dict[str, bytes]:
        return {
            path: (root / path).read_bytes()
            for path in ("run.json", "jobs/J001/job.json")
        }

    def add_direct_fact_source(self, evidence: dict, source: str) -> None:
        if source == "external_system":
            evidence["external_system"] = [{
                "system": "artifact-service",
                "observation": "direct",
                "effect_state": "confirmed",
                "summary": "The external state was queried directly.",
            }]
        elif source == "repository_filesystem":
            evidence["workspace"] = {
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The repository and filesystem were inspected directly.",
            }
        elif source in {"report", "checkpoint"}:
            evidence[source] = {
                "observation": "direct",
                "path": f"jobs/J001/{source}.md",
                "summary": f"The {source} was inspected directly.",
            }

    def mark_completed(self, root: Path) -> None:
        job = load_json(root / "jobs" / "J001" / "job.json")
        job.update({
            "status": "completed",
            "outcome": {
                "status": "completed",
                "summary": "Persisted completion.",
                "report_path": "jobs/J001/report.md",
            },
        })
        run = load_json(root / "run.json")
        run["status"] = "completed"
        write_json(root / "jobs" / "J001" / "job.json", job)
        write_json(root / "run.json", run)

    def test_default_plan_validates_response_and_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Recovered report.\n")
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            result = self.invoke(root, self.evidence())

            self.assertEqual(result["classification"], "unrecorded_transport_response")
            self.assertFalse(result["apply"])
            self.assertEqual(result["recommended_action"], "record_transport_response")
            self.assertTrue(result["mutation_allowed"])
            self.assertEqual(result["material_contradictions"], [])
            self.assertEqual(result["contradictions"][0]["conflicting_source"],
                             "persisted_job_status")
            self.assertFalse(result["contradictions"][0]["material"])
            self.assertEqual(
                {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
                before,
            )

    def test_material_contradictions_block_apply_across_every_precedence_pair(self) -> None:
        sources = [
            "transport_response",
            "external_system",
            "repository_filesystem",
            "report",
            "persisted_job_status",
        ]
        expected_precedence = [
            "transport_response",
            "external_system",
            "repository_filesystem",
            "report_checkpoint",
            "persisted_job_status",
        ]
        for higher_index, higher in enumerate(sources[:-1]):
            for lower in sources[higher_index + 1:]:
                with self.subTest(higher=higher, lower=lower):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary) / "run"
                        self.write_state(root, report="Persisted report.\n")
                        includes_persisted = lower == "persisted_job_status"
                        if includes_persisted:
                            self.mark_completed(root)

                        if higher == "transport_response":
                            response = {
                                "status": "failed" if includes_persisted else "completed",
                                "summary": "Direct transport result.",
                            }
                            evidence = self.evidence(response)
                        else:
                            evidence = self.unavailable_evidence()

                        for source in (higher, lower):
                            if source not in {
                                "transport_response", "persisted_job_status"
                            }:
                                self.add_direct_fact_source(evidence, source)

                        subject = "job.outcome" if includes_persisted else "artifact:result"
                        evidence["facts"] = [{
                            "source": higher,
                            "subject": subject,
                            "value": "failed" if includes_persisted else "present",
                        }]
                        if not includes_persisted:
                            evidence["facts"].append({
                                "source": lower,
                                "subject": subject,
                                "value": "absent",
                            })
                        before = self.authoritative_bytes(root)

                        result = self.invoke(root, evidence, apply=True)

                        self.assertEqual(
                            result["classification"],
                            "contradictory_recovery_evidence",
                        )
                        self.assertEqual(result["fact_precedence"], expected_precedence)
                        self.assertEqual(
                            result["material_contradictions"][0]["preferred_source"],
                            higher,
                        )
                        self.assertEqual(
                            result["material_contradictions"][0]["conflicting_source"],
                            lower,
                        )
                        self.assertFalse(result["mutation_allowed"])
                        self.assertFalse(result["replacement_allowed"])
                        self.assertFalse(result["state_changed"])
                        self.assertEqual(self.authoritative_bytes(root), before)

    def test_report_and_checkpoint_disagreement_is_material_without_tie_breaking_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Current report.\n")
            (root / "jobs" / "J001" / "checkpoint.md").write_text(
                "Current checkpoint.\n", encoding="utf-8"
            )
            evidence = self.unavailable_evidence()
            self.add_direct_fact_source(evidence, "report")
            self.add_direct_fact_source(evidence, "checkpoint")
            evidence["facts"] = [
                {"source": "report", "subject": "artifact:result", "value": "present"},
                {"source": "checkpoint", "subject": "artifact:result", "value": "absent"},
            ]
            before = self.authoritative_bytes(root)

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "contradictory_recovery_evidence")
            contradiction = result["material_contradictions"][0]
            self.assertEqual(
                {contradiction["preferred_source"], contradiction["conflicting_source"]},
                {"report", "checkpoint"},
            )
            self.assertFalse(result["mutation_allowed"])
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_apply_records_normalized_outcome_without_persisting_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Recovered report.\n")

            result = self.invoke(root, self.evidence(), apply=True)
            job = load_json(root / "jobs" / "J001" / "job.json")
            run = load_json(root / "run.json")

            self.assertTrue(result["recorded"])
            self.assertEqual(result["status"], "completed")
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["revision"], 2)
            self.assertEqual(job["outcome"], {
                "status": "completed",
                "summary": "Recovered work is complete.",
                "report_path": "jobs/J001/report.md",
            })
            self.assertEqual(run["status"], "completed")
            persisted = b"\n".join(
                path.read_bytes() for path in root.rglob("*") if path.is_file()
            )
            self.assertNotIn(b"transport://transport-session-1", persisted)
            self.assertFalse(any(
                "transcript" in path.name.lower() or "delivery" in path.name.lower()
                for path in root.rglob("*")
            ))

    def test_required_report_failure_does_not_partially_record_session_or_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(
                root,
                status="starting",
                session_ref=None,
                report_required=True,
            )
            before = self.authoritative_bytes(root)

            with self.assertRaisesRegex(
                OrchestratorError, "accessible non-empty report"
            ):
                self.invoke(root, self.evidence(), apply=True)

            self.assertEqual(self.authoritative_bytes(root), before)
            job = load_json(root / "jobs" / "J001" / "job.json")
            self.assertIsNone(job["session_ref"])
            self.assertIsNone(job["outcome"])

    def test_completed_response_uses_normal_execution_field_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report_required=False)
            before = self.authoritative_bytes(root)
            evidence = self.evidence({
                "status": "completed",
                "summary": "Complete.",
                "question": "Should more work be done?",
            })

            with self.assertRaisesRegex(OrchestratorError, "must not contain a question"):
                self.invoke(root, evidence, apply=True)

            self.assertEqual(self.authoritative_bytes(root), before)

    def test_repeated_apply_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Recovered report.\n")
            evidence = self.evidence()
            first = self.invoke(root, evidence, apply=True)
            before = self.authoritative_bytes(root)

            second = self.invoke(root, evidence, apply=True)

            self.assertTrue(first["recorded"])
            self.assertFalse(second["recorded"])
            self.assertEqual(second["classification"], "recorded_transport_response")
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_active_session_plan_keeps_existing_execution_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.authoritative_bytes(root)
            evidence = self.session_evidence("active")

            first = self.invoke(root, evidence)
            second = self.invoke(root, evidence)

            self.assertEqual(first, second)
            self.assertEqual(first["classification"], "active_session")
            self.assertEqual(first["recommended_action"], "keep_existing_session_running")
            self.assertFalse(first["replacement_allowed"])
            self.assertEqual(first["transport_instruction"]["kind"], "keep_running")
            self.assertEqual(
                first["transport_instruction"]["session_ref"],
                "transport-session-1",
            )
            self.assertIn("native status", first["transport_instruction"]["instruction"])
            self.assertNotIn("prompt", first["transport_instruction"])
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_active_session_apply_restores_running_without_replacing_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="recovering")

            result = self.invoke(root, self.session_evidence("active"), apply=True)
            job = load_json(root / "jobs" / "J001" / "job.json")

            self.assertTrue(result["state_changed"])
            self.assertEqual(result["state_transition"], {
                "from": "recovering",
                "to": "running",
            })
            self.assertFalse(result["replacement_allowed"])
            self.assertEqual(job["status"], "running")
            self.assertEqual(job["session_ref"], "transport-session-1")
            self.assertEqual(job["revision"], 2)

    def test_available_session_plan_and_apply_require_same_session_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            before = self.authoritative_bytes(root)
            evidence = self.session_evidence("available")

            plan = self.invoke(root, evidence)
            applied = self.invoke(root, evidence, apply=True)

            for result in (plan, applied):
                self.assertEqual(result["classification"], "available_session")
                self.assertEqual(
                    result["recommended_action"],
                    "continue_existing_session_for_outcome",
                )
                self.assertFalse(result["replacement_allowed"])
                self.assertFalse(result["state_changed"])
                self.assertEqual(
                    result["transport_instruction"]["kind"], "continue_session"
                )
                self.assertEqual(
                    result["transport_instruction"]["session_ref"],
                    "transport-session-1",
                )
                self.assertIn(
                    "Continue in this same session",
                    result["transport_instruction"]["prompt"],
                )
                self.assertNotIn(
                    "replacement", result["transport_instruction"]["prompt"].lower()
                )
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_replacement_prompt_contains_every_available_recovery_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, status="recovering", report="Current report body.\n")
            run = load_json(root / "run.json")
            run["job_ids"].append("J002")

            job = load_json(root / "jobs" / "J001" / "job.json")
            job.update({
                "pending_question": {
                    "text": "Which recovery option should be used?",
                    "context": "The prior session stopped at a decision point.",
                },
                "related_reports": ["jobs/J002/report.md"],
                "checkpoint_path": "jobs/J001/checkpoint.md",
                "outcome": {
                    "status": "needs_input",
                    "summary": "A recovery decision is required.",
                    "question": "Which recovery option should be used?",
                },
            })
            write_json(root / "jobs" / "J001" / "job.json", job)
            (root / "jobs" / "J001" / "checkpoint.md").write_text(
                "Checkpoint body.", encoding="utf-8"
            )

            related = {
                **job,
                "id": "J002",
                "title": "Recovery advisor",
                "status": "completed",
                "prompt_path": "jobs/J002/prompt.md",
                "session_ref": "transport-session-2",
                "creation_sequence": 2,
                "pending_question": None,
                "related_reports": [],
                "report_path": "jobs/J002/report.md",
                "checkpoint_path": None,
                "outcome": {
                    "status": "completed",
                    "summary": "Advice complete.",
                    "report_path": "jobs/J002/report.md",
                },
            }
            write_json(root / "jobs" / "J002" / "job.json", related)
            (root / "jobs" / "J002" / "prompt.md").write_text(
                "Provide recovery advice.", encoding="utf-8"
            )
            (root / "jobs" / "J002" / "report.md").write_text(
                "Related report body.", encoding="utf-8"
            )
            write_json(root / "run.json", run)

            evidence = self.unavailable_evidence(
                workspace={
                    "observation": "direct",
                    "path": "C:/workspace",
                    "summary": "Two modified files and passing focused tests.",
                },
                report={
                    "observation": "direct",
                    "path": "jobs/J001/report.md",
                    "summary": "The report records completed implementation work.",
                },
                checkpoint={
                    "observation": "direct",
                    "path": "jobs/J001/checkpoint.md",
                    "summary": "Resume after reviewing the pending choice.",
                },
                recovery_findings=[
                    "The old session is unavailable.",
                    "No repeated external effect is required.",
                ],
            )
            evidence["transport"].update({
                "transcript_ref": "transport://transport-session-1",
                "transcript_content": "Prior worker transcript content.",
            })

            result = self.invoke(root, evidence)
            prompt = result["transport_instruction"]["prompt"]

            self.assertEqual(result["classification"], "unavailable_session")
            self.assertEqual(result["recommended_action"], "start_replacement_session")
            self.assertTrue(result["replacement_allowed"])
            for expected in (
                "Complete the job.",
                "transport://transport-session-1",
                "Prior worker transcript content.",
                "Current report body.",
                "The report records completed implementation work.",
                "Checkpoint body.",
                "Resume after reviewing the pending choice.",
                "Related report body.",
                "C:/workspace",
                "Two modified files and passing focused tests.",
                "Which recovery option should be used?",
                "The prior session stopped at a decision point.",
                "The old session is unavailable.",
                "No repeated external effect is required.",
            ):
                with self.subTest(expected=expected):
                    self.assertIn(expected, prompt)
            self.assertNotIn("bootstrap", prompt.lower())
            self.assertNotIn("acknowledg", prompt.lower())

    def test_ordinary_job_uses_workspace_evidence_without_recovery_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence(workspace={
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "The local changes are inspectable and focused tests pass.",
            })

            result = self.invoke(root, evidence)

            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["recommended_action"], "start_replacement_session")
            self.assertEqual(result["reconciliation_basis"], {
                "kind": "inspectable_local_state",
                "sources": ["workspace"],
                "recovery_policy_required": False,
            })
            self.assertIn(
                "The local changes are inspectable and focused tests pass.",
                result["transport_instruction"]["prompt"],
            )

    def test_ordinary_read_only_job_uses_report_without_recovery_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, report="Completed research findings.\n")
            evidence = self.unavailable_evidence(report={
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The durable findings can be inspected by a replacement.",
            })

            result = self.invoke(root, evidence)

            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["reconciliation_basis"], {
                "kind": "inspectable_local_state",
                "sources": ["report"],
                "recovery_policy_required": False,
            })
            prompt = result["transport_instruction"]["prompt"]
            self.assertIn("Completed research findings.", prompt)
            self.assertIn("The durable findings can be inspected", prompt)

    def test_external_effect_replacement_requires_configured_check_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, recovery_policy=self.external_recovery_policy())
            evidence = self.unavailable_evidence(workspace={
                "observation": "direct",
                "path": "C:/workspace",
                "summary": "Local state is inspectable but cannot prove publication.",
            })
            before = self.authoritative_bytes(root)

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "recovery_check_required")
            self.assertEqual(
                result["recommended_action"], "perform_configured_recovery_check"
            )
            self.assertFalse(result["replacement_allowed"])
            self.assertFalse(result["state_changed"])
            self.assertEqual(result["recovery_check_instruction"], {
                "check": "Query whether release 2.4.0 already exists.",
                "accepted_results": ["positive", "negative", "unknown"],
            })
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_external_outcome_is_undecidable_when_every_safety_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, recovery_policy=self.external_recovery_policy())
            evidence = self.unavailable_evidence(
                recovery_check=self.recovery_check("unknown")
            )
            before = self.authoritative_bytes(root)

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "external_outcome_undecidable")
            self.assertEqual(
                result["recommended_action"],
                "request_user_authority_or_recovery_investigation",
            )
            self.assertEqual(result["safe_action_evidence"], {
                "transport_outcome": False,
                "idempotency_key": False,
                "external_query": False,
                "durable_local_effect": False,
            })
            self.assertFalse(result["automatic_retry_allowed"])
            self.assertFalse(result["replacement_allowed"])
            self.assertFalse(result["state_changed"])
            self.assertNotIn("transport_instruction", result)
            self.assertNotIn("state_transition", result)
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_transport_outcome_prevents_external_undecidable_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(
                root,
                report="Recovered report.\n",
                recovery_policy=self.external_recovery_policy(),
            )

            result = self.invoke(root, self.evidence())

            self.assertEqual(result["classification"], "unrecorded_transport_response")
            self.assertEqual(result["recommended_action"], "record_transport_response")

    def test_idempotency_key_permits_safe_replacement_without_external_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            policy = {
                **self.external_recovery_policy(),
                "idempotency_key": "publish-release-2.4.0",
            }
            self.write_state(root, recovery_policy=policy)

            result = self.invoke(root, self.unavailable_evidence())

            self.assertEqual(result["classification"], "unavailable_session")
            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["reconciliation_basis"], {
                "kind": "idempotency_key",
                "idempotency_key": "publish-release-2.4.0",
            })

    def test_durable_local_effect_evidence_permits_safe_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(
                root,
                report="A durable provider receipt records no publication.\n",
                recovery_policy=self.external_recovery_policy(),
            )
            evidence = self.unavailable_evidence(report={
                "observation": "direct",
                "path": "jobs/J001/report.md",
                "summary": "The durable receipt proves the effect is absent.",
                "effect_state": "absent",
            })

            result = self.invoke(root, evidence)

            self.assertEqual(result["classification"], "unavailable_session")
            self.assertTrue(result["replacement_allowed"])
            self.assertEqual(result["reconciliation_basis"], {
                "kind": "durable_local_effect_evidence",
                "result": "absent",
                "sources": ["report"],
            })

    def test_positive_external_recovery_check_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, recovery_policy=self.external_recovery_policy())
            evidence = self.unavailable_evidence(
                recovery_check=self.recovery_check("positive")
            )
            before = self.authoritative_bytes(root)

            result = self.invoke(root, evidence, apply=True)

            self.assertEqual(result["classification"], "external_effect_confirmed")
            self.assertEqual(
                result["recommended_action"],
                "reconcile_confirmed_external_effect",
            )
            self.assertFalse(result["replacement_allowed"])
            self.assertFalse(result["state_changed"])
            self.assertEqual(
                result["recovery_check_result"]["result"], "positive"
            )
            self.assertNotIn("transport_instruction", result)
            self.assertEqual(self.authoritative_bytes(root), before)

    def test_result_for_different_recovery_check_cannot_unlock_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, recovery_policy=self.external_recovery_policy())
            supplied = self.recovery_check("negative")
            supplied["check"] = "Query whether a different release exists."
            evidence = self.unavailable_evidence(recovery_check=supplied)
            before = self.authoritative_bytes(root)

            with self.assertRaisesRegex(
                OrchestratorError, "does not match its configured job-level check"
            ):
                self.invoke(root, evidence, apply=True)

            self.assertEqual(self.authoritative_bytes(root), before)

    def test_negative_external_recovery_check_permits_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root, recovery_policy=self.external_recovery_policy())
            evidence = self.unavailable_evidence(
                recovery_check=self.recovery_check("negative")
            )

            result = self.invoke(root, evidence, apply=True)
            job = load_json(root / "jobs" / "J001" / "job.json")

            self.assertEqual(result["classification"], "unavailable_session")
            self.assertTrue(result["replacement_allowed"])
            self.assertTrue(result["state_changed"])
            self.assertEqual(result["reconciliation_basis"], {
                "kind": "configured_recovery_check",
                "check": "Query whether release 2.4.0 already exists.",
                "result": "negative",
                "summary": "Release 2.4.0 does not exist in the provider.",
            })
            prompt = result["transport_instruction"]["prompt"]
            self.assertIn("## Recovery Check Result", prompt)
            self.assertIn("Result: `negative`", prompt)
            self.assertEqual(job["status"], "recovering")

    def test_replacement_prompt_omits_unavailable_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)

            result = self.invoke(root, self.unavailable_evidence())
            prompt = result["transport_instruction"]["prompt"]

            self.assertIn("## Original Job Prompt", prompt)
            for heading in (
                "Available Transport Transcript",
                "Current Report",
                "Current Checkpoint",
                "Related Reports",
                "Workspace Observation",
                "Pending Question",
                "Recovery Findings",
            ):
                with self.subTest(heading=heading):
                    self.assertNotIn(heading, prompt)
            self.assertNotIn("bootstrap", prompt.lower())
            self.assertNotIn("acknowledg", prompt.lower())

    def test_replacement_apply_marks_recovering_without_persisting_prompt_or_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            self.write_state(root)
            evidence = self.unavailable_evidence()
            evidence["transport"]["transcript_content"] = "Ephemeral transcript text."

            result = self.invoke(root, evidence, apply=True)
            job = load_json(root / "jobs" / "J001" / "job.json")

            self.assertTrue(result["state_changed"])
            self.assertEqual(result["state_transition"], {
                "from": "running",
                "to": "recovering",
            })
            self.assertEqual(job["status"], "recovering")
            self.assertEqual(job["session_ref"], "transport-session-1")
            self.assertEqual(job["revision"], 2)
            persisted = b"\n".join(
                path.read_bytes() for path in root.rglob("*") if path.is_file()
            )
            self.assertNotIn(b"Ephemeral transcript text.", persisted)
            self.assertFalse(any(
                "transcript" in path.name.lower() or "recovery-prompt" in path.name.lower()
                for path in root.rglob("*")
            ))


if __name__ == "__main__":
    unittest.main()
