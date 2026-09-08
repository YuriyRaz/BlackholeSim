"""Append-only graph model for the v6 dynamic orchestration protocol."""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator_core import (
    SCHEMA_VERSION,
    OrchestratorError,
    canonical_bytes,
    content_hash,
    load_json,
    load_schema,
    stable_id,
    utc_now,
    validate_record,
    write_json,
)


# ---------------------------------------------------------------------------
# Graph status enum
# ---------------------------------------------------------------------------

class GraphStatus(str, Enum):
    PLANNING = "planning"
    PENDING = "pending"
    COMMITTING = "committing"
    OPEN = "open"
    SEALED = "sealed"
    CANCELING = "canceling"
    RECOVERY_REQUIRED = "recovery_required"


# ---------------------------------------------------------------------------
# Graph state  (Task 3.1)
# ---------------------------------------------------------------------------

class GraphState:
    """Persistent graph state: envelope, revision, digest, status, limits, authority."""

    def __init__(
        self,
        envelope: dict[str, Any],
        graph_revision: int = 1,
        graph_digest: str = "0" * 64,
        status: str = GraphStatus.PLANNING,
        terminal_barrier: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        expansion_ledger: list[str] | None = None,
        current_goal_judge_id: str | None = None,
        active_planning_authority_id: str | None = None,
        expansion_slot: ExpansionSlot | None = None,
    ) -> None:
        if not isinstance(envelope, dict):
            raise OrchestratorError("envelope must be a dict")
        self.envelope = envelope
        self.graph_revision = graph_revision
        self.graph_digest = graph_digest
        self.status = status
        self.terminal_barrier = terminal_barrier or {}
        self.limits = limits or envelope.get("limits", {})
        self.expansion_ledger = expansion_ledger or []
        self.current_goal_judge_id = current_goal_judge_id
        self.active_planning_authority_id = active_planning_authority_id
        self.expansion_slot = expansion_slot or ExpansionSlot()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}
        self._batches: dict[str, dict[str, Any]] = {}
        self._verifier_assignments: dict[str, dict[str, Any]] = {}
        self._repair_gate_history: list[dict[str, Any]] = []
        self._expansions: dict[str, dict[str, Any]] = {}
        self._generations: list[dict[str, Any]] = []
        self._terminal_outcomes: dict[str, dict[str, Any]] = {}
        self._verifier_authority_bindings: dict[str, dict[str, Any]] = {}
        self._authorities: dict[str, dict[str, Any]] = {}
        self._target_acceptances: dict[str, dict[str, Any]] = {}

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "envelope": self.envelope,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "status": self.status,
            "terminal_barrier": self.terminal_barrier,
            "limits": self.limits,
            "expansion_ledger": self.expansion_ledger,
            "current_goal_judge_id": self.current_goal_judge_id,
            "active_planning_authority_id": self.active_planning_authority_id,
            "expansion_slot": self.expansion_slot.to_dict(),
            "jobs": self._jobs,
            "edges": self._edges,
            "batches": self._batches,
            "verifier_assignments": self._verifier_assignments,
            "repair_gate_history": self._repair_gate_history,
            "expansions": self._expansions,
            "generations": self._generations,
            "terminal_outcomes": self._terminal_outcomes,
            "verifier_authority_bindings": self._verifier_authority_bindings,
            "authorities": self._authorities,
            "target_acceptances": self._target_acceptances,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphState:
        slot_data = data.get("expansion_slot")
        expansion_slot = ExpansionSlot.from_dict(slot_data) if slot_data else None
        gs = cls(
            envelope=data["envelope"],
            graph_revision=data.get("graph_revision", 1),
            graph_digest=data.get("graph_digest", "0" * 64),
            status=data.get("status", GraphStatus.PLANNING),
            terminal_barrier=data.get("terminal_barrier"),
            limits=data.get("limits"),
            expansion_ledger=data.get("expansion_ledger"),
            current_goal_judge_id=data.get("current_goal_judge_id"),
            active_planning_authority_id=data.get("active_planning_authority_id"),
            expansion_slot=expansion_slot,
        )
        gs._jobs = data.get("jobs", {})
        gs._edges = data.get("edges", {})
        gs._batches = data.get("batches", {})
        gs._verifier_assignments = data.get("verifier_assignments", {})
        gs._repair_gate_history = data.get("repair_gate_history", [])
        gs._expansions = data.get("expansions", {})
        gs._generations = data.get("generations", [])
        gs._terminal_outcomes = data.get("terminal_outcomes", {})
        gs._verifier_authority_bindings = data.get("verifier_authority_bindings", {})
        gs._authorities = data.get("authorities", {})
        gs._target_acceptances = data.get("target_acceptances", {})
        return gs

    def save(self, path: Path) -> None:
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> GraphState:
        data = load_json(path)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Job record  (Task 3.2)
# ---------------------------------------------------------------------------

class JobRecord:
    """Append-only job definition with role, purpose, graph generation, and authority."""

    def __init__(
        self,
        job_id: str,
        role: str,
        purpose_key: str,
        graph_generation: int,
        expansion_origin: str,
        authority_id: str,
        context_snapshot_id: str,
        activation_id: str | None = None,
        repair_relationship: dict[str, str] | None = None,
        title: str = "",
        status: str = "pending",
    ) -> None:
        self.job_id = job_id
        self.role = role
        self.purpose_key = purpose_key
        self.graph_generation = graph_generation
        self.expansion_origin = expansion_origin
        self.authority_id = authority_id
        self.context_snapshot_id = context_snapshot_id
        self.activation_id = activation_id
        self.repair_relationship = repair_relationship
        self.title = title or f"{role}-{purpose_key}"
        self.status = status
        self.created_at = utc_now()
        self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "job_id": self.job_id,
            "role": self.role,
            "purpose_key": self.purpose_key,
            "graph_generation": self.graph_generation,
            "expansion_origin": self.expansion_origin,
            "authority_id": self.authority_id,
            "context_snapshot_id": self.context_snapshot_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.activation_id is not None:
            d["activation_id"] = self.activation_id
        if self.repair_relationship is not None:
            d["repair_relationship"] = self.repair_relationship
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        return cls(
            job_id=data["job_id"],
            role=data["role"],
            purpose_key=data["purpose_key"],
            graph_generation=data["graph_generation"],
            expansion_origin=data["expansion_origin"],
            authority_id=data["authority_id"],
            context_snapshot_id=data.get("context_snapshot_id", ""),
            activation_id=data.get("activation_id"),
            repair_relationship=data.get("repair_relationship"),
            title=data.get("title", ""),
            status=data.get("status", "pending"),
        )


# ---------------------------------------------------------------------------
# Edge record  (Task 3.2)
# ---------------------------------------------------------------------------

class EdgeRecord:
    """Typed dependency edge between two jobs."""

    VALID_EDGE_TYPES = frozenset({
        "success", "execution", "all-settled", "report",
        "verification", "batch", "cycle",
    })

    def __init__(
        self,
        edge_id: str,
        source_job_id: str,
        target_job_id: str,
        edge_type: str,
        graph_revision: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if edge_type not in self.VALID_EDGE_TYPES:
            raise OrchestratorError(
                f"invalid edge_type {edge_type!r}; must be one of {sorted(self.VALID_EDGE_TYPES)}"
            )
        self.edge_id = edge_id
        self.source_job_id = source_job_id
        self.target_job_id = target_job_id
        self.edge_type = edge_type
        self.graph_revision = graph_revision
        self.metadata = metadata or {}
        self.created_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "edge_id": self.edge_id,
            "source_job_id": self.source_job_id,
            "target_job_id": self.target_job_id,
            "edge_type": self.edge_type,
            "graph_revision": self.graph_revision,
            "created_at": self.created_at,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeRecord:
        return cls(
            edge_id=data["edge_id"],
            source_job_id=data["source_job_id"],
            target_job_id=data["target_job_id"],
            edge_type=data["edge_type"],
            graph_revision=data["graph_revision"],
            metadata=data.get("metadata"),
        )


# ---------------------------------------------------------------------------
# Verifier assignment  (Task 3.2)
# ---------------------------------------------------------------------------

class VerifierRecord:
    """Verifier assignment binding a verifier job to a target gate revision."""

    def __init__(
        self,
        assignment_id: str,
        target_job_id: str,
        target_gate_revision: int,
        verifier_job_id: str,
        run_id: str,
        cycle_id: str,
        status: str = "assigned",
        evidence_refs: list[str] | None = None,
    ) -> None:
        self.assignment_id = assignment_id
        self.target_job_id = target_job_id
        self.target_gate_revision = target_gate_revision
        self.verifier_job_id = verifier_job_id
        self.run_id = run_id
        self.cycle_id = cycle_id
        self.status = status
        self.evidence_refs = evidence_refs or []
        self.assigned_at = utc_now()
        self.completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "assignment_id": self.assignment_id,
            "target_job_id": self.target_job_id,
            "target_gate_revision": self.target_gate_revision,
            "verifier_job_id": self.verifier_job_id,
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "status": self.status,
            "evidence_refs": self.evidence_refs,
            "assigned_at": self.assigned_at,
        }
        if self.completed_at is not None:
            d["completed_at"] = self.completed_at
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifierRecord:
        v = cls(
            assignment_id=data["assignment_id"],
            target_job_id=data["target_job_id"],
            target_gate_revision=data["target_gate_revision"],
            verifier_job_id=data["verifier_job_id"],
            run_id=data["run_id"],
            cycle_id=data["cycle_id"],
            status=data.get("status", "assigned"),
            evidence_refs=data.get("evidence_refs"),
        )
        v.completed_at = data.get("completed_at")
        return v


