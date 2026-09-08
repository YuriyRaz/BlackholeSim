from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError  # noqa: E402
from transport_v5 import FakeTransportAdapter  # noqa: E402
from v5_core import (  # noqa: E402
    _condition,
    artifact_ref,
    init_v5_run,
    load_v5_state,
    record_v5_launch_receipt,
    record_v5_response_receipt,
    register_v5_jobs,
    select_v5_next_operation,
)


NOW = "2026-07-24T12:00:00Z"
RUN_ID = "RUN-EVTEST"


def _make_definition(jobs):
    return {"schema_version": 5, "jobs": jobs}


def _simple_job(job_id, *, conditions=None, depends_on=None, verifier_job_id=None, report_required=True):
    base = {
        "id": job_id,
        "title": f"Job {job_id}",
        "goal": f"Goal for {job_id}",
        "completion_conditions": conditions or [{
            "id": f"cond-{job_id}",
            "description": f"Condition for {job_id}",
            "required": True,
            "evidence_required": False,
            "verification": "self",
        }],
        "report_required": report_required,
        "side_effect_class": "none",
    }
    if depends_on:
        base["depends_on"] = depends_on
    return base


def _setup_run(base, definition):
    request = base / "request.md"
    request.write_text("Request\n", encoding="utf-8")
    result = init_v5_run(request, "Goal", run_id=RUN_ID, state_root=base, workspace=base)
    run_root = Path(result["run_root"])
    register_v5_jobs(run_root, definition, controller="test")
    return run_root


def _launch_and_respond(run_root, adapter, job_id, *, session, condition_id, condition_status="passed",
                         verified_by=None, status="completed", extra_conditions=None, report_content=None,
                         raw_extra=None):
    operation = select_v5_next_operation(run_root)
    assert operation.get("job_id") == job_id, f"Expected start for {job_id}, got {operation['operation']}"
    launch = record_v5_launch_receipt(run_root, adapter.launch_receipt(
        dispatch_id=operation["dispatch"]["dispatch_id"],
        native_session_ref=session,
        run_id=RUN_ID,
        job_id=job_id,
        prompt_sha256=operation["dispatch"]["prompt_sha256"],
        created_at=NOW,
    ), controller="test", adapter=adapter)

    if report_content is None:
        report_path = run_root / "jobs" / job_id / "report.md"
        report_path.write_text(f"Report for {job_id}\n", encoding="utf-8")
        report_content = report_path.read_bytes()

    condition_results = [{"condition_id": condition_id, "status": condition_status, "verified_by": verified_by or job_id}]
    if extra_conditions:
        condition_results.extend(extra_conditions)

    outcome = {"status": status, "summary": f"Result for {job_id}"}
    if status == "completed":
        report_ref = artifact_ref(RUN_ID, job_id, "report")
        outcome["artifacts"] = [{"ref": report_ref, "content_sha256": hashlib.sha256(report_content).hexdigest()}]
        outcome["condition_results"] = condition_results

    raw = json.dumps(outcome)
    return record_v5_response_receipt(run_root, adapter.response_receipt(
        attempt_id=launch["attempt_id"],
        native_session_ref=session,
        run_id=RUN_ID,
        job_id=job_id,
        response_id=f"RESP-{job_id}",
        raw_response=raw,
        received_at=NOW,
    ), controller="test", adapter=adapter)


# ── 1. Structured Conditions ──

class TestStructuredConditions(unittest.TestCase):
    def test_registration_with_valid_structured_conditions(self):
        cond = _condition({
            "id": "c1", "description": "desc", "required": True,
            "evidence_required": False, "verification": "self",
        })
        self.assertEqual(cond["id"], "c1")
        self.assertEqual(cond["verification"], "self")
        self.assertTrue(cond["required"])

    def test_duplicate_condition_ids_rejected(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "a", "required": True, "evidence_required": False, "verification": "self"},
                {"id": "c1", "description": "b", "required": True, "evidence_required": False, "verification": "self"},
            ]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            request = base / "request.md"
            request.write_text("Req\n", encoding="utf-8")
            result = init_v5_run(request, "Goal", run_id=RUN_ID, state_root=base, workspace=base)
            run_root = Path(result["run_root"])
            with self.assertRaisesRegex(OrchestratorError, "repeats condition"):
                register_v5_jobs(run_root, definition, controller="test")


