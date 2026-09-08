from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, write_json  # noqa: E402
from transport_v5 import FakeTransportAdapter  # noqa: E402
from v5_core import (  # noqa: E402
    V5,
    artifact_ref,
    init_v5_run,
    load_v5_state,
    record_v5_launch_receipt,
    record_v5_response_receipt,
    register_v5_jobs,
    resolve_artifact_ref,
    select_v5_next_operation,
)


NOW = "2026-07-24T12:00:00Z"


def _make_definition(jobs=None):
    return {
        "schema_version": 5,
        "jobs": jobs or [{
            "id": "J001",
            "title": "Primary",
            "goal": "Do work.",
            "completion_conditions": [{
                "id": "tests",
                "description": "Tests pass",
                "required": True,
                "evidence_required": False,
                "verification": "self",
            }],
            "report_required": True,
            "side_effect_class": "none",
        }],
    }


def _run_with_one_job(tmp, run_id="RUN-ART"):
    base = Path(tmp)
    request = base / "request.md"
    request.write_text("Request\n", encoding="utf-8")
    run = Path(init_v5_run(request, "Goal", run_id=run_id, state_root=base, workspace=base)["run_root"])
    register_v5_jobs(run, _make_definition(), controller="test")
    return run


def _run_with_chain(tmp, run_id="RUN-CHAIN"):
    base = Path(tmp)
    request = base / "request.md"
    request.write_text("Request\n", encoding="utf-8")
    definition = _make_definition(jobs=[
        {
            "id": "J001",
            "title": "First",
            "goal": "First job.",
            "completion_conditions": [{
                "id": "first_done",
                "description": "First done",
                "required": True,
                "evidence_required": False,
                "verification": "self",
            }],
            "report_required": True,
            "side_effect_class": "none",
        },
        {
            "id": "J002",
            "title": "Second",
            "goal": "Second job.",
            "depends_on": ["J001"],
            "completion_conditions": [{
                "id": "second_done",
                "description": "Second done",
                "required": True,
                "evidence_required": False,
                "verification": "self",
            }],
            "report_required": True,
            "side_effect_class": "none",
        },
    ])
    run = Path(init_v5_run(request, "Goal", run_id=run_id, state_root=base, workspace=base)["run_root"])
    register_v5_jobs(run, definition, controller="test")
    return run


class CanonicalReferenceParsingTest(unittest.TestCase):
    def test_artifact_ref_produces_correct_run_format(self) -> None:
        ref = artifact_ref("RUN-abc", "J001", "report")
        self.assertEqual(ref, "run://RUN-abc/jobs/J001/report")

    def test_artifact_ref_rejects_invalid_components(self) -> None:
        with self.assertRaises(OrchestratorError):
            artifact_ref("../../../etc", "J001", "report")
        with self.assertRaises(OrchestratorError):
            artifact_ref("RUN-1", "", "report")
        with self.assertRaises(OrchestratorError):
            artifact_ref("RUN-1", "J001", "..")

    def test_resolve_artifact_ref_resolves_valid_reference_to_correct_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            ref = artifact_ref("RUN-ART", "J001", "report")
            path = resolve_artifact_ref(run, ref)
            expected = (run / "jobs" / "J001" / "report.md").resolve()
            self.assertEqual(path, expected)

    def test_resolve_artifact_ref_rejects_wrong_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            ref = artifact_ref("RUN-WRONG", "J001", "report")
            with self.assertRaisesRegex(OrchestratorError, "another run"):
                resolve_artifact_ref(run, ref)

    def test_resolve_artifact_ref_rejects_invalid_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            with self.assertRaisesRegex(OrchestratorError, "invalid"):
                resolve_artifact_ref(run, "not-a-valid-ref")

    def test_resolve_artifact_ref_rejects_unsupported_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            ref = artifact_ref("RUN-ART", "J001", "log")
            with self.assertRaisesRegex(OrchestratorError, "unsupported"):
                resolve_artifact_ref(run, ref)