# ---------------------------------------------------------------------------
# Repair gate history  (Task 3.2)
# ---------------------------------------------------------------------------

class RepairGateRecord:
    """Append-only repair gate revision history entry."""

    def __init__(
        self,
        history_id: str,
        target_job_id: str,
        revision: int,
        repair_job_id: str,
        finding_id: str,
        status: str,
        evidence_refs: list[str] | None = None,
    ) -> None:
        self.history_id = history_id
        self.target_job_id = target_job_id
        self.revision = revision
        self.repair_job_id = repair_job_id
        self.finding_id = finding_id
        self.status = status
        self.evidence_refs = evidence_refs or []
        self.recorded_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "history_id": self.history_id,
            "target_job_id": self.target_job_id,
            "revision": self.revision,
            "repair_job_id": self.repair_job_id,
            "finding_id": self.finding_id,
            "status": self.status,
            "evidence_refs": self.evidence_refs,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairGateRecord:
        return cls(
            history_id=data["history_id"],
            target_job_id=data["target_job_id"],
            revision=data["revision"],
            repair_job_id=data["repair_job_id"],
            finding_id=data["finding_id"],
            status=data["status"],
            evidence_refs=data.get("evidence_refs"),
        )


# ---------------------------------------------------------------------------
# Graph-level helpers for managing records
# ---------------------------------------------------------------------------

def add_job_to_graph(gs: GraphState, record: dict[str, Any]) -> None:
    """Append a job record to the graph (no overwrite)."""
    job_id = record.get("job_id")
    if not job_id:
        raise OrchestratorError("job record missing job_id")
    if job_id in gs._jobs:
        raise OrchestratorError(f"job {job_id} already exists; append-only")
    validate_record("job-definition", record)
    gs._jobs[job_id] = record


def add_edge_to_graph(gs: GraphState, record: dict[str, Any]) -> None:
    """Append an edge record to the graph (no overwrite)."""
    edge_id = record.get("edge_id")
    if not edge_id:
        raise OrchestratorError("edge record missing edge_id")
    if edge_id in gs._edges:
        raise OrchestratorError(f"edge {edge_id} already exists; append-only")
    validate_record("typed-dependency-edge", record)
    gs._edges[edge_id] = record


def add_verifier_assignment(gs: GraphState, record: dict[str, Any]) -> None:
    """Append a verifier assignment to the graph."""
    assignment_id = record.get("assignment_id")
    if not assignment_id:
        raise OrchestratorError("verifier assignment missing assignment_id")
    if assignment_id in gs._verifier_assignments:
        raise OrchestratorError(f"verifier assignment {assignment_id} already exists; append-only")
    validate_record("verifier-assignment", record)
    gs._verifier_assignments[assignment_id] = record


def add_repair_gate(gs: GraphState, record: dict[str, Any]) -> None:
    """Append a repair gate history entry."""
    history_id = record.get("history_id")
    if not history_id:
        raise OrchestratorError("repair gate record missing history_id")
    for existing in gs._repair_gate_history:
        if existing.get("history_id") == history_id:
            raise OrchestratorError(f"repair gate {history_id} already exists; append-only")
    validate_record("repair-gate-history", record)
    gs._repair_gate_history.append(record)


def add_expansion(gs: GraphState, record: dict[str, Any]) -> None:
    """Append an expansion record."""
    expansion_id = record.get("expansion_id")
    if not expansion_id:
        raise OrchestratorError("expansion record missing expansion_id")
    if expansion_id in gs._expansions:
        raise OrchestratorError(f"expansion {expansion_id} already exists; append-only")
    gs._expansions[expansion_id] = record
    gs.expansion_ledger.append(expansion_id)


def add_generation(gs: GraphState, record: dict[str, Any]) -> None:
    """Append a graph generation record."""
    generation_id = record.get("generation_id")
    revision = record.get("graph_revision")
    if not generation_id:
        raise OrchestratorError("graph generation missing generation_id")
    if any(
        existing.get("generation_id") == generation_id
        or existing.get("graph_revision") == revision
        for existing in gs._generations
    ):
        raise OrchestratorError(
            f"graph generation {generation_id!r} or revision {revision!r} already exists; append-only"
        )
    validate_record("graph-generation", record)
    gs._generations.append(record)


def add_batch(gs: GraphState, record: dict[str, Any]) -> None:
    """Append a batch record."""
    batch_id = record.get("batch_id")
    if not batch_id:
        raise OrchestratorError("batch record missing batch_id")
    if batch_id in gs._batches:
        raise OrchestratorError(f"batch {batch_id} already exists; append-only")
    gs._batches[batch_id] = record


def get_job(gs: GraphState, job_id: str) -> dict[str, Any] | None:
    return gs._jobs.get(job_id)


def get_jobs(gs: GraphState) -> dict[str, dict[str, Any]]:
    return dict(gs._jobs)


def get_edges(gs: GraphState) -> dict[str, dict[str, Any]]:
    return dict(gs._edges)


def get_edges_from(gs: GraphState, job_id: str) -> list[dict[str, Any]]:
    return [e for e in gs._edges.values() if e.get("source_job_id") == job_id]


def get_edges_to(gs: GraphState, job_id: str) -> list[dict[str, Any]]:
    return [e for e in gs._edges.values() if e.get("target_job_id") == job_id]


def get_batches(gs: GraphState) -> dict[str, dict[str, Any]]:
    return dict(gs._batches)


def get_verifier_assignments_for_target(
    gs: GraphState, target_job_id: str
) -> list[dict[str, Any]]:
    return [
        v for v in gs._verifier_assignments.values()
        if v.get("target_job_id") == target_job_id
    ]


def get_repair_gate_history_for_target(
    gs: GraphState, target_job_id: str
) -> list[dict[str, Any]]:
    return [
        r for r in gs._repair_gate_history
        if r.get("target_job_id") == target_job_id
    ]


# ---------------------------------------------------------------------------
# Task 3.3: Canonical graph digest computation
# ---------------------------------------------------------------------------

def _collect_immutable_graph_payload(gs: GraphState) -> dict[str, Any]:
    """Collect only immutable topology and authority fields for digest."""
    return {
        "envelope": gs.envelope,
        "jobs": {
            k: {
                "job_id": v["job_id"],
                "role": v["role"],
                "purpose_key": v["purpose_key"],
                "graph_generation": v["graph_generation"],
                "expansion_origin": v["expansion_origin"],
                "authority_id": v["authority_id"],
            }
            for k, v in sorted(gs._jobs.items())
        },
        "edges": {
            k: {
                "edge_id": v["edge_id"],
                "source_job_id": v["source_job_id"],
                "target_job_id": v["target_job_id"],
                "edge_type": v["edge_type"],
                "graph_revision": v["graph_revision"],
            }
            for k, v in sorted(gs._edges.items())
        },
        "verifier_assignments": {
            k: {
                "assignment_id": v["assignment_id"],
                "target_job_id": v["target_job_id"],
                "target_gate_revision": v["target_gate_revision"],
                "verifier_job_id": v["verifier_job_id"],
            }
            for k, v in sorted(gs._verifier_assignments.items())
        },
        "repair_gate_history": [
            {
                "history_id": r["history_id"],
                "target_job_id": r["target_job_id"],
                "revision": r["revision"],
                "repair_job_id": r["repair_job_id"],
                "finding_id": r.get("finding_id", ""),
                "status": r["status"],
            }
            for r in sorted(gs._repair_gate_history, key=lambda x: x["history_id"])
        ],
        "batches": {
            k: {
                "batch_id": v["batch_id"],
                "status": v["status"],
                "job_ids": sorted(v.get("job_ids", [])),
            }
            for k, v in sorted(gs._batches.items())
        },
        "current_goal_judge_id": gs.current_goal_judge_id,
        "active_planning_authority_id": gs.active_planning_authority_id,
        "authorities": {
            authority_id: authority
            for authority_id, authority in sorted(gs._authorities.items())
        },
        "limits": gs.limits,
        "terminal_outcomes": {
            k: {
                "outcome_type": v["outcome_type"],
                "graph_revision": v["graph_revision"],
                "graph_digest": v["graph_digest"],
            }
            for k, v in sorted(gs._terminal_outcomes.items())
        },
    }


def compute_graph_digest(gs: GraphState) -> str:
    """Compute SHA-256 over immutable topology and authority, excluding volatile state."""
    payload = _collect_immutable_graph_payload(gs)
    data = canonical_bytes(payload)
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Task 3.4: Deterministic identity generation
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,127}$")


def validate_identity_format(identity: str) -> None:
    """Validate that an identity matches the v6 ID pattern."""
    if not _ID_RE.match(identity):
        raise OrchestratorError(
            f"identity {identity!r} does not match pattern [A-Z][A-Z0-9_-]{{0,127}}"
        )


def generate_expansion_id(
    run_id: str,
    decision_id: str,
    plan_digest: str,
) -> str:
    """Deterministic expansion ID from run, decision, and plan digest."""
    return stable_id("EXP", run_id, decision_id, plan_digest)


def generate_batch_id(
    expansion_id: str,
    batch_index: int,
) -> str:
    """Deterministic batch ID from expansion and batch index."""
    return stable_id("BATCH", expansion_id, str(batch_index))


def generate_decision_id(
    job_id: str,
    response_digest: str,
) -> str:
    """Deterministic decision ID from job and response."""
    return stable_id("DEC", job_id, response_digest)


