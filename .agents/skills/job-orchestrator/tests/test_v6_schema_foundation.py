"""Focused v6 schema foundation validation tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    SCHEMA_VERSION,
    SCHEMA_REGISTRY,
    OrchestratorError,
    load_schema,
    validate_record,
    content_hash,
)


def _valid_id() -> str:
    return "T-ABCDEFGHIJKLMOPQRST"


def _valid_digest() -> str:
    return "a" * 64


def _valid_datetime() -> str:
    return "2026-01-15T10:30:00Z"


def _minimal_record(kind: str, extra: dict | None = None) -> dict:
    """Build a minimal valid record for a given schema kind."""
    base = {"schema_version": SCHEMA_VERSION}
    if extra:
        base.update(extra)
    return base


class NestedFieldValidationTest(unittest.TestCase):
    """Prove nested object fields are validated against sub-schemas."""

    def test_campaign_envelope_limits_rejects_missing_max_cycles(self) -> None:
        record = _minimal_record("campaign-envelope", {
            "envelope_id": _valid_id(),
            "campaign_id": _valid_id(),
            "goal": "fix bug",
            "strategy": "repair",
            "version": 1,
            "authority_id": _valid_id(),
            "limits": {"max_jobs_per_cycle": 5, "max_total_jobs": 20},
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("campaign-envelope", record)
        self.assertIn("max_cycles", str(ctx.exception))

    def test_graph_policy_constraints_rejects_unknown_field(self) -> None:
        record = _minimal_record("graph-policy", {
            "policy_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "limits": {"max_vertices": 100, "max_edges": 200, "max_expansion_depth": 5},
            "constraints": {"cycle_detection": "strict", "fan_out_limit": 10, "unknown_field": "bad"},
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("graph-policy", record)
        self.assertIn("unexpected fields", str(ctx.exception))

    def test_finding_evidence_entry_rejects_missing_digest(self) -> None:
        record = _minimal_record("finding", {
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "producer_role": "verifier",
            "cycle_id": _valid_id(),
            "severity": "high",
            "confidence": 0.9,
            "evidence": [{"ref": "run://test/jobs/123"}],
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("finding", record)
        self.assertIn("digest", str(ctx.exception))

    def test_work_plan_target_rejects_invalid_target_type(self) -> None:
        record = _minimal_record("work-plan", {
            "plan_id": _valid_id(),
            "plan_type": "direct_repair",
            "cycle_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "targets": [{"target_id": _valid_id(), "target_type": "invalid_type"}],
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("work-plan", record)
        self.assertIn("target_type", str(ctx.exception))


class ClosedObjectValidationTest(unittest.TestCase):
    """Prove additionalProperties: false rejects extra fields at all levels."""

    def test_top_level_rejects_extra_field(self) -> None:
        record = _minimal_record("run", {
            "protocol_revision": "v6-closed",
            "run_id": "2026-01-15T103000Z-test",
            "goal": "test goal",
            "status": "active",
            "job_ids": [],
            "graph_revision": 1,
            "graph_digest": _valid_digest(),
            "campaign_envelope_id": _valid_id(),
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
            "sneaky_field": "should fail",
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("run", record)
        self.assertIn("unexpected fields", str(ctx.exception))
        self.assertIn("sneaky_field", str(ctx.exception))

    def test_nested_object_rejects_extra_field(self) -> None:
        record = _minimal_record("authority", {
            "authority_id": _valid_id(),
            "campaign_id": _valid_id(),
            "job_identity": _valid_id(),
            "role": "expander",
            "scope": {
                "allowed_child_roles": [],
                "max_child_depth": 0,
                "side_effects": ["none"],
                "max_child_jobs": 0,
                "extra": True
            },
            "granted_at": _valid_datetime(),
            "expires_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("authority", record)
        self.assertIn("unexpected fields", str(ctx.exception))

    def test_activation_rejects_extra_top_level(self) -> None:
        record = _minimal_record("activation", {
            "activation_id": _valid_id(),
            "job_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "context_snapshot_id": _valid_id(),
            "status": "activated",
            "created_at": _valid_datetime(),
            "bogus": True,
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("activation", record)
        self.assertIn("unexpected fields", str(ctx.exception))


class IdentityFormatValidationTest(unittest.TestCase):
    """Prove id pattern [A-Z][A-Z0-9_-]{0,127} is enforced."""

    def test_rejects_lowercase_id(self) -> None:
        record = _minimal_record("goal-judgment", {
            "judgment_id": "t-abcdefghijklmnopqrst",
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "GOAL_ACHIEVED",
            "evidence_refs": [],
            "reason": "all gates passed",
            "recorded_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("goal-judgment", record)

    def test_rejects_id_starting_with_digit(self) -> None:
        record = _minimal_record("dynamic-batch", {
            "batch_id": "1T-abcdefghijklmnopq",
            "campaign_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "open",
            "job_ids": [_valid_id()],
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("dynamic-batch", record)

    def test_rejects_too_long_id(self) -> None:
        long_id = "T-" + "A" * 128
        record = _minimal_record("expansion-commit", {
            "commit_id": long_id,
            "expansion_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision_before": 0,
            "graph_revision_after": 1,
            "status": "pending",
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("expansion-commit", record)

    def test_accepts_valid_id(self) -> None:
        record = _minimal_record("progress-fingerprint", {
            "fingerprint_id": "T-ABCDEFGHIJKLMOPQRST",
            "cycle_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "graph_revision": 1,
            "jobs_completed": 3,
            "jobs_total": 5,
            "findings_count": 1,
            "fingerprint_digest": _valid_digest(),
            "created_at": _valid_datetime(),
        })
        validate_record("progress-fingerprint", record)


class EdgeTypeValidationTest(unittest.TestCase):
    """Prove typed-dependency-edge edge_type enum is enforced."""

    def test_rejects_invalid_edge_type(self) -> None:
        record = _minimal_record("typed-dependency-edge", {
            "edge_id": _valid_id(),
            "source_job_id": _valid_id(),
            "target_job_id": _valid_id(),
            "edge_type": "invalid_edge",
            "graph_revision": 1,
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("typed-dependency-edge", record)
        self.assertIn("edge_type", str(ctx.exception))

    def test_accepts_valid_edge_types(self) -> None:
        for edge_type in ["success", "execution", "all-settled", "report", "verification", "batch", "cycle"]:
            record = _minimal_record("typed-dependency-edge", {
                "edge_id": _valid_id(),
                "source_job_id": _valid_id(),
                "target_job_id": _valid_id(),
                "edge_type": edge_type,
                "graph_revision": 1,
                "created_at": _valid_datetime(),
            })
            validate_record("typed-dependency-edge", record)


class CycleDetectionTest(unittest.TestCase):
    """Prove graph-policy cycle_detection constraint validation."""

    def test_accepts_strict_cycle_detection(self) -> None:
        record = _minimal_record("graph-policy", {
            "policy_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "limits": {"max_vertices": 100, "max_edges": 200, "max_expansion_depth": 5},
            "constraints": {"cycle_detection": "strict", "fan_out_limit": 10},
            "created_at": _valid_datetime(),
        })
        validate_record("graph-policy", record)

    def test_accepts_warn_cycle_detection(self) -> None:
        record = _minimal_record("graph-policy", {
            "policy_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "limits": {"max_vertices": 100, "max_edges": 200, "max_expansion_depth": 5},
            "constraints": {"cycle_detection": "warn", "fan_out_limit": 10},
            "created_at": _valid_datetime(),
        })
        validate_record("graph-policy", record)

    def test_rejects_invalid_cycle_detection(self) -> None:
        record = _minimal_record("graph-policy", {
            "policy_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "limits": {"max_vertices": 100, "max_edges": 200, "max_expansion_depth": 5},
            "constraints": {"cycle_detection": "ignore", "fan_out_limit": 10},
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("graph-policy", record)
        self.assertIn("cycle_detection", str(ctx.exception))


class AuthorityValidationTest(unittest.TestCase):
    """Prove authority scope validation and required fields."""

    def test_rejects_missing_authority_scope_fields(self) -> None:
        record = _minimal_record("authority", {
            "authority_id": _valid_id(),
            "campaign_id": _valid_id(),
            "job_identity": _valid_id(),
            "role": "expander",
            "scope": {
                "allowed_child_roles": [],
                "max_child_depth": 0,
                "side_effects": ["none"],
            },
            "granted_at": _valid_datetime(),
            "expires_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("authority", record)
        self.assertIn("max_child_jobs", str(ctx.exception))

    def test_rejects_non_boolean_scope_value(self) -> None:
        record = _minimal_record("authority", {
            "authority_id": _valid_id(),
            "campaign_id": _valid_id(),
            "job_identity": _valid_id(),
            "role": "expander",
            "scope": {"expansion": "yes", "repair": False, "verification": True},
            "granted_at": _valid_datetime(),
            "expires_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("authority", record)


class StaleRevisionRejectionTest(unittest.TestCase):
    """Prove graph_revision minimum constraints reject stale revisions."""

    def test_goal_gate_result_rejects_zero_revision(self) -> None:
        record = _minimal_record("goal-gate-result", {
            "goal_gate_result_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "definition_digest": _valid_digest(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 0,
            "producer_job_id": _valid_id(),
            "response_id": _valid_id(),
            "status": "passed",
            "measurement": "all checks pass",
            "evidence_refs": [],
            "recorded_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("goal-gate-result", record)
        self.assertIn("graph_revision", str(ctx.exception))

    def test_dispatch_rejects_zero_revision(self) -> None:
        record = _minimal_record("dispatch", {
            "dispatch_id": _valid_id(),
            "job_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "graph_revision": 0,
            "nonce": "nonce-123",
            "work_units": [{"unit_id": _valid_id(), "unit_type": "test"}],
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("dispatch", record)
        self.assertIn("graph_revision", str(ctx.exception))

    def test_expansion_commit_rejects_zero_after_revision(self) -> None:
        record = _minimal_record("expansion-commit", {
            "commit_id": _valid_id(),
            "expansion_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision_before": 0,
            "graph_revision_after": 0,
            "status": "pending",
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("expansion-commit", record)
        self.assertIn("graph_revision_after", str(ctx.exception))

    def test_activation_rejects_zero_revision(self) -> None:
        record = _minimal_record("activation", {
            "activation_id": _valid_id(),
            "job_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 0,
            "context_snapshot_id": _valid_id(),
            "status": "activated",
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("activation", record)
        self.assertIn("graph_revision", str(ctx.exception))


class AdditionalPropertiesRejectionTest(unittest.TestCase):
    """Prove additionalProperties:false rejects unknown fields everywhere."""

    def test_goal_judgment_rejects_extra_decision_field(self) -> None:
        record = _minimal_record("goal-judgment", {
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "CONTINUE",
            "evidence_refs": [],
            "reason": "more work needed",
            "recorded_at": _valid_datetime(),
            "extra_decision_info": "should fail",
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("goal-judgment", record)
        self.assertIn("unexpected fields", str(ctx.exception))
        self.assertIn("extra_decision_info", str(ctx.exception))

    def test_context_snapshot_versions_rejects_extra_field(self) -> None:
        record = _minimal_record("context-snapshot", {
            "snapshot_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "versions": {"goal_gates": 2, "findings": 1, "graph": 3, "extra": 0},
            "digest": _valid_digest(),
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("context-snapshot", record)
        self.assertIn("unexpected fields", str(ctx.exception))

    def test_graph_generation_rejects_extra_field(self) -> None:
        record = _minimal_record("graph-generation", {
            "generation_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "parent_revision": 0,
            "vertex_count": 5,
            "edge_count": 3,
            "graph_digest": _valid_digest(),
            "created_at": _valid_datetime(),
            "version_tag": "initial",
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("graph-generation", record)
        self.assertIn("unexpected fields", str(ctx.exception))

    def test_strategy_decision_rejects_extra_field(self) -> None:
        record = _minimal_record("strategy-decision", {
            "decision_id": _valid_id(),
            "campaign_id": _valid_id(),
            "cycle_id": _valid_id(),
            "decision_type": "expand",
            "rationale": "need more coverage",
            "producer_job_id": _valid_id(),
            "recorded_at": _valid_datetime(),
            "approved_by": "admin",
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("strategy-decision", record)
        self.assertIn("unexpected fields", str(ctx.exception))


class RequiredFieldsValidationTest(unittest.TestCase):
    """Prove missing required fields are caught."""

    def test_missing_required_field_in_run(self) -> None:
        record = _minimal_record("run", {
            "protocol_revision": "v6-closed",
            "run_id": "2026-01-15T103000Z-test",
            "goal": "test",
            "status": "active",
            "job_ids": [],
            "graph_revision": 1,
            "graph_digest": _valid_digest(),
            "campaign_envelope_id": _valid_id(),
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        validate_record("run", record)

    def test_missing_goal_in_run(self) -> None:
        record = _minimal_record("run", {
            "protocol_revision": "v6-closed",
            "run_id": "2026-01-15T103000Z-test",
            "status": "active",
            "job_ids": [],
            "graph_revision": 1,
            "graph_digest": _valid_digest(),
            "campaign_envelope_id": _valid_id(),
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("run", record)
        self.assertIn("goal", str(ctx.exception))


class EnumValidationTest(unittest.TestCase):
    """Prove enum constraints are enforced for all enum fields."""

    def test_goal_judgment_rejects_invalid_decision(self) -> None:
        record = _minimal_record("goal-judgment", {
            "judgment_id": _valid_id(),
            "goal_gate_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "producer_job_id": _valid_id(),
            "decision": "MAYBE",
            "evidence_refs": [],
            "reason": "unclear",
            "recorded_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("goal-judgment", record)
        self.assertIn("decision", str(ctx.exception))

    def test_dynamic_batch_rejects_invalid_status(self) -> None:
        record = _minimal_record("dynamic-batch", {
            "batch_id": _valid_id(),
            "campaign_id": _valid_id(),
            "cycle_id": _valid_id(),
            "status": "processing",
            "job_ids": [_valid_id()],
            "created_at": _valid_datetime(),
            "updated_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("dynamic-batch", record)
        self.assertIn("status", str(ctx.exception))

    def test_finding_rejects_invalid_severity(self) -> None:
        record = _minimal_record("finding", {
            "finding_id": _valid_id(),
            "producer_job_id": _valid_id(),
            "producer_role": "verifier",
            "cycle_id": _valid_id(),
            "severity": "catastrophic",
            "confidence": 0.5,
            "evidence": [{"ref": "run://test/jobs/1", "digest": _valid_digest()}],
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError) as ctx:
            validate_record("finding", record)
        self.assertIn("severity", str(ctx.exception))


class SchemaRegistryCompletenessTest(unittest.TestCase):
    """Prove all schema files are registered."""

    def test_registry_count_matches_directory(self) -> None:
        v6_dir = ROOT / "schemas" / "v6"
        schema_files = {f.stem.replace(".schema", "") for f in v6_dir.glob("*.schema.json")}
        registered = SCHEMA_REGISTRY[6]
        self.assertEqual(schema_files, registered,
                         f"Schema files {schema_files} != registered {registered}")

    def test_all_registered_schemas_load(self) -> None:
        for kind in SCHEMA_REGISTRY[6]:
            schema = load_schema(kind)
            self.assertEqual(schema.get("type"), "object", f"Schema {kind} must be object type")
            self.assertFalse(schema.get("additionalProperties", True),
                             f"Schema {kind} must have additionalProperties: false")
            self.assertEqual(schema.get("properties", {}).get("schema_version", {}).get("const"), 6,
                             f"Schema {kind} must enforce schema_version: 6")


class DigestFormatValidationTest(unittest.TestCase):
    """Prove digest pattern [0-9a-f]{64} is enforced."""

    def test_rejects_uppercase_digest(self) -> None:
        record = _minimal_record("context-snapshot", {
            "snapshot_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "versions": {"goal_gates": 0, "findings": 0, "graph": 1},
            "digest": "A" * 64,
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("context-snapshot", record)

    def test_rejects_short_digest(self) -> None:
        record = _minimal_record("progress-fingerprint", {
            "fingerprint_id": _valid_id(),
            "cycle_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "graph_revision": 1,
            "jobs_completed": 0,
            "jobs_total": 1,
            "findings_count": 0,
            "fingerprint_digest": "abc123",
            "created_at": _valid_datetime(),
        })
        with self.assertRaises(OrchestratorError):
            validate_record("progress-fingerprint", record)

    def test_accepts_valid_lowercase_hex_digest(self) -> None:
        record = _minimal_record("context-snapshot", {
            "snapshot_id": _valid_id(),
            "run_id": "2026-01-15T103000Z-test",
            "cycle_id": _valid_id(),
            "graph_revision": 1,
            "versions": {"goal_gates": 0, "findings": 0, "graph": 1},
            "digest": "a" * 64,
            "created_at": _valid_datetime(),
        })
        validate_record("context-snapshot", record)


class DatetimeFormatValidationTest(unittest.TestCase):
    """Prove date-time format is enforced."""

    def test_rejects_invalid_datetime(self) -> None:
        record = _minimal_record("retained-expansion", {
            "expansion_id": _valid_id(),
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
            "created_at": "not-a-date",
        })
        with self.assertRaises(OrchestratorError):
            validate_record("retained-expansion", record)

    def test_rejects_naive_datetime(self) -> None:
        record = _minimal_record("retained-expansion", {
            "expansion_id": _valid_id(),
            "plan_id": _valid_id(),
            "campaign_id": _valid_id(),
            "graph_revision": 1,
            "jobs_added": [_valid_id()],
            "edges_added": [],
            "provenance": {
                "producer_job_id": _valid_id(),
                "authority_id": _valid_id(),
                "cycle_id": _valid_id(),
            },
            "created_at": "2026-01-15T10:30:00",
        })
        with self.assertRaises(OrchestratorError):
            validate_record("retained-expansion", record)


if __name__ == "__main__":
    unittest.main()