# ── 2. Completion Claimed ──

class TestCompletionClaimed(unittest.TestCase):
    def test_self_verified_all_passed_completes(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "c1", "required": True, "evidence_required": False, "verification": "self"},
            ]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            result = _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1")
            self.assertEqual(result["status"], "completed")

    def test_missing_required_condition_gives_completion_claimed(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "self cond", "required": True, "evidence_required": False, "verification": "self"},
                {"id": "c2", "description": "independent cond", "required": True, "evidence_required": False,
                 "verification": "independent", "verifier_job_id": "J002"},
            ]),
            _simple_job("J002", depends_on=["J001"]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            result = _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1",
                                          extra_conditions=[{"condition_id": "c2", "status": "not_run", "verified_by": "J001"}])
            self.assertEqual(result["status"], "completion_claimed")


# ── 3. Independent Verifier Gate ──

class TestIndependentVerifierGate(unittest.TestCase):
    def test_verifier_job_scheduled_from_completion_claimed(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "needs verifier", "required": True, "evidence_required": False,
                 "verification": "independent", "verifier_job_id": "J002"},
            ]),
            _simple_job("J002", depends_on=["J001"]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1")
            state = load_v5_state(run_root)
            self.assertEqual(state["jobs"]["J001"]["status"], "completion_claimed")
            next_op = select_v5_next_operation(run_root)
            self.assertEqual(next_op["job_id"], "J002")

    def test_self_approving_independent_condition_does_not_satisfy(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "independent", "required": True, "evidence_required": False,
                 "verification": "independent", "verifier_job_id": "J002"},
            ]),
            _simple_job("J002", depends_on=["J001"]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1",
                                verified_by="J001")
            state = load_v5_state(run_root)
            self.assertEqual(state["jobs"]["J001"]["status"], "completion_claimed")
            next_op = select_v5_next_operation(run_root)
            self.assertEqual(next_op["job_id"], "J002")


# ── 4. Verifier Failure ──

class TestVerifierFailure(unittest.TestCase):
    def test_verifier_returning_failed_puts_target_in_repair_required(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "verified", "required": True, "evidence_required": False,
                 "verification": "independent", "verifier_job_id": "J002"},
            ]),
            _simple_job("J002", depends_on=["J001"], conditions=[
                {"id": "c1", "description": "verify c1", "required": True, "evidence_required": False, "verification": "self"},
            ]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1")
            _launch_and_respond(run_root, adapter, "J002", session="s2", condition_id="c1",
                                condition_status="failed")
            state = load_v5_state(run_root)
            self.assertEqual(state["jobs"]["J001"]["status"], "repair_required")

    def test_verifier_returning_unavailable_blocks_target(self):
        definition = _make_definition([
            _simple_job("J001", conditions=[
                {"id": "c1", "description": "verified", "required": True, "evidence_required": False,
                 "verification": "independent", "verifier_job_id": "J002"},
            ]),
            _simple_job("J002", depends_on=["J001"], conditions=[
                {"id": "c1", "description": "verify c1", "required": True, "evidence_required": False, "verification": "self"},
            ]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="c1")
            _launch_and_respond(run_root, adapter, "J002", session="s2", condition_id="c1",
                                condition_status="unavailable")
            state = load_v5_state(run_root)
            self.assertEqual(state["jobs"]["J001"]["status"], "blocked")


# ── 5. Terminal Run Disposition ──

class TestTerminalRunDisposition(unittest.TestCase):
    def test_all_completed_yields_successful_run_complete(self):
        definition = _make_definition([
            _simple_job("J001"),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="cond-J001")
            result = select_v5_next_operation(run_root)
            self.assertEqual(result, {"operation": "run_complete", "run_status": "completed", "successful": True})

    def test_one_job_failed_yields_failed_run_complete(self):
        definition = _make_definition([
            _simple_job("J001"),
            _simple_job("J002"),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _setup_run(Path(tmp), definition)
            adapter = FakeTransportAdapter()
            _launch_and_respond(run_root, adapter, "J001", session="s1", condition_id="cond-J001")
            _launch_and_respond(run_root, adapter, "J002", session="s2", condition_id="cond-J002", status="failed")
            result = select_v5_next_operation(run_root)
            self.assertEqual(result, {"operation": "run_complete", "run_status": "failed", "successful": False})


if __name__ == "__main__":
    unittest.main()