class StaleReportRejectionTest(unittest.TestCase):
    def test_report_from_earlier_attempt_is_rejected_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            adapter = FakeTransportAdapter()
            start = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-ART", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Original report content", encoding="utf-8")
            correct_digest = hashlib.sha256(report.read_bytes()).hexdigest()
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{"ref": "run://RUN-ART/jobs/J001/report", "content_sha256": correct_digest}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-ART", job_id="J001", response_id="RESP-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["status"], "completed")
            old_digest = hashlib.sha256(b"stale content").hexdigest()
            stale_raw = json.dumps({
                "status": "completed", "summary": "Stale.",
                "artifacts": [{"ref": "run://RUN-ART/jobs/J001/report", "content_sha256": old_digest}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            with self.assertRaisesRegex(OrchestratorError, "active attempt"):
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                    run_id="RUN-ART", job_id="J001", response_id="RESP-STALE",
                    raw_response=stale_raw, received_at=NOW,
                ), controller="test", adapter=adapter)

    def test_report_from_different_run_is_rejected_as_cross_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp, run_id="RUN-A")
            adapter = FakeTransportAdapter()
            start = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-A", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Good report", encoding="utf-8")
            good_digest = hashlib.sha256(report.read_bytes()).hexdigest()
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{"ref": "run://RUN-A/jobs/J001/report", "content_sha256": good_digest}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-A", job_id="J001", response_id="RESP-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J001"]["status"], "completed")
            cross_raw = json.dumps({
                "status": "completed", "summary": "From another run.",
                "artifacts": [{"ref": "run://RUN-B/jobs/J001/report", "content_sha256": "a" * 64}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            with self.assertRaisesRegex(OrchestratorError, "active attempt"):
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                    run_id="RUN-A", job_id="J001", response_id="RESP-CROSS",
                    raw_response=cross_raw, received_at=NOW,
                ), controller="test", adapter=adapter)


class RootReplacementRejectionTest(unittest.TestCase):
    def test_root_replaced_report_file_rejected_on_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_one_job(tmp)
            adapter = FakeTransportAdapter()
            start = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-ART", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("Worker authored report", encoding="utf-8")
            worker_digest = hashlib.sha256(report.read_bytes()).hexdigest()
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [{"ref": "run://RUN-ART/jobs/J001/report", "content_sha256": worker_digest}],
                "condition_results": [{"condition_id": "tests", "status": "passed", "verified_by": "J001"}],
            })
            receipt = adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-ART", job_id="J001", response_id="RESP-1",
                raw_response=raw, received_at=NOW,
            )
            report.write_text("Root replaced content", encoding="utf-8")
            with self.assertRaisesRegex(OrchestratorError, "digest does not match"):
                record_v5_response_receipt(run, receipt, controller="test", adapter=adapter)