def generate_global_job_id(
    run_id: str,
    expansion_id: str,
    local_job_id: str,
) -> str:
    """Deterministic global job ID with path-safety.

    stable_id uses lowercase hex; we uppercase to satisfy the v6 ID pattern
    [A-Z][A-Z0-9_-]{0,127}.
    """
    candidate = stable_id("JOB", run_id, expansion_id, local_job_id)
    candidate = candidate[:4] + candidate[4:].upper()
    validate_identity_format(candidate)
    return candidate


def validate_identity_uniqueness(
    candidate: str,
    existing_ids: set[str],
    label: str = "identity",
) -> None:
    """Check for collision with existing identities."""
    if candidate in existing_ids:
        raise OrchestratorError(
            f"{label} collision: {candidate!r} already exists"
        )


# ---------------------------------------------------------------------------
# Task 3.5: Prospective graph validation
# ---------------------------------------------------------------------------

def _collect_all_edges(gs: GraphState, new_edges: list[dict[str, Any]] | None = None) -> list[tuple[str, str]]:
    """Collect all edges as (source, target) tuples."""
    edges = [(e["source_job_id"], e["target_job_id"]) for e in gs._edges.values()]
    if new_edges:
        for e in new_edges:
            edges.append((e["source_job_id"], e["target_job_id"]))
    return edges


