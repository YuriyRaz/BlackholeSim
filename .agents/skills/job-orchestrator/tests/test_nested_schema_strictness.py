from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, validate_record


class NestedSchemaStrictnessTest(unittest.TestCase):
    def result(self) -> dict:
        return {
            "schema_version": 3,
            "dispatch_id": "DSP-1",
            "nonce": "NONCE-1",
            "status": "completed",
            "summary": "done",
            "completed_work_units": ["U1"],
            "artifacts": [{
                "path": "report.md",
                "sha256": "0" * 64,
                "purpose": "worker report",
            }],
            "acceptance_evidence": ["tests passed"],
            "blocking_issues": [],
            "proposed_jobs": [],
            "improvement_observations": [],
            "checkpoint_sha256": "1" * 64,
            "created_at": "2026-07-09T12:00:00Z",
        }

    def event(self, event_type: str, data: dict) -> dict:
        return {
            "schema_version": 3,
            "event_id": "EV-1",
            "type": event_type,
            "run_id": "RUN-1",
            "revision": 1,
            "correlation_id": "COR-1",
            "created_at": "2026-07-09T12:00:00Z",
            "data": data,
        }

    def test_result_rejects_malformed_nested_evidence(self) -> None:
        valid = self.result()
        validate_record("result", valid)

        for artifact in (
            {"path": "report.md", "sha256": "bad"},
            {"path": "report.md", "sha256": "0" * 64, "unexpected": True},
        ):
            malformed = {**valid, "artifacts": [artifact]}
            with self.subTest(artifact=artifact):
                with self.assertRaises(OrchestratorError):
                    validate_record("result", malformed)

        malformed = {**valid, "improvement_observations": ["not-an-object"]}
        with self.assertRaises(OrchestratorError):
            validate_record("result", malformed)

    def test_lifecycle_event_rejects_wrong_variant_and_nested_result(self) -> None:
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record(
                "lifecycle-event",
                self.event("run_status", {"status": "active", "arbitrary": True}),
            )

        malformed = self.result()
        malformed["artifacts"] = [{"path": "report.md", "sha256": "bad"}]
        with self.assertRaises(OrchestratorError):
            validate_record(
                "lifecycle-event",
                self.event(
                    "worker_result",
                    {"dispatch_id": "DSP-1", "result": malformed},
                ),
            )

        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record(
                "lifecycle-event",
                self.event(
                    "dispatch_updated",
                    {
                        "dispatch_id": "DSP-1",
                        "changes": {
                            "side_effect_class": "bogus",
                            "unexpected": True,
                        },
                    },
                ),
            )

    def test_proposed_job_workflow_rejects_unknown_nested_fields(self) -> None:
        malformed = self.result()
        malformed["status"] = "blocked"
        malformed["acceptance_evidence"] = []
        malformed["blocking_issues"] = ["Needs child work"]
        malformed["proposed_jobs"] = [{
            "id": "CHILD-1",
            "workflow": {
                "unexpected": True,
                "nodes": [{"id": "apply", "position": 1, "work_units": ["U1"]}],
            },
        }]
        with self.assertRaisesRegex(OrchestratorError, "unexpected fields"):
            validate_record("result", malformed)


if __name__ == "__main__":
    unittest.main()
