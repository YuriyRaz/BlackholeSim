from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    LEGACY_UNATTESTED_VERSION,
    TRUSTED_RUN_VERSION,
    OrchestratorError,
    SCHEMA_REGISTRY,
    classify_run_version,
    load_schema,
    load_v4_state,
    require_run_version,
    validate_record,
    write_json,
    write_v4_document,
)
from transport_v5 import FakeTransportAdapter  # noqa: E402
from v5_core import (  # noqa: E402
    V5,
    init_v5_run,
    load_v5_state,
    record_v5_launch_receipt,
    record_v5_response_receipt,
    register_v5_jobs,
    select_v5_next_operation,
)


NOW = "2026-07-24T12:00:00Z"


class Version5ProtocolTest(unittest.TestCase):
    def definition(self) -> dict:
        return {
            "schema_version": 5,
            "jobs": [{
                "id": "J001",
                "title": "Implement",
                "goal": "Implement the requested change.",
                "completion_conditions": [{
                    "id": "tests",
                    "description": "Focused tests pass",
                    "required": True,
                    "evidence_required": False,
                    "verification": "self",
                }],
                "report_required": True,
                "side_effect_class": "repository",
                "recovery_policy": {"check": "Inspect repository state."},
            }],
        }

    def test_v5_schema_registry_contains_trusted_record_kinds(self) -> None:
        expected = {
            "artifact", "attempt", "completion-claim", "condition-result", "dispatch",
            "job", "job-definition", "launch-receipt", "outcome", "raw-response",
            "recovery-evidence", "response-receipt", "run", "setup",
        }
        self.assertEqual(SCHEMA_REGISTRY[5], frozenset(expected))
        for kind in expected:
            self.assertEqual(load_schema(kind, 5)["type"], "object")

    def test_v5_rejects_unknown_fields_and_invalid_condition_status(self) -> None:
        record = {
            "schema_version": 5,
            "condition_id": "tests",
            "status": "passed",
            "verified_by": "J001",
        }
        validate_record("condition-result", record)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("condition-result", {**record, "root_authored": True})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("condition-result", {**record, "status": "done"})

    def test_v5_rejects_caller_authored_session_and_accepts_adapter_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-5", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            self.assertEqual(start["operation"], "start_job")
            adapter = FakeTransportAdapter()
            with self.assertRaisesRegex(OrchestratorError, "adapter-authenticated"):
                record_v5_launch_receipt(
                    run,
                    {
                        "schema_version": 5,
                        "transport": "fake",
                        "dispatch_id": start["dispatch"]["dispatch_id"],
                        "native_session_ref": "invented-label",
                        "run_id": "RUN-5",
                        "job_id": "J001",
                        "prompt_sha256": start["dispatch"]["prompt_sha256"],
                        "created_at": NOW,
                        "proof": {},
                    },
                    controller="test",
                    adapter=adapter,
                )
            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-real",
                run_id="RUN-5",
                job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            )
            launch = record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            self.assertEqual(launch["native_session_ref"], "ses-real")
            self.assertEqual(load_v5_state(run)["jobs"]["J001"]["active_attempt_id"], launch["attempt_id"])

    def test_v5_raw_response_and_report_digest_are_bound_to_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-5", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"], native_session_ref="ses-real",
                run_id="RUN-5", job_id="J001", prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Worker report\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed",
                "summary": "Implemented.",
                "artifacts": [{
                    "ref": "run://RUN-5/jobs/J001/report",
                    "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-real", run_id="RUN-5", job_id="J001",
                response_id="RESP-1", raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertEqual(result["status"], "completed")
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["artifacts"][0]["content_sha256"], hashlib.sha256(report.read_bytes()).hexdigest())


NOW_V4 = "2026-07-14T12:00:00Z"


class Version5SchemaValidationTest(unittest.TestCase):
    """Comprehensive v5 schema tests for required fields, strict rejection, digests, IDs, and enums."""

    def test_run_schema_requires_all_fields_and_rejects_extra(self) -> None:
        valid = {
            "schema_version": 5, "protocol_version": 5, "run_id": "RUN-1",
            "goal": "Test", "status": "active", "job_ids": [],
            "created_at": NOW, "updated_at": NOW, "revision": 1,
        }
        validate_record("run", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("run", {**valid, "extra": True})

    def test_run_schema_rejects_invalid_status(self) -> None:
        record = {
            "schema_version": 5, "protocol_version": 5, "run_id": "RUN-1",
            "goal": "Test", "status": "unknown", "job_ids": [],
            "created_at": NOW, "updated_at": NOW, "revision": 1,
        }
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("run", record)

    def test_dispatch_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "dispatch_id": "DSP-1", "run_id": "RUN-1",
            "job_id": "J001", "kind": "start",
            "prompt_ref": "run://RUN-1/jobs/J001/prompt",
            "prompt_path": "jobs/J001/prompt.md",
            "prompt_sha256": "a" * 64, "status": "pending",
            "created_at": NOW,
        }
        validate_record("dispatch", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("dispatch", {**valid, "caller_ref": "x"})

    def test_dispatch_schema_rejects_invalid_kind(self) -> None:
        record = {
            "schema_version": 5, "dispatch_id": "DSP-1", "run_id": "RUN-1",
            "job_id": "J001", "kind": "retry",
            "prompt_ref": "run://RUN-1/jobs/J001/prompt",
            "prompt_path": "jobs/J001/prompt.md",
            "prompt_sha256": "a" * 64, "status": "pending",
            "created_at": NOW,
        }
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("dispatch", record)

    def test_dispatch_prompt_sha256_must_be_hex64(self) -> None:
        record = {
            "schema_version": 5, "dispatch_id": "DSP-1", "run_id": "RUN-1",
            "job_id": "J001", "kind": "start",
            "prompt_ref": "run://RUN-1/jobs/J001/prompt",
            "prompt_path": "jobs/J001/prompt.md",
            "prompt_sha256": "not-a-valid-hash", "status": "pending",
            "created_at": NOW,
        }
        with self.assertRaisesRegex(OrchestratorError, "invalid format"):
            validate_record("dispatch", record)

    def test_attempt_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "attempt_id": "ATT-1", "dispatch_id": "DSP-1",
            "transport": "fake", "native_session_ref": "ses-1",
            "run_id": "RUN-1", "job_id": "J001",
            "prompt_sha256": "b" * 64, "status": "active",
            "created_at": NOW,
        }
        validate_record("attempt", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("attempt", {**valid, "root_token": True})

    def test_attempt_schema_rejects_invalid_status(self) -> None:
        record = {
            "schema_version": 5, "attempt_id": "ATT-1", "dispatch_id": "DSP-1",
            "transport": "fake", "native_session_ref": "ses-1",
            "run_id": "RUN-1", "job_id": "J001",
            "prompt_sha256": "b" * 64, "status": "invalid",
            "created_at": NOW,
        }
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("attempt", record)

    def test_raw_response_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "response_id": "R-1", "attempt_id": "ATT-1",
            "response_sha256": "c" * 64, "raw_response": "{}",
            "received_at": NOW,
        }
        validate_record("raw-response", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("raw-response", {**valid, "forged": True})

    def test_raw_response_response_sha256_must_be_hex64(self) -> None:
        record = {
            "schema_version": 5, "response_id": "R-1", "attempt_id": "ATT-1",
            "response_sha256": "xyz", "raw_response": "{}",
            "received_at": NOW,
        }
        with self.assertRaisesRegex(OrchestratorError, "invalid format"):
            validate_record("raw-response", record)

    def test_artifact_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "ref": "run://RUN-1/jobs/J001/report",
            "path": "jobs/J001/report.md", "kind": "report",
            "producer_job_id": "J001", "attempt_id": "ATT-1",
            "content_sha256": "d" * 64, "accepted_at": NOW,
        }
        validate_record("artifact", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("artifact", {**valid, "root_signed": True})

    def test_artifact_kind_enum_is_valid(self) -> None:
        base = {
            "schema_version": 5, "ref": "run://RUN-1/jobs/J001/report",
            "path": "jobs/J001/report.md", "producer_job_id": "J001",
            "attempt_id": "ATT-1", "content_sha256": "d" * 64,
            "accepted_at": NOW,
        }
        for kind in ("report", "checkpoint", "evidence"):
            validate_record("artifact", {**base, "kind": kind})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("artifact", {**base, "kind": "prompt"})

    def test_completion_claim_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "response_id": "R-1",
            "condition_results": [], "claimed_at": NOW,
        }
        validate_record("completion-claim", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("completion-claim", {**valid, "forged": True})

    def test_condition_result_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "condition_id": "c1",
            "status": "passed", "verified_by": "J001",
        }
        validate_record("condition-result", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("condition-result", {**valid, "root_signed": True})

    def test_condition_result_status_enum_exactly_five_values(self) -> None:
        base = {
            "schema_version": 5, "condition_id": "c1",
            "verified_by": "J001",
        }
        for status in ("passed", "failed", "not_run", "unavailable", "unknown"):
            validate_record("condition-result", {**base, "status": status})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("condition-result", {**base, "status": "error"})

    def test_outcome_v5_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "status": "completed",
            "summary": "Done", "response_id": "R-1",
        }
        validate_record("outcome", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("outcome", {**valid, "root_authored": True})

    def test_outcome_v5_status_enum_is_valid(self) -> None:
        base = {"schema_version": 5, "summary": "Done", "response_id": "R-1"}
        for status in ("completed", "needs_input", "failed"):
            validate_record("outcome", {**base, "status": status})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("outcome", {**base, "status": "canceled"})

    def test_launch_receipt_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "transport": "fake",
            "dispatch_id": "DSP-1", "native_session_ref": "ses-1",
            "run_id": "RUN-1", "job_id": "J001",
            "prompt_sha256": "e" * 64, "created_at": NOW,
            "proof": {},
        }
        validate_record("launch-receipt", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("launch-receipt", {**valid, "caller_proof": True})

    def test_response_receipt_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "transport": "fake",
            "attempt_id": "ATT-1", "native_session_ref": "ses-1",
            "run_id": "RUN-1", "job_id": "J001",
            "response_id": "R-1", "response_sha256": "f" * 64,
            "raw_response": "{}", "received_at": NOW,
            "status": "returned", "proof": {},
        }
        validate_record("response-receipt", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("response-receipt", {**valid, "forged": True})

    def test_response_receipt_status_enum_is_valid(self) -> None:
        base = {
            "schema_version": 5, "transport": "fake",
            "attempt_id": "ATT-1", "native_session_ref": "ses-1",
            "run_id": "RUN-1", "job_id": "J001",
            "response_id": "R-1", "response_sha256": "f" * 64,
            "raw_response": "{}", "received_at": NOW, "proof": {},
        }
        for status in ("returned", "empty", "canceled", "lost", "unavailable", "unknown"):
            validate_record("response-receipt", {**base, "status": status})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("response-receipt", {**base, "status": "error"})

    def test_recovery_evidence_v5_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "job_id": "J001",
            "observed_at": NOW, "classification": "active",
            "transport": {}, "recovery_id": "REC-1",
        }
        validate_record("recovery-evidence", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("recovery-evidence", {**valid, "forged": True})

    def test_recovery_evidence_v5_classification_enum_is_valid(self) -> None:
        base = {
            "schema_version": 5, "job_id": "J001",
            "observed_at": NOW, "transport": {}, "recovery_id": "REC-1",
        }
        for cls in ("active", "returned", "canceled", "lost", "unknown", "contradictory"):
            validate_record("recovery-evidence", {**base, "classification": cls})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("recovery-evidence", {**base, "classification": "invalid"})

    def test_job_definition_v5_side_effect_class_enum_is_valid(self) -> None:
        for side_effect in ("none", "repository", "external_idempotent", "external_non_idempotent"):
            definition = {
                "schema_version": 5,
                "jobs": [{
                    "id": "J001", "title": "T", "goal": "G",
                    "completion_conditions": [{
                        "id": "c1", "description": "D", "required": True,
                        "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": side_effect,
                }],
            }
            validate_record("job-definition", definition)
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("job-definition", {
                "schema_version": 5,
                "jobs": [{
                    "id": "J001", "title": "T", "goal": "G",
                    "completion_conditions": [{
                        "id": "c1", "description": "D", "required": True,
                        "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "dangerous",
                }],
            })

    def test_job_v5_schema_rejects_extra_properties(self) -> None:
        valid = {
            "schema_version": 5, "id": "J001", "title": "T", "status": "queued",
            "prompt_path": "jobs/J001/prompt.md", "priority": 0,
            "creation_sequence": 1, "depends_on": [], "parent_job_id": None,
            "waiting_on": [], "pending_question": None, "answers": [],
            "related_reports": [], "report_required": True,
            "report_path": "run://RUN-1/jobs/J001/report",
            "checkpoint_path": None, "side_effect_class": "none",
            "recovery_policy": None, "dispatches": [], "attempts": [],
            "active_attempt_id": None, "artifacts": [], "raw_responses": [],
            "outcome": None, "completion_claim": None,
            "completion_conditions": [], "pending_dispatch_id": None,
            "created_at": NOW, "updated_at": NOW, "revision": 1,
        }
        validate_record("job", valid)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("job", {**valid, "forged": True})

    def test_job_v5_side_effect_class_enum_is_valid(self) -> None:
        base = {
            "schema_version": 5, "id": "J001", "title": "T", "status": "queued",
            "prompt_path": "jobs/J001/prompt.md", "priority": 0,
            "creation_sequence": 1, "depends_on": [], "parent_job_id": None,
            "waiting_on": [], "pending_question": None, "answers": [],
            "related_reports": [], "report_required": True,
            "report_path": "run://RUN-1/jobs/J001/report",
            "checkpoint_path": None, "recovery_policy": None,
            "dispatches": [], "attempts": [], "active_attempt_id": None,
            "artifacts": [], "raw_responses": [], "outcome": None,
            "completion_claim": None, "completion_conditions": [],
            "pending_dispatch_id": None,
            "created_at": NOW, "updated_at": NOW, "revision": 1,
        }
        for side_effect in ("none", "repository", "external_idempotent", "external_non_idempotent"):
            validate_record("job", {**base, "side_effect_class": side_effect})
        with self.assertRaisesRegex(OrchestratorError, "one of"):
            validate_record("job", {**base, "side_effect_class": "toxic"})

    def test_v4_schemas_are_loadable_for_legacy_audit(self) -> None:
        for kind in ("run", "job", "job-definition", "outcome", "setup"):
            schema = load_schema(kind, LEGACY_UNATTESTED_VERSION)
            self.assertEqual(schema["type"], "object")

    def test_v4_run_schema_version_is_4(self) -> None:
        schema = load_schema("run", LEGACY_UNATTESTED_VERSION)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 4)


class VersionLoadingTest(unittest.TestCase):
    """Tests for version loading that recognizes v4 as legacy_unattested."""

    def _v4_run_document(self) -> dict:
        return {
            "schema_version": 4, "protocol_version": 4, "run_id": "RUN-V4",
            "goal": "Legacy work", "status": "active", "job_ids": [],
            "created_at": NOW_V4, "updated_at": NOW_V4, "revision": 1,
        }

    def _v5_run_document(self) -> dict:
        return {
            "schema_version": 5, "protocol_version": 5, "run_id": "RUN-V5",
            "goal": "Trusted work", "status": "active", "job_ids": [],
            "created_at": NOW_V4, "updated_at": NOW_V4, "revision": 1,
        }

    def _write_v4_run(self, root: Path, document: dict) -> None:
        write_v4_document(root / "run.json", "run", document)

    def _write_v5_run(self, root: Path, document: dict) -> None:
        write_json(root / "run.json", document)

    def test_require_run_version_accepts_v4_and_v5(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_v4_run(root, self._v4_run_document())
            self.assertEqual(require_run_version(root, 4), 4)
            self._write_v5_run(root, self._v5_run_document())
            self.assertEqual(require_run_version(root, 5), 5)

    def test_require_run_version_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_v4_run(root, self._v4_run_document())
            with self.assertRaisesRegex(OrchestratorError, "unsupported version"):
                require_run_version(root, 5)
            self._write_v5_run(root, self._v5_run_document())
            with self.assertRaisesRegex(OrchestratorError, "unsupported version"):
                require_run_version(root, 4)

    def test_classify_run_version_v4_is_legacy_unattested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_v4_run(root, self._v4_run_document())
            result = classify_run_version(root)
            self.assertEqual(result["version"], 4)
            self.assertEqual(result["trust"], "legacy_unattested")
            self.assertFalse(result["mutable"])

    def test_classify_run_version_v5_is_authenticated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_v5_run(root, self._v5_run_document())
            result = classify_run_version(root)
            self.assertEqual(result["version"], 5)
            self.assertEqual(result["trust"], "authenticated_receipts")
            self.assertTrue(result["mutable"])

    def test_v4_runs_remain_available_for_legacy_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = {
                "schema_version": 4, "id": "J001", "title": "Legacy",
                "status": "queued", "prompt_path": "jobs/J001/prompt.md",
                "session_ref": None, "priority": 0, "creation_sequence": 1,
                "depends_on": [], "parent_job_id": None, "waiting_on": [],
                "pending_question": None, "related_reports": [],
                "report_required": False, "report_path": "jobs/J001/report.md",
                "checkpoint_path": None, "outcome": None, "recovery_policy": None,
                "created_at": NOW_V4, "updated_at": NOW_V4, "revision": 1,
            }
            run_doc = self._v4_run_document()
            run_doc["job_ids"] = ["J001"]
            (root / "jobs" / "J001").mkdir(parents=True)
            write_json(root / "jobs" / "J001" / "job.json", job)
            self._write_v4_run(root, run_doc)
            state = load_v4_state(root)
            self.assertEqual(state["run"]["schema_version"], 4)
            self.assertEqual(state["jobs"]["J001"]["status"], "queued")

    def test_new_runs_use_v5_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            result = init_v5_run(request, "Goal", run_id="RUN-NEW", state_root=base, workspace=base)
            root = Path(result["run_root"])
            classification = classify_run_version(root)
            self.assertEqual(classification["version"], 5)
            self.assertEqual(classification["trust"], "authenticated_receipts")
            self.assertTrue(classification["mutable"])

    def test_v4_run_not_silently_converted_to_v5(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_v4_run(root, self._v4_run_document())
            classification = classify_run_version(root)
            self.assertEqual(classification["trust"], "legacy_unattested")
            self.assertFalse(classification["mutable"])

    def test_v4_outcome_not_treated_as_v5_evidence(self) -> None:
        v4_outcome = {"status": "completed", "summary": "Legacy done."}
        validate_record("outcome", v4_outcome)
        v5_outcome = {"schema_version": 5, "status": "completed", "summary": "Done.", "response_id": "R-1"}
        validate_record("outcome", v5_outcome)
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("outcome", {"status": "completed", "summary": "Done.", "extra": True})


class AtomicPersistenceTest(unittest.TestCase):
    """Tests that v5 persistence handles immutable dispatches, append-only attempts, raw responses, artifacts, claims, and condition results."""

    def definition(self) -> dict:
        return {
            "schema_version": 5,
            "jobs": [{
                "id": "J001", "title": "Work", "goal": "Do work.",
                "completion_conditions": [{
                    "id": "tests", "description": "Tests pass",
                    "required": True, "evidence_required": False,
                    "verification": "self",
                }],
                "report_required": True, "side_effect_class": "none",
            }],
        }

    def test_dispatch_records_are_immutable_once_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-6", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            receipt = adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-6", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            )
            record_v5_launch_receipt(run, receipt, controller="test", adapter=adapter)
            state = load_v5_state(run)
            dispatch = next(d for d in state["jobs"]["J001"]["dispatches"]
                          if d["dispatch_id"] == start["dispatch"]["dispatch_id"])
            self.assertEqual(dispatch["status"], "delivered")

    def test_attempts_are_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-7", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch1 = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-7", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            state1 = load_v5_state(run)
            attempt_count_1 = len(state1["jobs"]["J001"]["attempts"])
            self.assertEqual(attempt_count_1, 1)
            self.assertEqual(state1["jobs"]["J001"]["attempts"][0]["attempt_id"], launch1["attempt_id"])

    def test_raw_responses_are_stored_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-8", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-8", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            raw = json.dumps({"status": "completed", "summary": "Done.", "response_id": "R-1"})
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-8", job_id="J001", response_id="R-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(len(state["jobs"]["J001"]["raw_responses"]), 1)
            self.assertEqual(state["jobs"]["J001"]["raw_responses"][0]["response_id"], "R-1")

    def test_artifacts_are_recorded_with_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-9", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-9", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Report content\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-9/jobs/J001/report",
                    "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-9", job_id="J001", response_id="R-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(len(state["jobs"]["J001"]["artifacts"]), 1)
            artifact = state["jobs"]["J001"]["artifacts"][0]
            self.assertEqual(artifact["ref"], "run://RUN-9/jobs/J001/report")
            self.assertEqual(artifact["kind"], "report")
            self.assertEqual(artifact["content_sha256"], hashlib.sha256(report.read_bytes()).hexdigest())
            self.assertEqual(artifact["producer_job_id"], "J001")
            self.assertEqual(artifact["attempt_id"], launch["attempt_id"])

    def test_completion_claim_is_recorded_on_completed_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-10", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-10", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Done\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-10/jobs/J001/report",
                    "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-10", job_id="J001", response_id="R-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            claim = state["jobs"]["J001"]["completion_claim"]
            self.assertIsNotNone(claim)
            self.assertEqual(claim["response_id"], "R-1")
            self.assertEqual(len(claim["condition_results"]), 1)
            self.assertEqual(claim["condition_results"][0]["condition_id"], "tests")
            self.assertEqual(claim["condition_results"][0]["status"], "passed")

    def test_condition_results_require_valid_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-11", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-11", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Done\n", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{
                    "ref": "run://RUN-11/jobs/J001/report",
                    "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                }],
                "condition_results": [{
                    "condition_id": "tests", "status": "passed", "verified_by": "J001",
                }],
            })
            result = record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-11", job_id="J001", response_id="R-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            self.assertEqual(result["status"], "completed")

    def test_attempt_ids_are_unique_across_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            run = Path(init_v5_run(request, "Goal", run_id="RUN-12", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, self.definition(), controller="test")
            start = select_v5_next_operation(run)
            adapter = FakeTransportAdapter()
            launch1 = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1", run_id="RUN-12", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"], created_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            ids = [a["attempt_id"] for a in state["jobs"]["J001"]["attempts"]]
            self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