def _detect_cycle(edges: list[tuple[str, str]]) -> list[str] | None:
    """Detect cycles in a directed graph. Returns cycle path or None."""
    adj: dict[str, list[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src, []).append(tgt)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    parent: dict[str, str | None] = {}

    for node in adj:
        color[node] = WHITE
        parent[node] = None

    for node in list(adj.keys()):
        if color.get(node, WHITE) != WHITE:
            continue
        stack = [node]
        while stack:
            u = stack[-1]
            if color.get(u, WHITE) == WHITE:
                color[u] = GRAY
                for v in adj.get(u, []):
                    if color.get(v, WHITE) == WHITE:
                        parent[v] = u
                        stack.append(v)
                    elif color.get(v) == GRAY:
                        cycle = [v, u]
                        cur = u
                        while cur != v:
                            cur = parent.get(cur)
                            if cur is None:
                                break
                            cycle.append(cur)
                        cycle.reverse()
                        return cycle
            else:
                stack.pop()
                color[u] = BLACK
    return None


def validate_prospective_graph(
    gs: GraphState,
    new_jobs: list[dict[str, Any]] | None = None,
    new_edges: list[dict[str, Any]] | None = None,
    new_batches: list[dict[str, Any]] | None = None,
    batch_additions: dict[str, list[str]] | None = None,
    new_verifier_assignments: list[dict[str, Any]] | None = None,
    new_repair_gates: list[dict[str, Any]] | None = None,
) -> list[str]:
    """
    Validate a prospective graph (existing + new records).
    Returns a list of error strings; empty means valid.
    """
    errors: list[str] = []
    new_jobs = new_jobs or []
    new_edges = new_edges or []
    new_batches = new_batches or []
    batch_additions = batch_additions or {}
    new_verifier_assignments = new_verifier_assignments or []
    new_repair_gates = new_repair_gates or []

    proposed_job_ids = [j.get("job_id", "") for j in new_jobs]
    if len(proposed_job_ids) != len(set(proposed_job_ids)):
        errors.append("proposed job identities are not unique")
    for job_id in proposed_job_ids:
        try:
            validate_identity_format(job_id)
        except OrchestratorError as exc:
            errors.append(str(exc))
        if job_id in gs._jobs:
            errors.append(f"job identity collision: {job_id!r} already exists")

    proposed_edge_ids = [e.get("edge_id", "") for e in new_edges]
    if len(proposed_edge_ids) != len(set(proposed_edge_ids)):
        errors.append("proposed edge identities are not unique")
    for edge_id in proposed_edge_ids:
        try:
            validate_identity_format(edge_id)
        except OrchestratorError as exc:
            errors.append(str(exc))
        if edge_id in gs._edges:
            errors.append(f"edge identity collision: {edge_id!r} already exists")

    all_job_ids = set(gs._jobs.keys()) | set(proposed_job_ids)
    all_edges = _collect_all_edges(gs, new_edges)

    # 1. Dependency validity: edges must reference existing jobs
    for e in new_edges:
        src = e["source_job_id"]
        tgt = e["target_job_id"]
        if src not in all_job_ids:
            errors.append(f"edge {e.get('edge_id', '?')}: source_job_id {src!r} not found")
        if tgt not in all_job_ids:
            errors.append(f"edge {e.get('edge_id', '?')}: target_job_id {tgt!r} not found")

    # 2. Existing edges validity
    for eid, e in gs._edges.items():
        if e["source_job_id"] not in all_job_ids:
            errors.append(f"edge {eid}: source_job_id {e['source_job_id']!r} not found")
        if e["target_job_id"] not in all_job_ids:
            errors.append(f"edge {eid}: target_job_id {e['target_job_id']!r} not found")

    # 3. Parent relationships and hierarchy cycles.
    hierarchy: list[tuple[str, str]] = []
    for existing in gs._jobs.values():
        origin = existing.get("expansion_origin")
        if origin and origin != "ROOT":
            hierarchy.append((origin, existing["job_id"]))
    for j in new_jobs:
        origin = j.get("expansion_origin")
        if origin and origin not in all_job_ids and origin != "ROOT":
            errors.append(f"job {j['job_id']}: expansion_origin {origin!r} not found")
        if origin and origin != "ROOT":
            hierarchy.append((origin, j["job_id"]))
    hierarchy_cycle = _detect_cycle(hierarchy)
    if hierarchy_cycle is not None:
        errors.append(f"hierarchy cycle detected: {' -> '.join(hierarchy_cycle)}")

    # 4. Activation constraints: activation_id must be unique per job
    seen_activations: set[str] = {
        str(j["activation_id"])
        for j in gs._jobs.values()
        if j.get("activation_id")
    }
    for j in new_jobs:
        aid = j.get("activation_id")
        if aid:
            if aid in seen_activations:
                errors.append(f"job {j['job_id']}: duplicate activation_id {aid!r}")
            seen_activations.add(aid)

    # 5. Repair relationship: target must exist
    for j in new_jobs:
        repair = j.get("repair_relationship")
        if repair:
            target = repair.get("target_job_id")
            if target and target not in all_job_ids:
                errors.append(f"job {j['job_id']}: repair target {target!r} not found")

    # 6. Verifier assignments: target and verifier must exist and be distinct.
    assignment_ids = set(gs._verifier_assignments)
    for v in [*gs._verifier_assignments.values(), *new_verifier_assignments]:
        assignment_id = v.get("assignment_id", "")
        if v in new_verifier_assignments:
            if assignment_id in assignment_ids:
                errors.append(f"verifier assignment {assignment_id!r} already exists")
            assignment_ids.add(assignment_id)
        target = v.get("target_job_id")
        if target and target not in all_job_ids:
            errors.append(f"verifier {assignment_id}: target {target!r} not found")
        verifier = v.get("verifier_job_id")
        if verifier and verifier not in all_job_ids:
            errors.append(f"verifier {assignment_id}: job {verifier!r} not found")
        if target and verifier and target == verifier:
            errors.append(f"verifier {assignment_id}: self-verification is not allowed")

    # 7. Graph and hierarchy cycles
    cycle = _detect_cycle(all_edges)
    if cycle is not None:
        errors.append(f"dependency cycle detected: {' -> '.join(cycle)}")

    # 8. Role contracts: role must be non-empty
    for j in new_jobs:
        if not j.get("role"):
            errors.append(f"job {j['job_id']}: role is empty")
        if not j.get("purpose_key"):
            errors.append(f"job {j['job_id']}: purpose_key is empty")

    # 9. Batch membership: additions are append-only and only open batches accept them.
    for bid, batch in gs._batches.items():
        for jid in batch.get("job_ids", []):
            if jid not in all_job_ids:
                errors.append(f"batch {bid}: job {jid!r} not found")
    seen_batches = set(gs._batches)
    for batch in new_batches:
        batch_id = batch.get("batch_id", "")
        if batch_id in seen_batches:
            errors.append(f"batch identity collision: {batch_id!r} already exists")
        seen_batches.add(batch_id)
        for job_id in batch.get("job_ids", []):
            if job_id not in all_job_ids:
                errors.append(f"batch {batch_id}: job {job_id!r} not found")
    for batch_id, job_ids in batch_additions.items():
        batch = gs._batches.get(batch_id)
        if batch is None:
            errors.append(f"batch {batch_id!r} not found for membership addition")
            continue
        if batch.get("status") != "open":
            errors.append(
                f"batch {batch_id!r} is {batch.get('status')!r}; only open batches accept members"
            )
        for job_id in job_ids:
            if job_id not in all_job_ids:
                errors.append(f"batch {batch_id}: job {job_id!r} not found")
            if job_id in batch.get("job_ids", []):
                errors.append(f"batch {batch_id}: job {job_id!r} is already a member")

    # 10. Repair records must advance one target monotonically and reference jobs.
    latest_repairs: dict[str, int] = {}
    for record in [*gs._repair_gate_history, *new_repair_gates]:
        target = record.get("target_job_id", "")
        repair_job = record.get("repair_job_id", "")
        revision = record.get("revision", 0)
        if target not in all_job_ids:
            errors.append(f"repair gate {record.get('history_id', '?')}: target {target!r} not found")
        if repair_job not in all_job_ids:
            errors.append(
                f"repair gate {record.get('history_id', '?')}: repair job {repair_job!r} not found"
            )
        previous = latest_repairs.get(target, 0)
        if revision <= previous:
            errors.append(
                f"repair gate {record.get('history_id', '?')}: revision {revision} does not advance {previous}"
            )
        latest_repairs[target] = max(previous, revision)

    # 11. Goal reachability: at least one path from root(s) to each non-root job
    # (simplified: check that every new job has at least one edge in or is root)
    root_jobs = {j["job_id"] for j in new_jobs if not j.get("expansion_origin")}
    non_root_new = {j["job_id"] for j in new_jobs if j.get("expansion_origin")}
    targets_with_edges = {tgt for _, tgt in all_edges}
    for jid in non_root_new:
        if jid not in targets_with_edges:
            # Check if it has no edges at all (standalone)
            has_out = any(src == jid for src, _ in all_edges)
            if not has_out:
                errors.append(f"job {jid}: unreachable (no incoming or outgoing edges)")

    return errors


# ---------------------------------------------------------------------------
# Task 3.6: Immutable ceilings enforcement
# ---------------------------------------------------------------------------

def validate_limits(
    gs: GraphState,
    proposed_job_count: int = 0,
    proposed_edge_count: int = 0,
    proposed_expansion_depth: int = 0,
    proposed_purpose_count: int = 0,
    proposed_hypothesis_count: int = 0,
    proposed_batch_count: int = 0,
    proposed_concurrency: int = 0,
    proposed_external_effects: int = 0,
    proposed_prompt_size: int = 0,
    proposed_plan_size: int = 0,
    estimated_time_seconds: float = 0,
    estimated_cost: float = 0,
    proposed_jobs: list[dict[str, Any]] | None = None,
    proposed_edges: list[dict[str, Any]] | None = None,
    proposed_batches: list[dict[str, Any]] | None = None,
) -> list[str]:
    """
    Validate proposed expansion against immutable ceilings.
    Returns a list of error strings; empty means within limits.
    Whole-plan rejection: if any single limit is exceeded, the plan is rejected.
    """
    errors: list[str] = []
    limits = gs.limits or {}
    envelope = gs.envelope or {}
    campaign_limits = envelope.get("limits", {})
    proposed_jobs = proposed_jobs or []
    proposed_edges = proposed_edges or []
    proposed_batches = proposed_batches or []
    if proposed_jobs:
        proposed_job_count = len(proposed_jobs)
    if proposed_edges:
        proposed_edge_count = len(proposed_edges)
    if proposed_batches:
        proposed_batch_count = sum(
            1 for batch in proposed_batches if batch.get("status", "open") == "open"
        )

    total_jobs = len(gs._jobs) + proposed_job_count
    max_total_jobs = campaign_limits.get("max_total_jobs")
    if max_total_jobs is not None and total_jobs > max_total_jobs:
        errors.append(
            f"total jobs limit exceeded: {total_jobs} > {max_total_jobs}"
        )

    max_jobs_per_cycle = campaign_limits.get("max_jobs_per_cycle")
    if max_jobs_per_cycle is not None and proposed_job_count > max_jobs_per_cycle:
        errors.append(
            f"jobs per expansion limit exceeded: {proposed_job_count} > {max_jobs_per_cycle}"
        )

    max_cycles = campaign_limits.get("max_cycles")
    if max_cycles is not None:
        cycle_count = len(gs._generations) // 2 + 1  # rough estimate
        if cycle_count > max_cycles:
            errors.append(
                f"cycle limit exceeded: {cycle_count} > {max_cycles}"
            )

    max_vertices = limits.get("max_vertices")
    if max_vertices is not None and total_jobs > max_vertices:
        errors.append(
            f"graph vertices limit exceeded: {total_jobs} > {max_vertices}"
        )

    total_edges = len(gs._edges) + proposed_edge_count
    max_edges = limits.get("max_edges")
    if max_edges is not None and total_edges > max_edges:
        errors.append(
            f"graph edges limit exceeded: {total_edges} > {max_edges}"
        )

    max_depth = limits.get("max_expansion_depth")
    if max_depth is not None and proposed_expansion_depth > max_depth:
        errors.append(
            f"expansion depth limit exceeded: {proposed_expansion_depth} > {max_depth}"
        )

    fan_out = limits.get("fan_out_limit")
    if fan_out is not None and proposed_job_count > fan_out:
        errors.append(
            f"fan-out limit exceeded: {proposed_job_count} > {fan_out}"
        )

    # Concurrency limit
    max_concurrency = limits.get("max_concurrency")
    if max_concurrency is not None and proposed_concurrency > max_concurrency:
        errors.append(
            f"concurrency limit exceeded: {proposed_concurrency} > {max_concurrency}"
        )

    # External effects limit
    max_external = limits.get("max_external_effects")
    if max_external is not None and proposed_external_effects > max_external:
        errors.append(
            f"external effects limit exceeded: {proposed_external_effects} > {max_external}"
        )

    # Prompt size limit
    max_prompt = limits.get("max_prompt_size")
    if max_prompt is not None and proposed_prompt_size > max_prompt:
        errors.append(
            f"prompt size limit exceeded: {proposed_prompt_size} > {max_prompt}"
        )

    # Plan size limit
    max_plan = limits.get("max_plan_size")
    if max_plan is not None and proposed_plan_size > max_plan:
        errors.append(
            f"plan size limit exceeded: {proposed_plan_size} > {max_plan}"
        )

    # Time limit
    max_time = limits.get("max_time_seconds")
    if max_time is not None and estimated_time_seconds > max_time:
        errors.append(
            f"time limit exceeded: {estimated_time_seconds:.1f}s > {max_time}s"
        )

    # Cost limit
    max_cost = limits.get("max_cost")
    if max_cost is not None and estimated_cost > max_cost:
        errors.append(
            f"cost limit exceeded: {estimated_cost:.2f} > {max_cost:.2f}"
        )

    # Hypotheses per finding group
    max_hypotheses = limits.get("max_hypotheses_per_group")
    if max_hypotheses is not None and proposed_hypothesis_count > max_hypotheses:
        errors.append(
            f"hypotheses per group limit exceeded: {proposed_hypothesis_count} > {max_hypotheses}"
        )

    # Open batches limit
    max_open_batches = limits.get("max_open_batches")
    if max_open_batches is not None:
        open_count = sum(
            1 for b in gs._batches.values()
            if b.get("status") == "open"
        ) + proposed_batch_count
        if open_count > max_open_batches:
            errors.append(
                f"open batches limit exceeded: {open_count} > {max_open_batches}"
            )

    # Dependencies per job limit
    max_deps = limits.get("max_dependencies_per_job")
    if max_deps is not None:
        dep_counts: dict[str, int] = {}
        for e in [*gs._edges.values(), *proposed_edges]:
            dep_counts[e["target_job_id"]] = dep_counts.get(e["target_job_id"], 0) + 1
        for jid, count in dep_counts.items():
            if count > max_deps:
                errors.append(
                    f"dependencies per job limit exceeded for {jid}: {count} > {max_deps}"
                )

    # Purposes limit
    max_purposes = limits.get("max_unique_purposes")
    if max_purposes is not None:
        purposes = {
            j.get("purpose_key", "")
            for j in [*gs._jobs.values(), *proposed_jobs]
            if j.get("purpose_key")
        }
        if len(purposes) > max_purposes:
            errors.append(
                f"unique purposes limit exceeded: {len(purposes)} > {max_purposes}"
            )

    max_repeated = limits.get("max_repeated_purpose")
    if max_repeated is not None:
        counts: dict[str, int] = {}
        for job in [*gs._jobs.values(), *proposed_jobs]:
            purpose = job.get("purpose_key", "")
            if purpose:
                counts[purpose] = counts.get(purpose, 0) + 1
        for purpose, count in counts.items():
            if count > max_repeated:
                errors.append(
                    f"repeated purpose limit exceeded for {purpose!r}: {count} > {max_repeated}"
                )

    return errors


# ---------------------------------------------------------------------------
# Graph status transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    GraphStatus.PLANNING: {GraphStatus.PENDING, GraphStatus.CANCELING},
    GraphStatus.PENDING: {GraphStatus.COMMITTING, GraphStatus.CANCELING, GraphStatus.RECOVERY_REQUIRED},
    GraphStatus.COMMITTING: {GraphStatus.OPEN, GraphStatus.RECOVERY_REQUIRED, GraphStatus.CANCELING},
    GraphStatus.OPEN: {GraphStatus.PLANNING, GraphStatus.SEALED, GraphStatus.CANCELING, GraphStatus.RECOVERY_REQUIRED},
    GraphStatus.SEALED: set(),
    GraphStatus.CANCELING: {GraphStatus.SEALED, GraphStatus.RECOVERY_REQUIRED},
    GraphStatus.RECOVERY_REQUIRED: {GraphStatus.PLANNING, GraphStatus.COMMITTING, GraphStatus.CANCELING, GraphStatus.SEALED},
}


def transition_graph_status(gs: GraphState, new_status: str) -> None:
    """Validate and apply a graph status transition."""
    current = gs.status
    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise OrchestratorError(
            f"invalid graph status transition: {current!r} -> {new_status!r}; "
            f"allowed: {sorted(allowed)}"
        )
    gs.status = new_status


def advance_graph_revision(gs: GraphState) -> int:
    """Advance the graph revision and recompute digest."""
    gs.graph_revision += 1
    gs.graph_digest = compute_graph_digest(gs)
    return gs.graph_revision


# ---------------------------------------------------------------------------
# Task 8.1: Verifier authority binding
# ---------------------------------------------------------------------------