class MissingDependencyReportsTest(unittest.TestCase):
    def test_job_with_incomplete_dependency_cannot_be_dispatched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_chain(tmp)
            start = select_v5_next_operation(run)
            self.assertEqual(start["operation"], "start_job")
            self.assertEqual(start["job_id"], "J001")
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["J002"]["status"], "queued")
            self.assertEqual(state["jobs"]["J001"]["status"], "starting")

    def test_job_with_dependency_that_has_no_accepted_report_cannot_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = _run_with_chain(tmp, run_id="RUN-CHAIN2")
            adapter = FakeTransportAdapter()
            start = select_v5_next_operation(run)
            launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                dispatch_id=start["dispatch"]["dispatch_id"],
                native_session_ref="ses-1",
                run_id="RUN-CHAIN2", job_id="J001",
                prompt_sha256=start["dispatch"]["prompt_sha256"],
                created_at=NOW,
            ), controller="test", adapter=adapter)
            report = run / "jobs" / "J001" / "report.md"
            report.write_text("First job report", encoding="utf-8")
            raw = json.dumps({
                "status": "completed", "summary": "Done.",
                "artifacts": [],
                "condition_results": [{"condition_id": "first_done", "status": "passed", "verified_by": "J001"}],
            })
            record_v5_response_receipt(run, adapter.response_receipt(
                attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                run_id="RUN-CHAIN2", job_id="J001", response_id="RESP-1",
                raw_response=raw, received_at=NOW,
            ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertIn(state["jobs"]["J001"]["status"], ("completed", "completion_claimed"))
            self.assertEqual(state["jobs"]["J002"]["status"], "queued")
            self.assertEqual(len(state["jobs"]["J001"]["artifacts"]), 0)


class MultiDependencyOrderingTest(unittest.TestCase):
    def test_job_with_multiple_dependencies_gets_reports_in_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            definition = _make_definition(jobs=[
                {
                    "id": "JA",
                    "title": "Alpha",
                    "goal": "Alpha job.",
                    "completion_conditions": [{
                        "id": "alpha_done", "description": "Alpha done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
                {
                    "id": "JB",
                    "title": "Beta",
                    "goal": "Beta job.",
                    "completion_conditions": [{
                        "id": "beta_done", "description": "Beta done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
                {
                    "id": "JC",
                    "title": "Consumer",
                    "goal": "Consume reports.",
                    "depends_on": ["JA", "JB"],
                    "completion_conditions": [{
                        "id": "consumer_done", "description": "Consumer done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
            ])
            run = Path(init_v5_run(request, "Goal", run_id="RUN-MULTI", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, definition, controller="test")
            adapter = FakeTransportAdapter()
            for job_id in ("JA", "JB"):
                start = select_v5_next_operation(run)
                launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                    dispatch_id=start["dispatch"]["dispatch_id"],
                    native_session_ref="ses-1",
                    run_id="RUN-MULTI", job_id=job_id,
                    prompt_sha256=start["dispatch"]["prompt_sha256"],
                    created_at=NOW,
                ), controller="test", adapter=adapter)
                report = run / "jobs" / job_id / "report.md"
                report.write_text(f"Report from {job_id}", encoding="utf-8")
                raw = json.dumps({
                    "status": "completed", "summary": f"{job_id} done.",
                    "artifacts": [{
                        "ref": f"run://RUN-MULTI/jobs/{job_id}/report",
                        "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                    }],
                    "condition_results": [{
                        "condition_id": "alpha_done" if job_id == "JA" else "beta_done",
                        "status": "passed", "verified_by": job_id,
                    }],
                })
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                    run_id="RUN-MULTI", job_id=job_id, response_id=f"RESP-{job_id}",
                    raw_response=raw, received_at=NOW,
                ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["JA"]["status"], "completed")
            self.assertEqual(state["jobs"]["JB"]["status"], "completed")
            self.assertEqual(state["jobs"]["JC"]["status"], "queued")
            start = select_v5_next_operation(run)
            self.assertEqual(start["operation"], "start_job")
            self.assertEqual(start["job_id"], "JC")
            prompt = start["prompt"]
            self.assertIn("Dependency Reports", prompt)
            dep_lines = [l for l in prompt.splitlines() if "sha256" in l and "run://" in l]
            self.assertEqual(len(dep_lines), 2)
            refs = [l.split("`")[1] for l in dep_lines if "`" in l]
            self.assertIn("run://RUN-MULTI/jobs/JA/report", refs)
            self.assertIn("run://RUN-MULTI/jobs/JB/report", refs)
            self.assertEqual(refs, sorted(refs))


class AdvisoryDependencyCoexistenceTest(unittest.TestCase):
    def test_prompt_includes_both_advisory_and_dependency_reports_without_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            request = base / "request.md"
            request.write_text("Request\n", encoding="utf-8")
            definition = _make_definition(jobs=[
                {
                    "id": "JADV",
                    "title": "Advisory",
                    "goal": "Advisory job.",
                    "completion_conditions": [{
                        "id": "adv_done", "description": "Advisory done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
                {
                    "id": "JDEP",
                    "title": "Dependency",
                    "goal": "Dep job.",
                    "completion_conditions": [{
                        "id": "dep_done", "description": "Dep done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
                {
                    "id": "JMAIN",
                    "title": "Main",
                    "goal": "Main job consuming both.",
                    "depends_on": ["JDEP"],
                    "related_reports": ["run://RUN-CO/jobs/JADV/report"],
                    "completion_conditions": [{
                        "id": "main_done", "description": "Main done",
                        "required": True, "evidence_required": False, "verification": "self",
                    }],
                    "report_required": True, "side_effect_class": "none",
                },
            ])
            run = Path(init_v5_run(request, "Goal", run_id="RUN-CO", state_root=base, workspace=base)["run_root"])
            register_v5_jobs(run, definition, controller="test")
            adapter = FakeTransportAdapter()
            for job_id in ("JADV", "JDEP"):
                start = select_v5_next_operation(run)
                launch = record_v5_launch_receipt(run, adapter.launch_receipt(
                    dispatch_id=start["dispatch"]["dispatch_id"],
                    native_session_ref="ses-1",
                    run_id="RUN-CO", job_id=job_id,
                    prompt_sha256=start["dispatch"]["prompt_sha256"],
                    created_at=NOW,
                ), controller="test", adapter=adapter)
                report = run / "jobs" / job_id / "report.md"
                report.write_text(f"Report from {job_id}", encoding="utf-8")
                raw = json.dumps({
                    "status": "completed", "summary": f"{job_id} done.",
                    "artifacts": [{
                        "ref": f"run://RUN-CO/jobs/{job_id}/report",
                        "content_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                    }],
                    "condition_results": [{
                        "condition_id": "adv_done" if job_id == "JADV" else "dep_done",
                        "status": "passed", "verified_by": job_id,
                    }],
                })
                record_v5_response_receipt(run, adapter.response_receipt(
                    attempt_id=launch["attempt_id"], native_session_ref="ses-1",
                    run_id="RUN-CO", job_id=job_id, response_id=f"RESP-{job_id}",
                    raw_response=raw, received_at=NOW,
                ), controller="test", adapter=adapter)
            state = load_v5_state(run)
            self.assertEqual(state["jobs"]["JADV"]["status"], "completed")
            self.assertEqual(state["jobs"]["JDEP"]["status"], "completed")
            self.assertEqual(state["jobs"]["JMAIN"]["status"], "queued")
            start = select_v5_next_operation(run)
            self.assertEqual(start["operation"], "start_job")
            self.assertEqual(start["job_id"], "JMAIN")
            prompt = start["prompt"]
            self.assertIn("Dependency Reports", prompt)
            self.assertIn("Related Reports", prompt)
            self.assertIn("run://RUN-CO/jobs/JADV/report", prompt)
            dep_refs = [line for line in prompt.splitlines() if "JDEP" in line and "sha256" in line]
            self.assertEqual(len(dep_refs), 1)
            adv_refs = [line for line in prompt.splitlines() if "JADV" in line]
            self.assertTrue(len(adv_refs) >= 1)
            self.assertNotIn("advisory: `run://", prompt)
            dep_section_start = prompt.index("Dependency Reports")
            related_section_start = prompt.index("Related Reports")
            self.assertLess(dep_section_start, related_section_start)


if __name__ == "__main__":
    unittest.main()