class VerifierAuthorityBinder:
    """Bind independent Verifier authority to exact target job, condition,
    target gate revision, graph generation, and evidence contract."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs

    def bind_verifier_authority(
        self,
        assignment_id: str,
        target_job_id: str,
        target_gate_revision: int,
        verifier_job_id: str,
        run_id: str,
        cycle_id: str,
        condition_id: str,
        graph_generation: int,
        required_evidence_types: list[str] | None = None,
        required_evidence: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Bind a verifier to an exact target with full authority validation."""
        self.validate_target_identity(target_job_id)
        self.validate_gate_revision(target_job_id, target_gate_revision)
        self.validate_graph_generation(target_job_id, graph_generation)
        self.validate_evidence_contract(
            target_job_id, required_evidence_types or []
        )

        record = {
            "schema_version": SCHEMA_VERSION,
            "assignment_id": assignment_id,
            "target_job_id": target_job_id,
            "target_gate_revision": target_gate_revision,
            "verifier_job_id": verifier_job_id,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "status": "assigned",
            "evidence_refs": [],
            "required_evidence": required_evidence or [],
            "assigned_at": utc_now(),
        }
        add_verifier_assignment(self._gs, record)

        binding_metadata = {
            "condition_id": condition_id,
            "graph_generation": graph_generation,
            "required_evidence_types": required_evidence_types or [],
            "required_evidence": required_evidence or [],
        }
        self._gs._verifier_authority_bindings[assignment_id] = binding_metadata
        return record

    def validate_target_identity(self, target_job_id: str) -> None:
        """Check that the target job exists in the graph."""
        if get_job(self._gs, target_job_id) is None:
            raise OrchestratorError(
                f"verifier authority binding failed: target job {target_job_id!r} not found"
            )

    def validate_gate_revision(
        self, target_job_id: str, target_gate_revision: int
    ) -> None:
        """Check current gate revision matches expected."""
        history = get_repair_gate_history_for_target(self._gs, target_job_id)
        if not history:
            if target_gate_revision != 1:
                raise OrchestratorError(
                    f"gate revision mismatch for {target_job_id}: "
                    f"expected initial revision 1, got {target_gate_revision}"
                )
            return
        current_revision = max(r["revision"] for r in history)
        if target_gate_revision != current_revision:
            raise OrchestratorError(
                f"gate revision mismatch for {target_job_id}: "
                f"expected {current_revision}, got {target_gate_revision}"
            )

    def validate_graph_generation(
        self, target_job_id: str, graph_generation: int
    ) -> None:
        """Check that graph generation matches the target job's generation."""
        job = get_job(self._gs, target_job_id)
        if job is not None and job.get("graph_generation") != graph_generation:
            raise OrchestratorError(
                f"graph generation mismatch for {target_job_id}: "
                f"job has {job.get('graph_generation')}, got {graph_generation}"
            )

    def validate_evidence_contract(
        self, target_job_id: str, required_evidence_types: list[str]
    ) -> None:
        """Check that required evidence types are satisfied (placeholder for contract)."""
        if not required_evidence_types:
            return
        existing = get_repair_gate_history_for_target(self._gs, target_job_id)
        if not existing and required_evidence_types:
            raise OrchestratorError(
                f"evidence contract not satisfied for {target_job_id}: "
                f"no history found for required types {required_evidence_types}"
            )


# ---------------------------------------------------------------------------
# Task 8.2: Verification result applier
# ---------------------------------------------------------------------------

class VerificationResultApplier:
    """Apply verification results only to the exact current target gate,
    rejecting cross-target collisions, self-approval, stale revisions,
    unauthorized Verifiers, and missing required evidence."""

    VALID_VERDICTS = frozenset({"pass", "fail", "unavailable", "unknown", "not-run"})

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs

    def apply_verification_result(
        self,
        assignment_id: str,
        verdict: str,
        evidence_refs: list[str] | None = None,
        condition_result_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply a verification result to the exact target gate."""
        if verdict not in self.VALID_VERDICTS:
            raise OrchestratorError(
                f"invalid verdict {verdict!r}; must be one of {sorted(self.VALID_VERDICTS)}"
            )
        assignment = self._gs._verifier_assignments.get(assignment_id)
        if assignment is None:
            raise OrchestratorError(
                f"verification result application failed: assignment {assignment_id!r} not found"
            )

        target_job_id = assignment["target_job_id"]
        verifier_job_id = assignment["verifier_job_id"]
        target_gate_revision = assignment["target_gate_revision"]

        self.reject_cross_target(assignment_id, target_job_id)
        self.reject_self_approval(target_job_id, verifier_job_id)
        self.reject_stale_revision(target_job_id, target_gate_revision)
        self.reject_unauthorized_verifier(verifier_job_id)
        self.reject_missing_evidence(assignment, evidence_refs or [])

        assignment["status"] = "completed"
        assignment["completed_at"] = utc_now()
        assignment["verdict"] = verdict
        assignment["evidence_refs"] = evidence_refs or []

        result_record = {
            "schema_version": SCHEMA_VERSION,
            "assignment_id": assignment_id,
            "target_job_id": target_job_id,
            "target_gate_revision": target_gate_revision,
            "verifier_job_id": verifier_job_id,
            "verdict": verdict,
            "evidence_refs": evidence_refs or [],
            "recorded_at": utc_now(),
        }
        if condition_result_id is not None:
            result_record["condition_result_id"] = condition_result_id
        return result_record

    def reject_cross_target(
        self, assignment_id: str, target_job_id: str
    ) -> None:
        """Reject results that reference a different target than the assignment."""
        assignment = self._gs._verifier_assignments.get(assignment_id)
        if assignment is None:
            return
        if assignment.get("target_job_id") != target_job_id:
            raise OrchestratorError(
                f"cross-target collision: assignment {assignment_id} targets "
                f"{assignment.get('target_job_id')}, not {target_job_id}"
            )

    def reject_self_approval(
        self, target_job_id: str, verifier_job_id: str
    ) -> None:
        """Reject a verifier from approving its own target."""
        if target_job_id == verifier_job_id:
            raise OrchestratorError(
                f"self-approval rejected: verifier {verifier_job_id} cannot "
                f"approve its own target {target_job_id}"
            )

    def reject_stale_revision(
        self, target_job_id: str, target_gate_revision: int
    ) -> None:
        """Reject results for a stale gate revision."""
        history = get_repair_gate_history_for_target(self._gs, target_job_id)
        current_revision = max((r["revision"] for r in history), default=0)
        if target_gate_revision < current_revision:
            raise OrchestratorError(
                f"stale revision rejected for {target_job_id}: "
                f"gate is at revision {current_revision}, result is for "
                f"revision {target_gate_revision}"
            )

    def reject_unauthorized_verifier(self, verifier_job_id: str) -> None:
        """Reject verifiers not registered in the graph."""
        job = get_job(self._gs, verifier_job_id)
        if job is None:
            raise OrchestratorError(
                f"unauthorized verifier {verifier_job_id}: not found in graph"
            )
        role = job.get("role", "")
        if role != "verifier":
            raise OrchestratorError(
                f"unauthorized verifier {verifier_job_id}: role is {role!r}, "
                f"expected 'verifier'"
            )

    def reject_missing_evidence(
        self, assignment: dict[str, Any], evidence_refs: list[str]
    ) -> None:
        """Reject results with missing required evidence."""
        assignment_id = assignment.get("assignment_id", "")
        binding = self._gs._verifier_authority_bindings.get(assignment_id, {})
        required_artifacts = (
            assignment.get("required_evidence")
            or binding.get("required_evidence", [])
        )
        if required_artifacts:
            for artifact in required_artifacts:
                artifact_ref = artifact.get("artifact_ref", "")
                artifact_digest = artifact.get("artifact_digest", "")
                if artifact_ref not in evidence_refs:
                    raise OrchestratorError(
                        f"missing required evidence artifact for assignment "
                        f"{assignment_id}: expected ref {artifact_ref!r} "
                        f"with digest {artifact_digest[:16]}..."
                    )
            return
        required = binding.get("required_evidence_types", [])
        if not required:
            return
        if not evidence_refs:
            raise OrchestratorError(
                f"missing evidence for assignment "
                f"{assignment_id}: "
                f"required types {required}"
            )


# ---------------------------------------------------------------------------
# Task 8.3: Verdict tracker (execution separate from verdict)
# ---------------------------------------------------------------------------

class VerdictTracker:
    """Keep Verifier execution completion separate from target pass, fail,
    unavailable, unknown, or not-run verdicts so Architect review can follow
    non-passing checks."""

    VALID_VERDICTS = frozenset({"pass", "fail", "unavailable", "unknown", "not-run"})

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs
        self._execution_completions: dict[str, dict[str, Any]] = {}
        self._target_verdicts: dict[str, dict[str, Any]] = {}

    def record_execution_completion(
        self,
        assignment_id: str,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        """Record that verifier execution completed (separate from verdict)."""
        assignment = self._gs._verifier_assignments.get(assignment_id)
        if assignment is None:
            raise OrchestratorError(
                f"execution completion failed: assignment {assignment_id!r} not found"
            )
        timestamp = completed_at or utc_now()
        assignment["status"] = "completed"
        assignment["completed_at"] = timestamp
        record = {
            "assignment_id": assignment_id,
            "target_job_id": assignment["target_job_id"],
            "verifier_job_id": assignment["verifier_job_id"],
            "completed_at": timestamp,
        }
        self._execution_completions[assignment_id] = record
        return record

    def record_target_verdict(
        self,
        assignment_id: str,
        verdict: str,
        evidence_refs: list[str] | None = None,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        """Record a target verdict (pass, fail, unavailable, unknown, not-run)."""
        if verdict not in self.VALID_VERDICTS:
            raise OrchestratorError(
                f"invalid verdict {verdict!r}; must be one of {sorted(self.VALID_VERDICTS)}"
            )
        assignment = self._gs._verifier_assignments.get(assignment_id)
        if assignment is None:
            raise OrchestratorError(
                f"verdict recording failed: assignment {assignment_id!r} not found"
            )
        record = {
            "assignment_id": assignment_id,
            "target_job_id": assignment["target_job_id"],
            "target_gate_revision": assignment["target_gate_revision"],
            "verifier_job_id": assignment["verifier_job_id"],
            "verdict": verdict,
            "evidence_refs": evidence_refs or [],
            "recorded_at": recorded_at or utc_now(),
        }
        self._target_verdicts[assignment_id] = record
        return record

    def validate_verdict_separation(self, assignment_id: str) -> bool:
        """Ensure execution completion and verdict are tracked separately."""
        has_execution = assignment_id in self._execution_completions
        has_verdict = assignment_id in self._target_verdicts
        if has_execution and has_verdict:
            exec_record = self._execution_completions[assignment_id]
            verdict_record = self._target_verdicts[assignment_id]
            if exec_record.get("completed_at") == verdict_record.get("recorded_at"):
                raise OrchestratorError(
                    f"verdict separation violated for {assignment_id}: "
                    f"execution and verdict timestamps must differ"
                )
        return has_execution or has_verdict

    def get_execution_completion(
        self, assignment_id: str
    ) -> dict[str, Any] | None:
        return self._execution_completions.get(assignment_id)

    def get_target_verdict(
        self, assignment_id: str
    ) -> dict[str, Any] | None:
        return self._target_verdicts.get(assignment_id)


# ---------------------------------------------------------------------------
# Task 8.4: Repair round appender
# ---------------------------------------------------------------------------

class RepairRoundAppender:
    """Allow an authorized expansion to append repair work, a fresh Verifier,
    and the next gate revision for a repair-required or blocked target."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs

    def append_repair_round(
        self,
        target_job_id: str,
        repair_job_id: str,
        finding_id: str,
        evidence_refs: list[str] | None = None,
        authorization_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a repair round with fresh verifier and next gate revision."""
        self.validate_repair_authority(target_job_id, authorization_id)

        history = get_repair_gate_history_for_target(self._gs, target_job_id)
        current_revision = max((r["revision"] for r in history), default=0) + 1

        gate_record = self.create_next_gate_revision(
            target_job_id, current_revision, repair_job_id, finding_id,
            evidence_refs or []
        )
        return gate_record

    def validate_repair_authority(
        self, target_job_id: str, authorization_id: str | None
    ) -> None:
        """Check that the expansion has authorization to append a repair round."""
        job = get_job(self._gs, target_job_id)
        if job is None:
            raise OrchestratorError(
                f"repair authority validation failed: target {target_job_id!r} not found"
            )
        if authorization_id is not None:
            if authorization_id not in self._gs.expansion_ledger:
                raise OrchestratorError(
                    f"repair authority rejected: {authorization_id!r} not in "
                    f"expansion ledger"
                )

    def create_next_gate_revision(
        self,
        target_job_id: str,
        revision: int,
        repair_job_id: str,
        finding_id: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        """Create the next gate revision record."""
        raw_id = stable_id("RGH", target_job_id, str(revision))
        history_id = raw_id[:4] + raw_id[4:].upper()
        record = {
            "schema_version": SCHEMA_VERSION,
            "history_id": history_id,
            "target_job_id": target_job_id,
            "revision": revision,
            "repair_job_id": repair_job_id,
            "finding_id": finding_id,
            "status": "applied",
            "evidence_refs": evidence_refs,
            "recorded_at": utc_now(),
        }
        add_repair_gate(self._gs, record)
        return record


# ---------------------------------------------------------------------------
# Task 8.5: Target accepter
# ---------------------------------------------------------------------------

class TargetAccepter:
    """Allow a current passing repair-round result to accept the target
    while preserving all earlier claims, findings, repairs, and results."""

    def __init__(self, gs: GraphState) -> None:
        self._gs = gs

    def accept_target(
        self,
        target_job_id: str,
        assignment_id: str,
        verdict: str,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Accept target with current passing repair round, preserving history."""
        self.validate_current_repair(target_job_id, assignment_id)

        if verdict != "pass":
            raise OrchestratorError(
                f"target acceptance requires 'pass' verdict, got {verdict!r}"
            )

        self.preserve_history(target_job_id)

        assignment = self._gs._verifier_assignments.get(assignment_id, {})
        target_gate_revision = assignment.get("target_gate_revision", 0)

        acceptance_record = {
            "schema_version": SCHEMA_VERSION,
            "target_job_id": target_job_id,
            "assignment_id": assignment_id,
            "verdict": verdict,
            "target_gate_revision": target_gate_revision,
            "evidence_refs": evidence_refs or [],
            "accepted_at": utc_now(),
            "history_preserved": True,
        }
        self._gs._target_acceptances[target_job_id] = acceptance_record
        return acceptance_record

    def preserve_history(self, target_job_id: str) -> dict[str, Any]:
        """Keep all earlier claims, findings, repairs, and results."""
        history = get_repair_gate_history_for_target(self._gs, target_job_id)
        assignments = get_verifier_assignments_for_target(self._gs, target_job_id)
        return {
            "target_job_id": target_job_id,
            "repair_gate_count": len(history),
            "verifier_assignment_count": len(assignments),
            "history_ids": [r.get("history_id") for r in history],
            "assignment_ids": [a.get("assignment_id") for a in assignments],
        }

    def validate_current_repair(
        self, target_job_id: str, assignment_id: str
    ) -> None:
        """Check that the current repair round exists and is valid."""
        assignment = self._gs._verifier_assignments.get(assignment_id)
        if assignment is None:
            raise OrchestratorError(
                f"current repair validation failed: assignment {assignment_id!r} not found"
            )
        if assignment.get("target_job_id") != target_job_id:
            raise OrchestratorError(
                f"assignment {assignment_id} targets "
                f"{assignment.get('target_job_id')}, not {target_job_id}"
            )
        history = get_repair_gate_history_for_target(self._gs, target_job_id)
        if not history:
            raise OrchestratorError(
                f"current repair validation failed: no repair history for "
                f"target {target_job_id}"
            )


# ---------------------------------------------------------------------------
# Task 7.1: Planning barrier
# ---------------------------------------------------------------------------

class PlanningBarrier:
    """Quiescent planning barrier for expansion operations."""

    BLOCKING_STATUSES = frozenset({
        GraphStatus.PLANNING,
        GraphStatus.PENDING,
        GraphStatus.COMMITTING,
        GraphStatus.CANCELING,
        GraphStatus.RECOVERY_REQUIRED,
    })

    @staticmethod
    def acquire_planning_barrier(gs: GraphState) -> None:
        """Ensure graph is in quiescent state before expansion planning."""
        if gs.status in PlanningBarrier.BLOCKING_STATUSES:
            raise OrchestratorError(
                f"planning barrier blocked: graph status is {gs.status!r}; "
                f"must be open or sealed"
            )

    @staticmethod
    def validate_no_active_jobs(gs: GraphState) -> None:
        """Check no jobs are currently running or pending dispatch."""
        active_statuses = {"running", "dispatching", "dispatch_pending"}
        for job_id, job in gs._jobs.items():
            if job.get("status") in active_statuses:
                raise OrchestratorError(
                    f"planning barrier blocked: job {job_id} is {job.get('status')!r}"
                )

    @staticmethod
    def validate_no_pending_dispatch(gs: GraphState) -> None:
        """Check no edges have pending dispatch and no unlaunched prepared dispatches exist."""
        for edge_id, edge in gs._edges.items():
            if edge.get("dispatch_status") == "pending":
                raise OrchestratorError(
                    f"planning barrier blocked: edge {edge_id} has pending dispatch"
                )
        for dispatch_id, dispatch in getattr(gs, "_dispatches", {}).items():
            if dispatch.get("status") == "prepared" and not dispatch.get("launched"):
                raise OrchestratorError(
                    f"planning barrier blocked: dispatch {dispatch_id} is prepared but unlaunched"
                )

    @staticmethod
    def validate_single_expansion_slot(gs: GraphState) -> None:
        """Check only one expansion is active (planning, committing, or pending)."""
        active_expansions = 0
        for exp_id, exp in gs._expansions.items():
            exp_status = exp.get("status", "committed")
            if exp_status in {"planning", "committing", "pending"}:
                active_expansions += 1
        if active_expansions > 1:
            raise OrchestratorError(
                f"planning barrier blocked: {active_expansions} active expansions; "
                f"only one allowed"
            )


# ---------------------------------------------------------------------------
# Task 7.2: Next operation selector
# ---------------------------------------------------------------------------

class NextOperationSelector:
    """Selects next operation with expansion priority."""

    @staticmethod
    def select_next_operation(gs: GraphState) -> str:
        """Return next operation type. Expansion takes precedence."""
        for exp_id, exp in gs._expansions.items():
            if exp.get("status") == "pending":
                return "commit_expansion"

        if gs.status == GraphStatus.OPEN:
            return "schedule_jobs"

        if gs.status == GraphStatus.SEALED:
            return "terminal"

        return "none"

    @staticmethod
    def validate_expansion_priority(gs: GraphState, selected_operation: str) -> None:
        """Validate expansion takes precedence over ordinary scheduling."""
        pending_expansions = [
            exp_id for exp_id, exp in gs._expansions.items()
            if exp.get("status") == "pending"
        ]
        if pending_expansions and selected_operation != "commit_expansion":
            raise OrchestratorError(
                f"expansion priority violation: pending expansions {pending_expansions} "
                f"but selected operation is {selected_operation!r}"
            )


# ---------------------------------------------------------------------------
# Task 7.3: Dispatch graph revision validation
# ---------------------------------------------------------------------------

class DispatchValidator:
    """Validates dispatch against current graph revision."""

    @staticmethod
    def validate_dispatch_graph_revision(
        gs: GraphState,
        dispatch_graph_revision: int,
    ) -> None:
        """Check graph revision matches dispatch snapshot."""
        if dispatch_graph_revision != gs.graph_revision:
            raise OrchestratorError(
                f"dispatch graph revision mismatch: dispatch={dispatch_graph_revision} "
                f"current={gs.graph_revision}"
            )

    @staticmethod
    def reject_stale_dispatch(
        gs: GraphState,
        dispatch_graph_revision: int,
        dispatch_digest: str,
    ) -> None:
        """Reject dispatch if graph topology has changed."""
        DispatchValidator.validate_dispatch_graph_revision(gs, dispatch_graph_revision)
        current_digest = compute_graph_digest(gs)
        if dispatch_digest != current_digest:
            raise OrchestratorError(
                f"stale dispatch rejected: digest mismatch"
            )


# ---------------------------------------------------------------------------
# Task 7.4: Typed edge readiness checking
# ---------------------------------------------------------------------------

class EdgeReadinessChecker:
    """Validates edge type semantics for readiness."""

    @staticmethod
    def check_edge_readiness(
        gs: GraphState,
        edge_id: str,
    ) -> bool:
        """Check if an edge is ready based on its type semantics."""
        edge = gs._edges.get(edge_id)
        if edge is None:
            raise OrchestratorError(f"edge {edge_id} not found")

        edge_type = edge.get("edge_type", "")
        source_job_id = edge.get("source_job_id", "")

        checkers = {
            "success": EdgeReadinessChecker.check_success_edge,
            "execution": EdgeReadinessChecker.check_execution_edge,
            "all-settled": EdgeReadinessChecker.check_all_settled_edge,
            "report": EdgeReadinessChecker.check_report_edge,
            "batch": EdgeReadinessChecker.check_batch_edge,
            "cycle": EdgeReadinessChecker.check_cycle_edge,
        }

        if edge_type == "verification":
            return EdgeReadinessChecker.check_verification_edge(gs, source_job_id, edge)

        if edge_type == "cycle":
            return EdgeReadinessChecker.check_cycle_edge(gs, source_job_id, edge)

        checker = checkers.get(edge_type)
        if checker is None:
            raise OrchestratorError(f"unknown edge type: {edge_type!r}")

        return checker(gs, source_job_id)

    @staticmethod
    def check_success_edge(gs: GraphState, source_job_id: str) -> bool:
        """Accepted success required from source job."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        if job.get("execution_status") == "failure":
            return False
        return job.get("status") == "completed" and job.get("completion_status") == "success"

    @staticmethod
    def check_execution_edge(gs: GraphState, source_job_id: str) -> bool:
        """Successful execution required from source job."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        return job.get("status") == "completed" and job.get("execution_status") == "success"

    @staticmethod
    def check_all_settled_edge(gs: GraphState, source_job_id: str) -> bool:
        """All jobs in the batch must be settled."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        batch_id = job.get("batch_id")
        if batch_id is None:
            batch_id = next((
                bid for bid, batch in gs._batches.items()
                if source_job_id in batch.get("job_ids", [])
            ), None)
        if batch_id is None:
            return job.get("status") in {"completed", "failed", "canceled"}
        batch = gs._batches.get(batch_id)
        if batch is None:
            return False
        if batch.get("status") == "open":
            return False
        for jid in batch.get("job_ids", []):
            j = gs._jobs.get(jid)
            if j and j.get("status") not in {"completed", "failed", "canceled"}:
                return False
        return True

    @staticmethod
    def check_report_edge(gs: GraphState, source_job_id: str) -> bool:
        """Accepted report consumed from source job."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        if job.get("execution_status") == "failure":
            return False
        return job.get("status") == "completed" and job.get("report_accepted") is True

    @staticmethod
    def check_verification_edge(gs: GraphState, source_job_id: str, edge: dict[str, Any] | None = None) -> bool:
        """Exact target verified successfully with matching condition/revision."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        if job.get("status") != "completed" or job.get("verification_passed") is not True:
            return False
        if edge is not None:
            metadata = edge.get("metadata", {})
            required_condition = metadata.get("condition_id")
            required_revision = metadata.get("target_gate_revision")
            required_target = metadata.get("target_job_id")
            if required_condition and job.get("condition_id") != required_condition:
                return False
            if required_revision and job.get("target_gate_revision") != required_revision:
                return False
            if required_target and job.get("target_job_id") != required_target:
                return False
        return True

    @staticmethod
    def check_batch_edge(gs: GraphState, source_job_id: str) -> bool:
        """Batch must be complete."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        batch_id = job.get("batch_id")
        if batch_id is None:
            batch_id = next((
                bid for bid, batch in gs._batches.items()
                if source_job_id in batch.get("job_ids", [])
            ), None)
        if batch_id is None:
            return False
        batch = gs._batches.get(batch_id)
        if batch is None:
            return False
        return batch.get("status") == "complete"

    @staticmethod
    def check_cycle_edge(
        gs: GraphState,
        source_job_id: str,
        edge: dict[str, Any] | None = None,
    ) -> bool:
        """Same-cycle evidence required."""
        job = gs._jobs.get(source_job_id)
        if job is None:
            return False
        source_cycle = job.get("cycle_id")
        if job.get("status") != "completed" or not source_cycle:
            return False
        if edge is not None:
            target = gs._jobs.get(edge.get("target_job_id", ""))
            if target is None or target.get("cycle_id") != source_cycle:
                return False
        return True


def is_job_eligible(gs: GraphState, job_id: str) -> bool:
    """Return whether one concrete job is dispatchable from the current graph."""
    if gs.status != GraphStatus.OPEN:
        return False
    job = gs._jobs.get(job_id)
    if job is None or job.get("role") == "control_root":
        return False
    if job.get("status", "pending") != "pending":
        return False
    incoming = sorted(
        (
            edge_id for edge_id, edge in gs._edges.items()
            if edge.get("target_job_id") == job_id
        )
    )
    return all(
        EdgeReadinessChecker.check_edge_readiness(gs, edge_id)
        for edge_id in incoming
    )


def eligible_job_ids(gs: GraphState) -> list[str]:
    """Return eligible jobs in deterministic generation and identity order."""
    return sorted(
        (job_id for job_id in gs._jobs if is_job_eligible(gs, job_id)),
        key=lambda job_id: (
            gs._jobs[job_id].get("graph_generation", 0),
            job_id,
        ),
    )


# ---------------------------------------------------------------------------
# Task 7.5: Batch membership and barriers
# ---------------------------------------------------------------------------

class BatchBarrier:
    """Batch state validation and sealing barriers."""

    VALID_BATCH_STATES = frozenset({"open", "sealed", "complete", "abandoned"})

    @staticmethod
    def validate_batch_membership(
        gs: GraphState,
        batch_id: str,
        job_id: str,
    ) -> None:
        """Check job is member of the batch."""
        batch = gs._batches.get(batch_id)
        if batch is None:
            raise OrchestratorError(f"batch {batch_id} not found")
        if batch.get("status") not in BatchBarrier.VALID_BATCH_STATES:
            raise OrchestratorError(
                f"batch {batch_id} has invalid state: {batch.get('status')!r}"
            )
        if job_id not in batch.get("job_ids", []):
            raise OrchestratorError(
                f"job {job_id} is not a member of batch {batch_id}"
            )

    @staticmethod
    def validate_batch_sealing(
        gs: GraphState,
        batch_id: str,
    ) -> None:
        """Ensure batch is sealed before completion."""
        batch = gs._batches.get(batch_id)
        if batch is None:
            raise OrchestratorError(f"batch {batch_id} not found")
        if batch.get("status") != "sealed":
            raise OrchestratorError(
                f"batch {batch_id} must be sealed before completion; "
                f"current status: {batch.get('status')!r}"
            )

    @staticmethod
    def validate_openspec_expansion(
        gs: GraphState,
        batch_id: str,
    ) -> None:
        """Check nested OpenSpec expansion exists before batch sealing."""
        batch = gs._batches.get(batch_id)
        if batch is None:
            raise OrchestratorError(f"batch {batch_id} not found")
        has_openspec_expansion = False
        for exp_id, exp in gs._expansions.items():
            if exp.get("batch_id") == batch_id and exp.get("type") == "openspec":
                has_openspec_expansion = True
                break
        if not has_openspec_expansion:
            raise OrchestratorError(
                f"batch {batch_id} requires nested OpenSpec expansion before sealing"
            )

    @staticmethod
    def advance_batch_lifecycle(gs: GraphState, batch_id: str) -> str | None:
        """Advance batch through open→sealed→complete lifecycle.

        Returns the new status or None if no transition occurred.
        """
        batch = gs._batches.get(batch_id)
        if batch is None:
            return None
        status = batch.get("status")
        if status == "open":
            job_ids = batch.get("job_ids", [])
            all_settled = all(
                gs._jobs.get(jid, {}).get("status") in {"completed", "failed", "canceled"}
                for jid in job_ids
            )
            if all_settled:
                batch["status"] = "sealed"
                batch["sealed_at"] = utc_now()
                return "sealed"
        elif status == "sealed":
            job_ids = batch.get("job_ids", [])
            has_success = any(
                gs._jobs.get(jid, {}).get("completion_status") == "success"
                for jid in job_ids
            )
            if has_success:
                batch["status"] = "complete"
                batch["completed_at"] = utc_now()
                return "complete"
        return None


# ---------------------------------------------------------------------------
# Task 7.6: Goal expansion handler
# ---------------------------------------------------------------------------

class GoalExpansionHandler:
    """Handles goal judge decisions for expansion."""

    @staticmethod
    def commit_continuation_expansion(
        gs: GraphState,
        expansion_id: str,
        decision: str,
    ) -> None:
        """Commit expansion on CONTINUE decision."""
        if decision != "CONTINUE":
            raise OrchestratorError(
                f"commit_continuation_expansion requires CONTINUE decision; got {decision!r}"
            )
        exp = gs._expansions.get(expansion_id)
        if exp is None:
            raise OrchestratorError(f"expansion {expansion_id} not found")
        if exp.get("status") != "pending":
            raise OrchestratorError(
                f"expansion {expansion_id} must be pending to commit; "
                f"current status: {exp.get('status')!r}"
            )
        exp["status"] = "committed"
        exp["committed_at"] = utc_now()

    @staticmethod
    def seal_on_goal_achieved(
        gs: GraphState,
        decision: str,
    ) -> None:
        """Seal graph without creating more work on GOAL_ACHIEVED."""
        if decision != "GOAL_ACHIEVED":
            raise OrchestratorError(
                f"seal_on_goal_achieved requires GOAL_ACHIEVED decision; got {decision!r}"
            )
        if gs.status != GraphStatus.OPEN:
            raise OrchestratorError(
                f"cannot seal: graph status is {gs.status!r}; must be open"
            )
        pending_expansions = [
            exp_id for exp_id, exp in gs._expansions.items()
            if exp.get("status") == "pending"
        ]
        if pending_expansions:
            raise OrchestratorError(
                f"cannot seal: pending expansions {pending_expansions} must be resolved"
            )
        transition_graph_status(gs, GraphStatus.SEALED)


# ---------------------------------------------------------------------------
# Task 7.7: Terminality checker
# ---------------------------------------------------------------------------

class TerminalityChecker:
    """Checks graph sealing and obligation completion."""

    @staticmethod
    def check_graph_sealed(gs: GraphState) -> None:
        """Graph must be sealed for terminality."""
        if gs.status != GraphStatus.SEALED:
            raise OrchestratorError(
                f"terminality check failed: graph status is {gs.status!r}; must be sealed"
            )

    @staticmethod
    def check_obligations(gs: GraphState) -> None:
        """All obligations must be satisfied."""
        obligations: list[str] = []

        for exp_id, exp in gs._expansions.items():
            if exp.get("status") in {"planning", "committing", "pending"}:
                obligations.append(f"expansion {exp_id} is {exp.get('status')!r}")

        for txn_id, txn in getattr(gs, "_transactions", {}).items():
            if txn.get("status") in {"pending", "committing"}:
                obligations.append(f"transaction {txn_id} is {txn.get('status')!r}")

        for batch_id, batch in gs._batches.items():
            if batch.get("status") in {"open", "sealed"}:
                obligations.append(f"batch {batch_id} is {batch.get('status')!r}")

        for job_id, job in gs._jobs.items():
            if job.get("status") in {"pending", "running", "dispatching", "dispatch_pending"}:
                obligations.append(f"job {job_id} is {job.get('status')!r}")

        for vass_id, vass in gs._verifier_assignments.items():
            if vass.get("status") == "assigned":
                obligations.append(f"verifier {vass_id} is assigned but not completed")

        if obligations:
            raise OrchestratorError(
                f"obligations not satisfied: {'; '.join(obligations)}"
            )

    @staticmethod
    def check_final_audit(gs: GraphState) -> None:
        """Audit must be coherent."""
        if not gs.graph_digest:
            raise OrchestratorError("final audit failed: missing graph digest")
        current_digest = compute_graph_digest(gs)
        if current_digest != gs.graph_digest:
            raise OrchestratorError(
                f"final audit failed: graph digest mismatch"
            )


# ---------------------------------------------------------------------------
# Task 7.8: Terminal outcome recorder
# ---------------------------------------------------------------------------

class TerminalOutcomeRecorder:
    """Records terminal outcomes atomically with sealed graph."""

    VALID_OUTCOMES = frozenset({
        "successful",
        "blocked",
        "infeasible",
        "failed",
        "canceled",
        "no_progress",
        "budget",
    })

    @staticmethod
    def record_terminal_outcome(
        gs: GraphState,
        outcome_type: str,
        goal_judge_decision: str | None = None,
        control_plane_disposition: str | None = None,
    ) -> dict[str, Any]:
        """Atomic terminal commit with sealed graph digest."""
        TerminalOutcomeRecorder.validate_terminal_outcome(outcome_type)
        TerminalityChecker.check_graph_sealed(gs)
        TerminalityChecker.check_final_audit(gs)

        outcome_record = {
            "schema_version": SCHEMA_VERSION,
            "outcome_type": outcome_type,
            "graph_revision": gs.graph_revision,
            "graph_digest": gs.graph_digest,
            "goal_judge_decision": goal_judge_decision,
            "control_plane_disposition": control_plane_disposition,
            "recorded_at": utc_now(),
        }

        outcome_id = stable_id("TERM", str(gs.graph_revision), outcome_type)
        gs._terminal_outcomes[outcome_id] = outcome_record

        return outcome_record

    @staticmethod
    def validate_terminal_outcome(outcome_type: str) -> None:
        """Ensure outcome type is valid."""
        if outcome_type not in TerminalOutcomeRecorder.VALID_OUTCOMES:
            raise OrchestratorError(
                f"invalid terminal outcome type: {outcome_type!r}; "
                f"must be one of {sorted(TerminalOutcomeRecorder.VALID_OUTCOMES)}"
            )


# ---------------------------------------------------------------------------
# Task 6.1: Expansion slot management
# ---------------------------------------------------------------------------

class ExpansionSlot:
    """Tracks the single active expansion slot on a graph.

    Only one expansion may be in-flight (planning/pending/committing) at any
    time.  The slot records the expansion identity, the graph revision at
    which it was created, and the current phase so that recovery and
    duplicate-detection are straightforward.
    """

    PHASE_IDLE = "idle"
    PHASE_PLANNING = "planning"
    PHASE_STAGING = "staging"
    PHASE_COMMITTING = "committing"
    PHASE_VISIBLE = "visible"

    def __init__(self) -> None:
        self.active_expansion_id: str | None = None
        self.phase: str = self.PHASE_IDLE
        self.created_revision: int = 0
        self.plan_digest: str = ""
        self.staged_bytes_digest: str = ""

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_expansion_id": self.active_expansion_id,
            "phase": self.phase,
            "created_revision": self.created_revision,
            "plan_digest": self.plan_digest,
            "staged_bytes_digest": self.staged_bytes_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpansionSlot:
        slot = cls()
        slot.active_expansion_id = data.get("active_expansion_id")
        slot.phase = data.get("phase", cls.PHASE_IDLE)
        slot.created_revision = data.get("created_revision", 0)
        slot.plan_digest = data.get("plan_digest", "")
        slot.staged_bytes_digest = data.get("staged_bytes_digest", "")
        return slot

    def is_idle(self) -> bool:
        return self.phase == self.PHASE_IDLE

    def activate(
        self,
        expansion_id: str,
        created_revision: int,
        plan_digest: str,
    ) -> None:
        """Claim the slot for a new expansion."""
        if not self.is_idle():
            raise OrchestratorError(
                f"expansion slot busy: {self.active_expansion_id!r} in phase {self.phase!r}"
            )
        self.active_expansion_id = expansion_id
        self.phase = self.PHASE_PLANNING
        self.created_revision = created_revision
        self.plan_digest = plan_digest
        self.staged_bytes_digest = ""

    def advance_phase(self, new_phase: str) -> None:
        """Move the slot to the next phase."""
        valid_progressions: dict[str, set[str]] = {
            self.PHASE_PLANNING: {self.PHASE_STAGING},
            self.PHASE_STAGING: {self.PHASE_COMMITTING},
            self.PHASE_COMMITTING: {self.PHASE_VISIBLE},
        }
        allowed = valid_progressions.get(self.phase, set())
        if new_phase not in allowed:
            raise OrchestratorError(
                f"invalid slot phase transition: {self.phase!r} -> {new_phase!r}; "
                f"allowed: {sorted(allowed)}"
            )
        self.phase = new_phase

    def release(self) -> None:
        """Release the slot back to idle."""
        self.active_expansion_id = None
        self.phase = self.PHASE_IDLE
        self.created_revision = 0
        self.plan_digest = ""
        self.staged_bytes_digest = ""


def validate_expansion_slot(slot: ExpansionSlot) -> list[str]:
    """Validate expansion slot invariants. Returns error list (empty = valid)."""
    errors: list[str] = []
    if slot.is_idle():
        return errors
    if not slot.active_expansion_id:
        errors.append("slot is non-idle but has no active_expansion_id")
    if slot.created_revision < 1:
        errors.append("created_revision must be >= 1 for active slot")
    if not slot.plan_digest:
        errors.append("plan_digest required for active slot")
    valid_phases = {
        ExpansionSlot.PHASE_PLANNING,
        ExpansionSlot.PHASE_STAGING,
        ExpansionSlot.PHASE_COMMITTING,
        ExpansionSlot.PHASE_VISIBLE,
    }
    if slot.phase not in valid_phases:
        errors.append(f"invalid slot phase: {slot.phase!r}")
    return errors
