#!/usr/bin/env python3
"""Trusted job-orchestrator control plane — v6 dynamic orchestration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator_core import OrchestratorError, load_json, _EXPANSION_ROLE_SCOPES, _authority_scope_for_role


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def init_run(args: argparse.Namespace) -> dict[str, Any]:
    from campaign_v6 import initialize_compiled_campaign, resume_frozen_campaign
    from orchestrator_core import write_json
    from pathlib import Path

    if getattr(args, "mode", None) == "resume":
        return resume_frozen_campaign(args)
    if getattr(args, "test_harness", False) and getattr(args, "mode", None) is None:
        args.mode = "custom"
        test_config = Path(args.workspace) / "test_strategy.json"
        write_json(test_config, {"custom_phases": []})
        args.strategy_config = test_config
    if getattr(args, "mode", None) is None:
        args.mode = "full_campaign"
    return initialize_compiled_campaign(args, _authority_scope_for_role)


def register_jobs(args: argparse.Namespace) -> dict[str, Any]:
    from graph_v6 import GraphState, add_batch, add_edge_to_graph, add_job_to_graph, compute_graph_digest
    from orchestrator_core import SCHEMA_VERSION, utc_now, write_json

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run_record = load_json(run_path)
    if run_record.get("status") != "active":
        raise OrchestratorError("registration is closed")

    graph_path = run_root / "graph" / "graph.json"
    if graph_path.exists():
        from graph_v6 import GraphState as _GS
        _check = _GS.load(graph_path)
        if len(_check._jobs) > 1 or len(_check._edges) > 0:
            raise OrchestratorError("registration is closed")

    definition = load_json(Path(args.definition))
    jobs = definition.get("jobs", [])
    edges = definition.get("edges", [])
    batches = definition.get("batches", [])

    graph_path = run_root / "graph" / "graph.json"
    graph = GraphState.load(graph_path) if graph_path.exists() else GraphState(envelope={})

    now = utc_now()
    for job in jobs:
        job_id = job.get("job_id")
        if not job_id:
            raise OrchestratorError("job definition missing job_id")
        job_dir = run_root / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        job_record = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "role": job.get("role", ""),
            "purpose_key": job.get("purpose_key", ""),
            "status": "pending",
            "revision": 0,
            "created_at": now,
        }
        write_json(job_dir / "job.json", job_record)

        authority_id = job.get("authority_id", f"AUTH-{job_id}")
        graph_job = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "title": job.get("title", job_id),
            "prompt_path": job.get("prompt_path", job_id),
            "role": job.get("role", ""),
            "purpose_key": job.get("purpose_key", ""),
            "graph_generation": job.get("graph_generation", 1),
            "expansion_origin": job.get("expansion_origin", "ROOT"),
            "authority_id": authority_id,
            "created_at": now,
        }
        add_job_to_graph(graph, graph_job)
        graph._jobs[job_id].update({"status": "pending", "revision": 0})
        graph._jobs[job_id]["cycle_id"] = ""

        authority = {
            "schema_version": SCHEMA_VERSION,
            "authority_id": authority_id,
            "campaign_id": graph.envelope.get("campaign_id", ""),
            "job_identity": job_id,
            "role": job.get("role", ""),
            "depth": 1,
            "status": "active",
            "scope": _authority_scope_for_role(job.get("role", ""), graph),
            "granted_at": now,
            "expires_at": "9999-12-31T23:59:59Z",
        }
        graph._authorities[authority_id] = authority

    for edge in edges:
        edge_id = edge.get("edge_id")
        if not edge_id:
            from orchestrator_core import stable_id
            edge_id = stable_id("EDGE", edge.get("source_job_id", ""), edge.get("target_job_id", ""))
            edge_id = edge_id[:5] + edge_id[5:].upper()
        graph_edge = {
            "schema_version": SCHEMA_VERSION,
            "edge_id": edge_id,
            "source_job_id": edge["source_job_id"],
            "target_job_id": edge["target_job_id"],
            "edge_type": edge.get("edge_type", "execution"),
            "graph_revision": graph.graph_revision,
            "created_at": now,
        }
        add_edge_to_graph(graph, graph_edge)

    for batch in batches:
        add_batch(graph, batch)

    for vass in definition.get("verifier_assignments", []):
        from graph_v6 import add_verifier_assignment
        add_verifier_assignment(graph, vass)

    for rgh in definition.get("repair_gate_history", []):
        from graph_v6 import add_repair_gate
        add_repair_gate(graph, rgh)

    graph.status = "open"
    graph.graph_digest = compute_graph_digest(graph)
    graph.save(graph_path)

    run_record["graph_revision"] = graph.graph_revision
    run_record["graph_digest"] = graph.graph_digest
    write_json(run_path, run_record)

    return {
        "registered": len(jobs),
        "run_root": str(run_root),
    }


def _load_scheduling_graph(run_root: Path, run: dict[str, Any]):
    from graph_v6 import GraphState, compute_graph_digest

    graph_path = run_root / "graph" / "graph.json"
    if not graph_path.exists():
        raise OrchestratorError(f"graph state not found: {graph_path}")
    graph = GraphState.load(graph_path)
    if graph.graph_revision != run.get("graph_revision"):
        raise OrchestratorError(
            "run and graph revision disagree; audit and recover before scheduling"
        )
    if graph.graph_digest != run.get("graph_digest"):
        raise OrchestratorError(
            "run and graph digest disagree; audit and recover before scheduling"
        )
    if compute_graph_digest(graph) != graph.graph_digest:
        raise OrchestratorError(
            "persisted graph digest is invalid; audit and recover before scheduling"
        )

    # Runtime execution state is persisted per job and deliberately excluded
    # from the immutable graph digest.
    for job_id, graph_job in graph._jobs.items():
        job_path = run_root / "jobs" / job_id / "job.json"
        if job_path.exists():
            runtime_job = load_json(job_path)
            for name in (
                "status", "revision", "execution_status", "completion_status",
                "report_accepted", "verification_passed", "condition_id",
                "target_gate_revision", "target_job_id", "cycle_id",
                "evidence_refs", "session_ref", "question",
            ):
                if name in runtime_job:
                    graph_job[name] = runtime_job[name]
        session_path = run_root / "jobs" / job_id / "session.json"
        if session_path.exists():
            graph_job["session_ref"] = load_json(session_path).get("session_ref", "")
    return graph


def _dependency_evidence_digest(graph, job_id: str) -> str:
    from orchestrator_core import content_hash

    incoming = sorted(
        (
            edge for edge in graph._edges.values()
            if edge.get("target_job_id") == job_id
        ),
        key=lambda edge: edge.get("edge_id", ""),
    )
    evidence = []
    for edge in incoming:
        source = graph._jobs.get(edge.get("source_job_id", ""), {})
        evidence.append({
            "edge_id": edge.get("edge_id", ""),
            "edge_type": edge.get("edge_type", ""),
            "metadata": edge.get("metadata", {}),
            "source_job_id": edge.get("source_job_id", ""),
            "source_status": source.get("status"),
            "execution_status": source.get("execution_status"),
            "completion_status": source.get("completion_status"),
            "report_accepted": source.get("report_accepted"),
            "verification_passed": source.get("verification_passed"),
            "evidence_refs": source.get("evidence_refs", []),
        })
    return content_hash(evidence)


def _update_runtime_job(
    run_root: Path,
    graph,
    job_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    from orchestrator_core import utc_now, write_json

    job_path = run_root / "jobs" / job_id / "job.json"
    if job_path.exists():
        job = load_json(job_path)
    else:
        definition = graph._jobs.get(job_id)
        if definition is None:
            raise OrchestratorError(f"job {job_id!r} does not exist")
        job = {
            "schema_version": 6,
            "job_id": job_id,
            "role": definition.get("role", ""),
            "purpose_key": definition.get("purpose_key", ""),
            "status": definition.get("status", "pending"),
            "revision": definition.get("revision", 0),
            "created_at": definition.get("created_at", utc_now()),
        }
    job.update(updates)
    job["revision"] = job.get("revision", 0) + 1
    job["updated_at"] = utc_now()
    write_json(job_path, job)
    graph._jobs[job_id].update(job)
    return job


_PLANNING_ROLES = frozenset({
    "goal_judge",
    "goal-judge",
    "work_planner_architect",
    "work-planner",
    "proposal_architect",
    "proposal-architect",
    "proposal_finalizer",
    "proposal-finalizer",
    "implementation_planner",
    "implementation-planner",
    "implementation_review_architect",
    "architect-review",
})


def _requires_quiescence(graph, job_id: str) -> bool:
    job = graph._jobs[job_id]
    authority = graph._authorities.get(job.get("authority_id", ""), {})
    return (
        authority.get("scope", {}).get("expansion") is True
        or job.get("role") in _PLANNING_ROLES
    )


def next_action(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import V6, content_hash
    from graph_v6 import GraphStatus, eligible_job_ids
    from audit_v6 import DynamicAuditor, AuditReporter, FindingClassification

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    version = run.get("schema_version")
    if version != V6:
        raise OrchestratorError(f"incompatible run: version {version}")
    protocol_revision = run.get("protocol_revision")
    if protocol_revision != "v6-closed":
        raise OrchestratorError(f"incompatible run: revision {protocol_revision}")
    if run.get("status") != "active":
        return {
            "operation": "run_complete",
            "run_status": run.get("status", "unknown"),
            "successful": run.get("status") == "completed",
        }

    graph = _load_scheduling_graph(run_root, run)

    retained_dir = run_root / "transactions" / "retained"
    if retained_dir.exists():
        for retained_file in sorted(retained_dir.glob("EXP-*.json")):
            if retained_file.name.endswith(".plan.json"):
                continue
            expansion_id = retained_file.stem
            if graph._expansions.get(expansion_id, {}).get("status") == "committed":
                continue
            try:
                retained = load_json(retained_file)
                if retained.get("status") != "pending":
                    continue
                return {
                    "operation": "commit_expansion",
                    "expansion_id": expansion_id,
                    "expected_graph_revision": retained["base_graph_revision"],
                    "expected_graph_digest": retained["base_graph_digest"],
                    "plan_digest": retained["plan_digest"],
                }
            except (KeyError, OrchestratorError):
                return {
                    "operation": "recover",
                    "transaction_id": expansion_id,
                    "reason": "invalid retained expansion metadata",
                }

    auditor = DynamicAuditor(graph)
    auditor.run_all(run_protocol_hash=run.get("protocol_hash"))
    reporter = AuditReporter(auditor.findings)

    if reporter.expose_control_plane_facts().get("blocks_resume"):
        return {
            "operation": "recover",
            "reason": "audit_gate_blocks_resume",
            "active_idle_contradiction": any(
                f.classification == FindingClassification.ACTIVE_IDLE_CONTRADICTION
                for f in auditor.findings
            ),
            "protocol_hash_mismatch": any(
                f.classification == FindingClassification.PROTOCOL_HASH_MISMATCH
                for f in auditor.findings
            ),
        }

    if graph.status == GraphStatus.RECOVERY_REQUIRED:
        return {"operation": "recover", "reason": "graph_recovery_required"}
    if graph.status in {
        GraphStatus.PLANNING,
        GraphStatus.PENDING,
        GraphStatus.COMMITTING,
        GraphStatus.CANCELING,
    }:
        return {
            "operation": "wait",
            "reason": f"graph_{graph.status}",
            "graph_status": graph.status,
        }
    if graph.status == GraphStatus.SEALED:
        return {
            "operation": "wait",
            "reason": "terminal_barrier",
            "graph_status": graph.status,
        }

    waiting_jobs = sorted(
        job_id for job_id, job in graph._jobs.items()
        if job.get("status") == "waiting"
    )
    if waiting_jobs:
        job_id = waiting_jobs[0]
        job = graph._jobs[job_id]
        if job.get("question"):
            return {
                "operation": "ask_user",
                "job_id": job_id,
                "question": job["question"],
                "session_ref": job.get("session_ref", ""),
            }
        return {
            "operation": "wait",
            "reason": "waiting_session",
            "job_id": job_id,
            "session_ref": job.get("session_ref", ""),
        }

    active_jobs = sorted(
        job_id for job_id, job in graph._jobs.items()
        if job.get("status") in {"running", "dispatching", "dispatch_pending"}
    )
    max_concurrency = graph.limits.get("max_concurrency")
    if isinstance(max_concurrency, int) and len(active_jobs) >= max_concurrency:
        return {
            "operation": "wait",
            "reason": "concurrency_barrier",
            "job_id": active_jobs[0],
        }

    eligible = [
        job_id for job_id in eligible_job_ids(graph)
        if not (_requires_quiescence(graph, job_id) and active_jobs)
    ]
    if not eligible:
        pending_jobs = sorted(
            job_id for job_id, job in graph._jobs.items()
            if job.get("role") != "control_root"
            and job.get("status", "pending") == "pending"
        )
        return {
            "operation": "wait",
            "reason": "dependency_or_batch_barrier" if pending_jobs else "graph_unsealed",
        }

    job_id = eligible[0]
    job_revision = graph._jobs[job_id].get("revision", 0)

    return {
        "operation": "prepare_dispatch",
        "job_id": job_id,
        "expected_revision": job_revision,
        "expected_graph_revision": graph.graph_revision,
        "expected_graph_digest": graph.graph_digest,
        "dependency_evidence_digest": _dependency_evidence_digest(graph, job_id),
    }


def prepare_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, content_hash, stable_id, utc_now, write_json
    from graph_v6 import DispatchValidator, get_edges_to, get_job, is_job_eligible

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    job_id = args.job
    graph = _load_scheduling_graph(run_root, run)
    graph_revision = graph.graph_revision
    graph_generation = 1
    run_id = run.get("run_id", "")

    job = get_job(graph, job_id)
    if job is None or job.get("role") == "control_root":
        raise OrchestratorError(f"job {job_id!r} does not exist")
    DispatchValidator.reject_stale_dispatch(
        graph,
        args.expected_graph_revision,
        args.expected_graph_digest,
    )
    current_revision = job.get("revision", 0)
    if args.expected_revision != current_revision:
        raise OrchestratorError(
            f"stale job compare-and-swap: expected revision {args.expected_revision}, "
            f"got {current_revision}"
        )
    if (
        args.expected_job_revision is not None
        and args.expected_job_revision != current_revision
    ):
        raise OrchestratorError(
            "stale job compare-and-swap: expected job revision "
            f"{args.expected_job_revision}, got {current_revision}"
        )
    if not is_job_eligible(graph, job_id):
        raise OrchestratorError(f"job {job_id!r} is not eligible for dispatch")
    dependency_digest = _dependency_evidence_digest(graph, job_id)
    if args.dependency_evidence_digest != dependency_digest:
        raise OrchestratorError("stale dependency evidence digest")

    graph_path = run_root / "graph" / "graph.json"
    prompt_text = f"Dispatch for job {job_id}"

    if graph_path.exists():
        from prompt_v6 import PromptRenderer

        gs = graph
        job = get_job(gs, job_id)
        if job is not None:
            graph_generation = job.get("graph_generation", graph_generation)

            assignment = None
            for vass in gs._verifier_assignments.values():
                if vass.get("verifier_job_id") == job_id:
                    assignment = vass
                    break

            if assignment is not None:
                assignment_id = assignment.get("assignment_id", "")
                binding = gs._verifier_authority_bindings.get(assignment_id, {})
                required_evidence = (
                    assignment.get("required_evidence")
                    or binding.get("required_evidence", [])
                )
                condition_id = binding.get("condition_id", "")
                evidence_refs = assignment.get("evidence_refs", [])

                accepted_reports = []
                target_gate_id = ""
                for dep_edge in get_edges_to(gs, job_id):
                    if dep_edge.get("edge_type") == "report":
                        src_id = dep_edge.get("source_job_id", "")
                        src_job = get_job(gs, src_id)
                        if src_job and src_job.get("status") == "completed":
                            for ref in src_job.get("evidence_refs", []):
                                accepted_reports.append({"ref": ref})
                    if not target_gate_id:
                        target_gate_id = dep_edge.get("metadata", {}).get("target_gate_id", "")

                renderer = PromptRenderer(run_id, run.get("goal", ""))
                prompt_text = renderer.render_verifier_prompt(
                    job_id=job_id,
                    activation_id=job.get("activation_id", ""),
                    cycle_id=assignment.get("cycle_id", ""),
                    graph_revision=graph_revision,
                    assignment_id=assignment_id,
                    target_job_id=assignment.get("target_job_id", ""),
                    target_gate_id=target_gate_id,
                    target_gate_revision=assignment.get("target_gate_revision", 0),
                    evidence_refs=evidence_refs,
                    required_evidence=required_evidence or None,
                    accepted_reports=accepted_reports or None,
                    condition_id=condition_id,
                    graph_generation=graph_generation,
                )

    prompt_sha256 = content_hash(prompt_text)

    dispatch_id = stable_id("DISP", run_id, job_id, utc_now())

    dispatch = {
        "dispatch_id": dispatch_id,
        "run_id": run_id,
        "campaign_id": run_id,
        "job_id": job_id,
        "graph_revision": graph_revision,
        "graph_generation": graph_generation,
        "prompt_sha256": prompt_sha256,
        "created_at": utc_now(),
    }

    dispatch_dir = run_root / "control" / "dispatches"
    write_json(dispatch_dir / f"{dispatch_id}.json", dispatch)
    _update_runtime_job(
        run_root,
        graph,
        job_id,
        {"status": "dispatch_pending", "dispatch_id": dispatch_id},
    )

    return {
        "dispatch": dispatch,
        "job_id": job_id,
        "dispatch_id": dispatch_id,
    }


def _verify_receipt_auth(run_root: Path, receipt: dict[str, Any]) -> None:
    """Verify the receipt's auth_tag matches the adapter binding."""
    from orchestrator_core import receipt_auth_tag

    setup_path = run_root / "setup.json"
    if not setup_path.exists():
        raise OrchestratorError(f"setup not found: {run_root}")
    setup = load_json(setup_path)
    binding = setup.get("adapter_binding", {})
    if not binding:
        raise OrchestratorError(
            "run has no adapter binding; transport receipts cannot be authoritative"
        )
    if not binding.get("adapter_id") or not binding.get("adapter_secret"):
        raise OrchestratorError("adapter binding is incomplete")
    if receipt.get("adapter_id") != binding["adapter_id"]:
        raise OrchestratorError("receipt adapter_id does not match adapter binding")

    provided_tag = receipt.get("auth_tag")
    if provided_tag is None:
        raise OrchestratorError("receipt missing auth_tag")

    check = {k: v for k, v in receipt.items() if k != "auth_tag"}
    expected_tag = receipt_auth_tag(binding, check)
    if provided_tag != expected_tag:
        raise OrchestratorError("authentication failed")


def record_launch_receipt(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, stable_id, utc_now, write_json

    run_root = Path(args.run)
    receipt = load_json(Path(args.receipt))

    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    _verify_receipt_auth(run_root, receipt)

    dispatch_id = receipt.get("dispatch_id", "")
    if not dispatch_id:
        raise OrchestratorError("launch receipt missing dispatch_id")

    run = load_json(run_path)
    run_id = run.get("run_id", "")

    dispatch_path = run_root / "control" / "dispatches" / f"{dispatch_id}.json"
    if not dispatch_path.exists():
        raise OrchestratorError(f"dispatch {dispatch_id!r} does not exist")
    dispatch = load_json(dispatch_path)
    graph = _load_scheduling_graph(run_root, run)
    job_id = dispatch.get("job_id", "")
    job = graph._jobs.get(job_id)
    if job is None or job.get("status") != "dispatch_pending":
        raise OrchestratorError(
            f"dispatch {dispatch_id!r} is not pending launch for job {job_id!r}"
        )

    attempt_id = stable_id("ATT", run_id, dispatch_id)
    attempts_dir = run_root / "control" / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    write_json(attempts_dir / f"{dispatch_id}.json", {
        "attempt_id": attempt_id,
        "dispatch_id": dispatch_id,
        "session_ref": receipt.get("session_ref", ""),
        "recorded_at": utc_now(),
    })
    _update_runtime_job(
        run_root,
        graph,
        job_id,
        {
            "status": "running",
            "session_ref": receipt.get("session_ref", ""),
            "attempt_id": attempt_id,
        },
    )

    authority = graph._authorities.get(job.get("authority_id", ""), {})
    scope = authority.get("scope", {})
    if scope.get("max_child_depth", 0) > 0 or scope.get("allowed_expansion_kinds"):
        from graph_v6 import compute_graph_digest

        graph.active_planning_authority_id = authority["authority_id"]
        if job.get("role") == "goal_judge":
            graph.current_goal_judge_id = job_id
        graph.graph_digest = compute_graph_digest(graph)
        graph.save(run_root / "graph" / "graph.json")
        run["graph_digest"] = graph.graph_digest
        write_json(run_path, run)
    elif job.get("role") == "goal_judge":
        from graph_v6 import compute_graph_digest

        graph.current_goal_judge_id = job_id
        graph.graph_digest = compute_graph_digest(graph)
        graph.save(run_root / "graph" / "graph.json")
        run["graph_digest"] = graph.graph_digest
        write_json(run_path, run)

    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "launch",
        "recorded": True,
        "dispatch_id": dispatch_id,
        "attempt_id": attempt_id,
        "recorded_at": utc_now(),
    }


def _load_graph_state(run_root: Path):
    from graph_v6 import GraphState

    graph_path = run_root / "graph" / "graph.json"
    if not graph_path.exists():
        return None
    return GraphState.load(graph_path)


def _validate_goal_gate_results(
    gs, goal_gate_result_ids: list[str], run_id: str
) -> None:
    if not goal_gate_result_ids:
        return
    assignments_by_id = gs._verifier_assignments
    for gid in goal_gate_result_ids:
        assignment = assignments_by_id.get(gid)
        if assignment is None:
            raise OrchestratorError(
                f"goal_gate_result_id {gid!r} not found in graph verifier assignments"
            )
        if assignment.get("run_id") != run_id:
            raise OrchestratorError(
                f"goal_gate_result_id {gid!r} belongs to run "
                f"{assignment.get('run_id')!r}, not {run_id!r}"
            )
        status = assignment.get("status")
        if status != "completed":
            raise OrchestratorError(
                f"goal_gate_result_id {gid!r} has status {status!r}; "
                f"must be 'completed'"
            )


def _validate_finding_dispositions(
    gs, finding_disposition_ids: list[str], run_id: str
) -> None:
    if not finding_disposition_ids:
        return
    dispositions = getattr(gs, "_finding_dispositions", {})
    for did in finding_disposition_ids:
        disp = dispositions.get(did)
        if disp is None:
            raise OrchestratorError(
                f"finding_disposition_id {did!r} not found in graph dispositions"
            )
        if disp.get("run_id") != run_id:
            raise OrchestratorError(
                f"finding_disposition_id {did!r} belongs to run "
                f"{disp.get('run_id')!r}, not {run_id!r}"
            )
        status = disp.get("status")
        valid_statuses = ("verified", "refuted", "superseded", "accepted_risk")
        if status not in valid_statuses:
            raise OrchestratorError(
                f"finding_disposition_id {did!r} has invalid status {status!r}"
            )


_WIRE_TO_VERDICT: dict[str, str] = {
    "passed": "pass",
    "failed": "fail",
    "not_run": "not-run",
    "unavailable": "unavailable",
    "unknown": "unknown",
}

_VERDICT_TO_RECORD_STATUS: dict[str, str] = {
    "pass": "met",
    "fail": "unmet",
    "not-run": "pending",
    "unavailable": "error",
    "unknown": "error",
}

_RECORD_STATUS_TO_VERDICT: dict[str, str] = {
    "met": "pass",
    "unmet": "fail",
    "pending": "not-run",
    "error": "unknown",
}


def _normalize_verifier_wire_results(receipt: dict[str, Any]) -> None:
    """Normalize plural wire condition_results into singular condition_result.

    Maps wire vocabulary -> applier verdict -> persisted record status,
    preserving the original wire status on the evidence trail.
    Runs before role validation so a spec-conformant verifier response
    reaches the runtime update block.
    """
    if "condition_result" in receipt:
        return
    results_list = receipt.get("condition_results")
    if not isinstance(results_list, list) or not results_list:
        return
    wire_entry = results_list[0]
    if not isinstance(wire_entry, dict):
        return
    wire_status = wire_entry.get("status", "")
    verdict = _WIRE_TO_VERDICT.get(wire_status, wire_status)
    record_status = _VERDICT_TO_RECORD_STATUS.get(verdict, "error")
    normalized = dict(wire_entry)
    normalized["status"] = record_status
    normalized["wire_status"] = wire_status
    normalized["verdict"] = verdict
    receipt["condition_result"] = normalized


_TYPED_RESULT_FIELDS = frozenset({
    "hypothesis_result", "work_plan", "expansion_plan", "goal_gate_result",
    "goal_judgment", "condition_result", "synthesis_result", "role_result",
    "finding",
})

_ROLE_RESULT_CONTRACTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "hypothesis_investigator": (
        frozenset({"hypothesis_result", "finding"}),
        frozenset({"hypothesis_result"}),
    ),
    "synthesis_architect": (
        frozenset({"synthesis_result", "finding"}),
        frozenset({"synthesis_result"}),
    ),
    "work_planner_architect": (
        frozenset({"work_plan", "expansion_plan", "finding"}),
        frozenset({"expansion_plan"}),
    ),
    "goal_judge": (
        frozenset({"goal_judgment", "expansion_plan", "finding"}),
        frozenset({"goal_judgment"}),
    ),
    "verifier": (
        frozenset({"condition_result", "finding"}),
        frozenset({"condition_result"}),
    ),
    "integration_verifier": (
        frozenset({"condition_result", "finding"}),
        frozenset({"condition_result"}),
    ),
    "implementation_review_architect": (
        frozenset({"role_result", "expansion_plan", "finding"}),
        frozenset({"role_result"}),
    ),
}

_RESULT_SCHEMAS = {
    "hypothesis_result": "hypothesis-result",
    "work_plan": "work-plan",
    "condition_result": "condition-result",
    "synthesis_result": "synthesis-result",
    "role_result": "role-result",
    "finding": "finding",
    "goal_judgment": "goal-judgment",
}

_RESULT_ID_FIELDS: dict[str, str] = {
    "hypothesis_result": "hypothesis_result_id",
    "synthesis_result": "synthesis_id",
    "work_plan": "plan_id",
    "condition_result": "condition_id",
    "role_result": "role_result_id",
    "finding": "finding_id",
    "goal_judgment": "judgment_id",
}


def _validate_role_typed_result(gs, job_id: str, receipt: dict[str, Any]) -> list[str]:
    from orchestrator_core import validate_record

    job = gs._jobs.get(job_id)
    if job is None:
        return [f"producer job {job_id!r} is not present in the graph"]
    role = job.get("role", "")
    provided = {name for name in _TYPED_RESULT_FIELDS if name in receipt}
    allowed, required = _ROLE_RESULT_CONTRACTS.get(
        role, (frozenset(), frozenset())
    )
    errors = [
        f"role {role!r} is not permitted to return {name!r}"
        for name in sorted(provided - allowed)
    ]
    if "condition_results" in receipt:
        results_list = receipt.get("condition_results")
        if isinstance(results_list, list) and len(results_list) > 1:
            import sys
            sys.stderr.write("Warning: verifier response contains more than one result in condition_results\n")
            errors.append("verifier response contains more than one result in condition_results; only a single result is supported")
    if receipt.get("status") in {"completed", "complete", "success"} and required and not (provided & required):
        errors.append(
            f"role {role!r} completed without required typed result; "
            f"expected one of {sorted(required)}"
        )
    result_role = receipt.get("result_role") or receipt.get("producer_role")
    if result_role is not None and result_role != role:
        errors.append(
            f"typed result role {result_role!r} does not match persisted role {role!r}"
        )
    for name in sorted(provided & allowed):
        value = receipt[name]
        if not isinstance(value, dict):
            errors.append(f"{name} must be a JSON object")
            continue
        producer = value.get("producer_job_id")
        if producer is not None and producer != job_id:
            errors.append(
                f"{name}.producer_job_id {producer!r} does not match producer {job_id!r}"
            )
        response_id = value.get("response_id") or value.get("source_response_id")
        if response_id is not None and response_id != receipt.get("response_id"):
            errors.append(
                f"{name} response identity {response_id!r} does not match receipt"
            )
        schema = _RESULT_SCHEMAS.get(name)
        if schema is not None:
            try:
                validate_record(schema, value)
                if name == "goal_judgment":
                    from transaction_v6 import GoalDecisionProcessor
                    processor = GoalDecisionProcessor(
                        current_judge_id=gs.current_goal_judge_id,
                        current_graph_revision=gs.graph_revision,
                    )
                    processor.validate_goal_authority(value)
                    if (
                        "graph_digest" in value
                        and value.get("graph_digest") != gs.graph_digest
                    ):
                        raise OrchestratorError("goal_judgment graph_digest is stale")
            except OrchestratorError as exc:
                errors.append(str(exc))
    return errors


def _persist_typed_result(
    run_root: Path,
    receipt: dict[str, Any],
) -> list[dict[str, Any]]:
    from orchestrator_core import write_json, utc_now

    persisted = []
    for name in _TYPED_RESULT_FIELDS:
        value = receipt.get(name)
        if not isinstance(value, dict):
            continue

        id_field = _RESULT_ID_FIELDS.get(name)
        if id_field is None:
            continue
        result_id = value.get(id_field)
        if not result_id:
            continue

        record = {
            "schema_version": 6,
            "result_type": name,
            "result_id": result_id,
            "producer_job_id": receipt.get("job_id", ""),
            "response_id": receipt.get("response_id", ""),
            "cycle_id": receipt.get("cycle_id", ""),
            **value,
            "persisted_at": utc_now(),
        }

        decisions_dir = run_root / "graph" / "decisions" / name
        decisions_dir.mkdir(parents=True, exist_ok=True)
        result_path = decisions_dir / f"{result_id}.json"

        if result_path.exists():
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            if existing.get("producer_job_id") == record.get("producer_job_id"):
                continue
            raise OrchestratorError(
                f"conflicting typed result identity reuse for {result_id!r}"
            )

        write_json(result_path, record)
        persisted.append({"result_type": name, "result_id": result_id})

    return persisted


def _response_evidence_paths(run_root: Path, response_id: str) -> tuple[Path, Path]:
    import re

    if not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,127}", response_id):
        raise OrchestratorError(f"invalid response_id {response_id!r}")
    return (
        run_root / "receipts" / "response" / f"{response_id}.json",
        run_root / "control" / "response-results" / f"{response_id}.json",
    )


def _retain_response_evidence(
    run_root: Path, receipt: dict[str, Any]
) -> dict[str, Any] | None:
    from orchestrator_core import atomic_write, canonical_bytes

    response_id = receipt.get("response_id", "")
    if not response_id:
        raise OrchestratorError("response receipt missing response_id")
    evidence_path, result_path = _response_evidence_paths(run_root, response_id)
    exact = canonical_bytes(receipt)
    if evidence_path.exists():
        if evidence_path.read_bytes() != exact:
            raise OrchestratorError(
                f"conflicting response identity reuse for {response_id!r}"
            )
        if result_path.exists():
            replay = load_json(result_path)
            replay["idempotent_replay"] = True
            return replay
        return None
    atomic_write(evidence_path, exact)
    return None


def _persist_response_result(
    run_root: Path, response_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    from orchestrator_core import write_json

    _evidence_path, result_path = _response_evidence_paths(run_root, response_id)
    write_json(result_path, result)
    return result


def _response_binding_errors(
    run_root: Path, receipt: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    dispatch_id = receipt.get("dispatch_id", "")
    dispatch_path = run_root / "control" / "dispatches" / f"{dispatch_id}.json"
    attempt_path = run_root / "control" / "attempts" / f"{dispatch_id}.json"
    if not dispatch_id or not dispatch_path.exists():
        return [f"response dispatch {dispatch_id!r} is not authoritative"]
    dispatch = load_json(dispatch_path)
    if receipt.get("job_id") != dispatch.get("job_id"):
        errors.append("response job_id does not match its dispatch")
    if not attempt_path.exists():
        errors.append("response has no authenticated launch attempt")
        return errors
    attempt = load_json(attempt_path)
    if receipt.get("attempt_id") != attempt.get("attempt_id"):
        errors.append("response attempt_id does not match its launch attempt")
    if receipt.get("session_ref") != attempt.get("session_ref"):
        errors.append("response session_ref does not match its launch session")
    return errors


def _is_narrower_limit(child: Any, parent: Any) -> bool:
    return (
        isinstance(child, (int, float))
        and not isinstance(child, bool)
        and isinstance(parent, (int, float))
        and not isinstance(parent, bool)
        and child <= parent
    )


def _validate_expansion_authority(
    gs, receipt: dict[str, Any], plan: dict[str, Any]
) -> tuple[list[str], dict[str, Any] | None]:
    from orchestrator_core import content_hash, parse_time, utc_now

    errors: list[str] = []
    job_id = receipt.get("job_id", "")
    job = gs._jobs.get(job_id, {})
    authority_id = job.get("authority_id", "")
    authority = gs._authorities.get(authority_id)
    if authority is None:
        return [f"producer authority {authority_id!r} is not persisted"], None
    scope = authority.get("scope", {})
    if authority.get("job_identity") != job_id or authority.get("role") != job.get("role"):
        errors.append("authority producer identity or role does not match the persisted job")
    if authority.get("status", "active") != "active":
        errors.append(f"authority {authority_id!r} is not active")
    if scope.get("max_child_depth", 0) <= 0 and not scope.get("allowed_expansion_kinds"):
        errors.append(f"role {job.get('role')!r} has no persisted expansion authority")
    if gs.active_planning_authority_id != authority_id:
        errors.append(
            f"authority {authority_id!r} is not the current planning authority"
        )
    try:
        if parse_time(authority.get("expires_at", "")) < parse_time(utc_now()):
            errors.append(f"authority {authority_id!r} is expired")
    except OrchestratorError as exc:
        errors.append(str(exc))

    expected = {
        "campaign_id": gs.envelope.get("campaign_id"),
        "source_job_id": job_id,
        "source_attempt_id": receipt.get("attempt_id"),
        "source_response_id": receipt.get("response_id"),
        "authority_id": authority_id,
        "authority_scope_digest": content_hash(scope),
        "base_graph_revision": gs.graph_revision,
        "base_graph_digest": gs.graph_digest,
    }
    for field, value in expected.items():
        if plan.get(field) != value:
            errors.append(
                f"expansion {field} {plan.get(field)!r} does not match current {value!r}"
            )
    expansion_kind = plan.get("expansion_kind")
    if expansion_kind not in scope.get("allowed_expansion_kinds", []):
        errors.append(
            f"expansion kind {expansion_kind!r} is outside authority scope"
        )
    targets = plan.get("target_jobs")
    if not isinstance(targets, list) or not targets:
        errors.append("expansion target_jobs must be a non-empty array")
        targets = []
    max_jobs = scope.get("max_child_jobs", 0)
    if not isinstance(max_jobs, int) or len(targets) > max_jobs:
        errors.append(
            f"expansion proposes {len(targets)} child jobs; authority permits {max_jobs}"
        )
    parent_depth = authority.get("depth", 0)
    max_child_depth = scope.get("max_child_depth", 0)
    allowed_roles = set(scope.get("allowed_child_roles", []))
    allowed_effects = set(scope.get("side_effects", []))
    parent_limits = scope.get("limits", {})
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(f"target_jobs[{index}] must be a JSON object")
            continue
        role = target.get("role")
        if role not in allowed_roles:
            errors.append(f"child role {role!r} is outside authority scope")
        effect = target.get("side_effect_class", "none")
        if effect not in allowed_effects:
            errors.append(f"child side effect {effect!r} is outside authority scope")
        child_depth = target.get("authority_depth", parent_depth + 1)
        if (
            not isinstance(child_depth, int)
            or child_depth <= parent_depth
            or child_depth > parent_depth + max_child_depth
        ):
            errors.append(
                f"child authority depth {child_depth!r} exceeds delegated depth"
            )
        delegated = target.get("authority_scope", {})
        if delegated:
            if not isinstance(delegated, dict):
                errors.append(f"target_jobs[{index}].authority_scope must be an object")
                continue
            for key in ("allowed_expansion_kinds", "allowed_child_roles", "side_effects"):
                if not set(delegated.get(key, [])).issubset(set(scope.get(key, []))):
                    errors.append(f"child {key} exceeds parent authority")
            for key in ("max_child_jobs", "max_child_depth"):
                if key in delegated and not _is_narrower_limit(delegated[key], scope.get(key)):
                    errors.append(f"child {key} exceeds parent authority")
        child_limits = target.get("limits", {})
        if child_limits:
            if not isinstance(child_limits, dict):
                errors.append(f"target_jobs[{index}].limits must be an object")
            else:
                for key, value in child_limits.items():
                    if key not in parent_limits or not _is_narrower_limit(value, parent_limits[key]):
                        errors.append(f"child limit {key!r} exceeds parent authority")
    return errors, authority


def _retain_expansion_plan(
    run_root: Path,
    run_id: str,
    gs,
    receipt: dict[str, Any],
    plan: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, Any]:
    from orchestrator_core import atomic_write, canonical_bytes, content_hash, stable_id, utc_now, write_json

    exact = canonical_bytes(plan)
    plan_digest = content_hash(exact)
    response_id = receipt["response_id"]
    expansion_id = stable_id("EXP", run_id, response_id).upper()
    retained_dir = run_root / "transactions" / "retained"
    retained_plan_path = retained_dir / f"{expansion_id}.plan.json"
    retained_record_path = retained_dir / f"{expansion_id}.json"
    if retained_record_path.exists():
        existing = load_json(retained_record_path)
        if existing.get("canonical_digest") != plan_digest or retained_plan_path.read_bytes() != exact:
            raise OrchestratorError(
                f"conflicting identity reuse for expansion {expansion_id!r}"
            )
        return existing
    provenance = {
        "producer_job_id": receipt["job_id"],
        "producer_attempt_id": receipt["attempt_id"],
        "response_id": response_id,
        "response_receipt_digest": content_hash(receipt),
        "graph_revision": gs.graph_revision,
        "graph_digest": gs.graph_digest,
        "source_artifact_digest": plan_digest,
        "authority_id": authority["authority_id"],
        "authority_scope": authority["scope"],
        "authority_scope_digest": content_hash(authority["scope"]),
        "validation_result": "accepted",
    }
    record = {
        "schema_version": 6,
        "expansion_id": expansion_id,
        "plan_id": plan.get("plan_id", ""),
        "status": "pending",
        "campaign_id": plan.get("campaign_id", ""),
        "cycle_id": plan.get("cycle_id", ""),
        "base_graph_revision": gs.graph_revision,
        "base_graph_digest": gs.graph_digest,
        "plan_digest": plan_digest,
        "canonical_digest": plan_digest,
        "canonical_size": len(exact),
        "provenance": provenance,
        "created_at": utc_now(),
    }
    atomic_write(retained_plan_path, exact)
    write_json(retained_record_path, record)
    staging_path = run_root / "transactions" / "staging" / f"{expansion_id}.staged.json"
    atomic_write(staging_path, exact)
    return record


def record_response_receipt(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, content_hash, utc_now, write_json
    from graph_v6 import compute_graph_digest

    run_root = Path(args.run)
    receipt = load_json(Path(args.receipt))

    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    _verify_receipt_auth(run_root, receipt)

    run = load_json(run_path)
    run_id = run.get("run_id", "")

    replay = _retain_response_evidence(run_root, receipt)
    if replay is not None:
        return replay

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "response",
        "recorded": True,
        "response_id": receipt.get("response_id", ""),
        "receipt_digest": content_hash(receipt),
        "recorded_at": utc_now(),
    }

    binding_errors = _response_binding_errors(run_root, receipt)
    if binding_errors:
        result.update({
            "authoritative": False,
            "operation": "resume_job",
            "job_id": receipt.get("job_id", ""),
            "session_ref": receipt.get("session_ref", ""),
            "correction": "; ".join(binding_errors),
        })
        return _persist_response_result(
            run_root, receipt["response_id"], result
        )

    gs = _load_graph_state(run_root)
    if gs is None:
        result.update({
            "authoritative": False,
            "correction": "graph state is unavailable",
        })
        return _persist_response_result(
            run_root, receipt["response_id"], result
        )

    if run.get("status") != "active" or gs.status in {"canceling", "sealed"}:
        result.update({
            "authoritative": False,
            "operation": "evidence_recorded",
            "job_id": receipt.get("job_id", ""),
            "reason": "run is canceled, canceling, sealed, or otherwise inactive",
        })
        return _persist_response_result(
            run_root, receipt["response_id"], result
        )

    if gs is not None:
        goal_gate_ids = receipt.get("goal_gate_result_ids", [])
        finding_disp_ids = receipt.get("finding_disposition_ids", [])
        _validate_goal_gate_results(gs, goal_gate_ids, run_id)
        _validate_finding_dispositions(gs, finding_disp_ids, run_id)

        _normalize_verifier_wire_results(receipt)

        job_id = receipt.get("job_id", "")
        typed_errors = _validate_role_typed_result(gs, job_id, receipt)
        if typed_errors:
            result.update({
                "authoritative": False,
                "operation": "resume_job",
                "job_id": job_id,
                "session_ref": receipt.get("session_ref", ""),
                "correction": "; ".join(typed_errors),
            })
            return _persist_response_result(
                run_root, receipt["response_id"], result
            )

        typed_persisted = _persist_typed_result(run_root, receipt)
        if typed_persisted:
            result["typed_result_ref"] = typed_persisted

    job_id = receipt.get("job_id", "")
    runtime_updates: dict[str, Any] | None = None
    if gs is not None and job_id in gs._jobs and run.get("status") == "active":
        response_status = receipt.get("status")
        if response_status == "needs_input":
            runtime_updates = {
                "status": "waiting",
                "question": receipt.get("question", ""),
                "session_ref": receipt.get("session_ref", ""),
            }
        elif response_status == "failed":
            runtime_updates = {
                "status": "failed",
                "execution_status": "failure",
                "completion_status": "failed",
            }
        else:
            runtime_updates = {
                "status": "completed",
                "execution_status": "success",
                "completion_status": "success",
                "report_accepted": True,
                "evidence_refs": receipt.get("evidence_refs", []),
            }
            condition_result = receipt.get("condition_result")
            if isinstance(condition_result, dict):
                # D16: derive the verdict server-side rather than trusting a
                # client-supplied "verdict"; mirror the derivation used in the
                # authoritative verification/acceptance block below.
                _wire_status = condition_result.get("wire_status", "")
                if _wire_status:
                    _derived_verdict = _WIRE_TO_VERDICT.get(_wire_status, "unknown")
                else:
                    _derived_verdict = _RECORD_STATUS_TO_VERDICT.get(
                        condition_result.get("status", ""), "unknown"
                    )
                runtime_updates.update({
                    # NOTE: this sets verification_passed on the SUBMITTING
                    # verifier's OWN job record (self-reported execution status).
                    # It is server-derived, but it carries NO target-acceptance
                    # authority: check_verification_edge (graph_v6.py) reads the
                    # TARGET job's verification_passed, which is set only through
                    # the owned-assignment path below. Do not couple this self
                    # field to target acceptance.
                    "verification_passed": _derived_verdict == "pass",
                    "condition_id": condition_result.get("condition_id"),
                    "target_gate_revision": condition_result.get("target_gate_revision"),
                    "target_job_id": condition_result.get("target_job_id"),
                })

    if receipt.get("status") == "needs_input" and receipt.get("question"):
        result["operation"] = "ask_user"
        result["question"] = receipt["question"]
        result["session_ref"] = receipt.get("session_ref", "")
        result["job_id"] = receipt.get("job_id", "")

        job_id = receipt.get("job_id", "")
        session_ref = receipt.get("session_ref", "")
        if job_id and session_ref:
            job_dir = run_root / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            session_path = job_dir / "session.json"
            session_data = {"session_ref": session_ref, "updated_at": utc_now()}
            write_json(session_path, session_data)
    else:
        result["operation"] = "resume_job"
        result["session_ref"] = receipt.get("session_ref", "")
        result["job_id"] = receipt.get("job_id", "")

        job_id = receipt.get("job_id", "")
        session_ref = receipt.get("session_ref", "")
        if job_id and session_ref:
            job_dir = run_root / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            session_path = job_dir / "session.json"
            session_data = {"session_ref": session_ref, "updated_at": utc_now()}
            write_json(session_path, session_data)

    expansion_plan = receipt.get("expansion_plan")
    if expansion_plan and gs is not None:
        authority_errors, authority = _validate_expansion_authority(
            gs, receipt, expansion_plan
        )
        batch_correction = None
        plan_batches = expansion_plan.get("batches", [])
        for plan_batch in plan_batches:
            batch_id = plan_batch.get("batch_id", "")
            existing = gs._batches.get(batch_id)
            if existing and existing.get("status") in ("sealed", "complete"):
                batch_correction = (
                    f"sealed or settled batch {batch_id}; "
                    "cannot add new membership"
                )
                break

        if authority_errors or batch_correction:
            corrections = list(authority_errors)
            if batch_correction:
                corrections.append(batch_correction)
            result["correction"] = "; ".join(corrections)
            result["authoritative"] = False
        else:
            assert authority is not None
            expansion = _retain_expansion_plan(
                run_root, run_id, gs, receipt, expansion_plan, authority
            )
            result["expansion"] = expansion
            result["authoritative"] = True

    goal_judgment = receipt.get("goal_judgment")
    if goal_judgment and gs is not None:
        decision = goal_judgment.get("decision", "")
        if decision == "GOAL_ACHIEVED":
            open_batches = [
                bid for bid, b in gs._batches.items()
                if b.get("status") == "open"
            ]
            if open_batches:
                result["correction"] = (
                    f"batch {open_batches[0]} is open; "
                    "goal cannot be achieved with pending batches"
                )
                result["operation"] = "resume_job"
                result["session_ref"] = receipt.get("session_ref", "")
                result["job_id"] = receipt.get("job_id", "")
                if runtime_updates is not None:
                    _update_runtime_job(run_root, gs, job_id, {
                        "status": "running",
                        "session_ref": receipt.get("session_ref", ""),
                    })
                return _persist_response_result(
                    run_root, receipt["response_id"], result
                )

        from graph_v6 import (
            GraphStatus,
            TerminalOutcomeRecorder,
            compute_graph_digest,
        )
        outcome_map = {
            "GOAL_ACHIEVED": "successful",
            "BLOCKED": "blocked",
            "INFEASIBLE": "infeasible",
            "BLOCKED_NO_PROGRESS": "no_progress",
            "BUDGET_EXHAUSTED": "budget",
        }
        _OUTCOME_TO_RUN_STATUS = {
            "successful": "completed",
            "blocked": "failed",
            "infeasible": "failed",
            "no_progress": "failed",
            "budget": "failed",
            "failed": "failed",
        }
        outcome_type = outcome_map.get(decision)
        if outcome_type and gs.status != GraphStatus.SEALED:
            gs.status = GraphStatus.SEALED
            gs.graph_digest = compute_graph_digest(gs)
            TerminalOutcomeRecorder.record_terminal_outcome(
                gs, outcome_type, goal_judge_decision=decision
            )
            gs.save(run_root / "graph" / "graph.json")
            run["status"] = _OUTCOME_TO_RUN_STATUS.get(outcome_type, "failed")
            run["graph_revision"] = gs.graph_revision
            run["graph_digest"] = gs.graph_digest
            from orchestrator_core import validate_record
            validate_record("run", run)
            write_json(run_path, run)
        result["terminal"] = {"outcome_type": outcome_type or "unknown"}
        result["operation"] = "resume_job"
        result["session_ref"] = receipt.get("session_ref", "")
        result["job_id"] = receipt.get("job_id", "")

    if runtime_updates is not None:
        if result.get("correction"):
            runtime_updates = {
                "status": "running",
                "session_ref": receipt.get("session_ref", ""),
            }
        _update_runtime_job(run_root, gs, job_id, runtime_updates)

        condition_result = receipt.get("condition_result")
        if isinstance(condition_result, dict) and gs is not None:
            from graph_v6 import VerificationResultApplier, TargetAccepter
            # D16: derive the verdict server-side. The plural wire form already
            # sets a server-derived verdict via _normalize_verifier_wire_results;
            # for the singular form we map the normalized wire/record status here
            # rather than trusting a client-supplied "verdict" field for the
            # accept decision.
            wire_status = condition_result.get("wire_status", "")
            record_status = condition_result.get("status", "")
            if wire_status:
                verdict = _WIRE_TO_VERDICT.get(wire_status, "unknown")
            else:
                verdict = _RECORD_STATUS_TO_VERDICT.get(record_status, "unknown")
            assignment_id = condition_result.get("assignment_id", "")
            evidence_refs = condition_result.get("evidence_refs", [])
            condition_result_id = condition_result.get("condition_id", "")

            if assignment_id and assignment_id in gs._verifier_assignments:
                # D15: verification/acceptance is a server-authored decision. The
                # assignment must be owned by the authenticated submitter
                # (receipt["job_id"], bound by the receipt HMAC and dispatch
                # binding). Reject cross-verifier submissions before any mutation.
                assignment = gs._verifier_assignments[assignment_id]
                if assignment.get("verifier_job_id") != job_id:
                    result["authoritative"] = False
                    result["correction"] = (
                        f"verifier {job_id!r} does not own assignment "
                        f"{assignment_id!r} (assigned to "
                        f"{assignment.get('verifier_job_id')!r}); "
                        "verification and acceptance refused"
                    )
                else:
                    try:
                        applier = VerificationResultApplier(gs)
                        applier.apply_verification_result(
                            assignment_id, verdict, evidence_refs, condition_result_id
                        )

                        if verdict == "pass":
                            target_job_id = condition_result.get("target_job_id", "")
                            if target_job_id and target_job_id in gs._jobs:
                                try:
                                    accepter = TargetAccepter(gs)
                                    accepter.accept_target(
                                        target_job_id, assignment_id, verdict, evidence_refs
                                    )
                                    _update_runtime_job(run_root, gs, target_job_id, {
                                        "verification_passed": True,
                                        "condition_id": condition_result.get("condition_id"),
                                        "target_gate_revision": condition_result.get("target_gate_revision"),
                                    })
                                except OrchestratorError as _err:
                                    condition_result["acceptance_warning"] = str(_err)
                    except OrchestratorError as _err:
                        condition_result["verification_warning"] = str(_err)
            elif assignment_id:
                # assignment_id was supplied but is unknown to the graph.
                result["authoritative"] = False
                result["correction"] = (
                    f"verifier assignment {assignment_id!r} is not present in the "
                    "graph; verification and acceptance refused"
                )
            # No `assignment_id`: there is no owned assignment to authorize a
            # target acceptance, so the handler MUST NOT mark any target
            # verification_passed here. Doing so previously let a verifier set
            # verification_passed on a client-named target with no ownership
            # check (D15 bypass). Target acceptance is only authoritative through
            # the owned-assignment path above.

            # Surface verification/acceptance warnings in the handler's return
            # value so they are persisted with the response result instead of
            # being confined to the in-memory receipt.
            for _warning_key in ("verification_warning", "acceptance_warning"):
                if _warning_key in condition_result:
                    result[_warning_key] = condition_result[_warning_key]

            gs.save(run_root / "graph" / "graph.json")

    if "authoritative" not in result:
        result["authoritative"] = True

    return _persist_response_result(run_root, receipt["response_id"], result)


def ask_user(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, utc_now
    from queue_backend import FileQueueBackend

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    if run.get("status") != "active":
        raise OrchestratorError("run is not active")

    backend = FileQueueBackend()
    question_id = backend.enqueue_question(
        run_root,
        args.job,
        args.question,
        context=getattr(args, "context", "") or "",
    )

    print(f"[WORKER QUESTION]")
    print(f"Question ID: {question_id}")
    print(f"Job ID: {args.job}")
    print(f"Run: {run_root}")
    print(f"---")
    print(f"{args.question}")
    if getattr(args, "context", ""):
        print(f"---")
        print(f"Context: {args.context}")

    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "ask_user",
        "question_id": question_id,
        "job_id": args.job,
        "question": args.question,
        "recorded_at": utc_now(),
    }


def record_answer(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, utc_now, write_json
    from queue_backend import FileQueueBackend

    run_root = Path(args.run)
    question_id = getattr(args, "question_id", None)

    if question_id:
        backend = FileQueueBackend()
        record = backend.record_answer(run_root, question_id, args.answer)
        job_id = record.get("job_id", "")
    else:
        job_id = args.job

    if not job_id:
        raise OrchestratorError("must specify --job or --question-id")

    session_ref = ""
    session_path = run_root / "jobs" / job_id / "session.json"
    if session_path.exists():
        session_data = load_json(session_path)
        session_ref = session_data.get("session_ref", "")

    job_path = run_root / "jobs" / job_id / "job.json"
    if job_path.exists():
        job = load_json(job_path)
        job["status"] = "running"
        job["revision"] = job.get("revision", 0) + 1
        job.pop("question", None)
        job["updated_at"] = utc_now()
        write_json(job_path, job)

    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "resume_job",
        "repeat_domain_work": False,
        "job_id": job_id,
        "question_id": question_id,
        "answer": args.answer,
        "session_ref": session_ref,
        "recorded_at": utc_now(),
    }


def list_pending(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION
    from queue_backend import FileQueueBackend

    run_root = Path(args.run)
    backend = FileQueueBackend()
    pending = backend.get_pending_questions(run_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "pending": pending,
        "count": len(pending),
    }


def commit_expansion(args: argparse.Namespace) -> dict[str, Any]:
    run_root = Path(args.run)
    from transaction_v6 import DurableExpansionTransaction

    return DurableExpansionTransaction(
        run_root,
        fault_at=getattr(args, "fault_at", None),
    ).commit(
        expansion_id=args.expansion_id,
        plan_digest=args.plan_digest,
        expected_graph_revision=args.expected_graph_revision,
        expected_graph_digest=args.expected_graph_digest,
    )


def audit(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, V6, utc_now, content_hash
    from graph_v6 import GraphState, compute_graph_digest
    from audit_v6 import DynamicAuditor, AuditReporter, FindingClassification

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    version = run.get("schema_version")
    protocol_revision = run.get("protocol_revision")
    is_trusted = version == V6 and protocol_revision == "v6-closed"

    run_protocol_hash = run.get("protocol_hash")

    graph_path = run_root / "graph.json"
    try:
        gs = GraphState.load(graph_path)
    except Exception as e:
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": False,
            "trusted": is_trusted,
            "version": version,
            "protocol_revision": protocol_revision,
            "graph": {
                "revision": run.get("graph_revision", 1),
                "digest": run.get("graph_digest", "0" * 64),
                "status": "active" if run.get("status") == "active" else run.get("status", "unknown"),
            },
            "obligations": {},
            "error": f"graph not found or invalid: {e}",
            "audit_digest": utc_now(),
        }

    rebuild = getattr(args, "rebuild", False)
    if rebuild:
        gs.graph_digest = compute_graph_digest(gs)
        gs.save(graph_path)
        run["graph_digest"] = gs.graph_digest
        write_json(run_path, run)

    auditor = DynamicAuditor(gs)
    auditor.run_all(run_protocol_hash=run_protocol_hash)
    reporter = AuditReporter(auditor.findings)
    report = reporter.generate_audit_report()

    active_idle_findings = [
        f for f in auditor.findings
        if f.classification == FindingClassification.ACTIVE_IDLE_CONTRADICTION
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "valid": reporter.validate_actionability(),
        "trusted": is_trusted,
        "version": version,
        "protocol_revision": protocol_revision,
        "graph": {
            "revision": gs.graph_revision,
            "digest": gs.graph_digest,
            "status": "active" if run.get("status") == "active" else run.get("status", "unknown"),
        },
        "obligations": {},
        "blocks_resume": report["facts"]["blocks_resume"],
        "active_idle_contradiction": len(active_idle_findings) > 0,
        "rebuild_performed": rebuild,
        "audit_report": report,
        "audit_digest": utc_now(),
    }


def recover(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, utc_now
    from audit_v6 import FindingClassification
    from transaction_v6 import ExpansionRecovery

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    job_id = args.job
    evidence_path = args.evidence
    transaction_id = getattr(args, "transaction", None)
    dry_run = getattr(args, "dry_run", False)

    if transaction_id:
        staging_dir = run_root / "transactions" / "staging"
        manifest_dir = run_root / "transactions" / "manifests"
        graph_state_path = run_root / "graph.json"

        recovery = ExpansionRecovery(
            staging_dir=staging_dir,
            manifest_dir=manifest_dir,
            graph_state_path=graph_state_path,
        )

        manifest_errors = recovery.validate_manifest(transaction_id)
        contradictory_errors = recovery.block_contradictory(transaction_id)
        errors = manifest_errors + contradictory_errors

        if errors:
            return {
                "schema_version": SCHEMA_VERSION,
                "recovery_action": "blocked",
                "transaction_id": transaction_id,
                "reason": "; ".join(errors),
                "recorded_at": utc_now(),
            }

        if dry_run:
            return {
                "schema_version": SCHEMA_VERSION,
                "recovery_action": "dry_run",
                "transaction_id": transaction_id,
                "would_recover": True,
                "proposed_action": "recover_from_crash",
                "recorded_at": utc_now(),
            }

        try:
            result = recovery.recover_from_crash(transaction_id)
            result["schema_version"] = SCHEMA_VERSION
            result["recorded_at"] = utc_now()
            return result
        except Exception as e:
            return {
                "schema_version": SCHEMA_VERSION,
                "recovery_action": "blocked",
                "transaction_id": transaction_id,
                "reason": str(e),
                "recorded_at": utc_now(),
            }

    if job_id and evidence_path:
        evidence = load_json(Path(evidence_path))
        classification = evidence.get("classification", "unknown")

        if dry_run:
            proposed_action = "none"
            if classification == FindingClassification.COMPLETED_RESULT_NOT_APPLIED:
                proposed_action = "apply_validated_result"
            elif classification in (
                FindingClassification.INTERRUPTED_DISPATCH_RECORDED_NOT_SENT,
                FindingClassification.INTERRUPTED_DISPATCH_SENT_NO_RESULT,
            ):
                proposed_action = "classify_and_recover_dispatch"
            elif classification == FindingClassification.EXTERNAL_EFFECT_UNKNOWN:
                proposed_action = "run_recovery_check"
            elif classification == FindingClassification.STALE_INDEX_OR_QUEUE:
                proposed_action = "rebuild_from_authoritative_evidence"
            elif classification == FindingClassification.DERIVED_SNAPSHOT_DRIFT:
                proposed_action = "rebuild_derived_snapshots"

            return {
                "schema_version": SCHEMA_VERSION,
                "recovery_action": "dry_run",
                "result": classification,
                "proposed_action": proposed_action,
                "would_mutate": classification not in (
                    FindingClassification.CLEAN,
                    FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT,
                    FindingClassification.EXTERNAL_EFFECT_UNKNOWN,
                    FindingClassification.PROTOCOL_HASH_MISMATCH,
                ),
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        if classification == FindingClassification.EXTERNAL_EFFECT_UNKNOWN:
            return {
                "schema_version": SCHEMA_VERSION,
                "result": classification,
                "replacement_authorized": False,
                "status": "blocked",
                "reason": "external effect state unknown; recovery check required before retry",
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        if classification == FindingClassification.PROTOCOL_HASH_MISMATCH:
            return {
                "schema_version": SCHEMA_VERSION,
                "result": classification,
                "replacement_authorized": False,
                "status": "blocked",
                "reason": "protocol hash mismatch; automatic recovery unsafe",
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        if classification == FindingClassification.JOURNAL_CORRUPT_OR_INSUFFICIENT:
            return {
                "schema_version": SCHEMA_VERSION,
                "result": classification,
                "replacement_authorized": False,
                "status": "blocked",
                "reason": "journal evidence insufficient; recovery investigation required",
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        if classification == FindingClassification.COMPLETED_RESULT_NOT_APPLIED:
            return {
                "schema_version": SCHEMA_VERSION,
                "result": classification,
                "replacement_authorized": False,
                "status": "recovered",
                "recovery_action": "apply_validated_result",
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        if classification == FindingClassification.STALE_INDEX_OR_QUEUE:
            return {
                "schema_version": SCHEMA_VERSION,
                "result": classification,
                "replacement_authorized": False,
                "status": "recovered",
                "recovery_action": "rebuild_index",
                "job_id": job_id,
                "recorded_at": utc_now(),
            }

        return {
            "schema_version": SCHEMA_VERSION,
            "result": classification,
            "replacement_authorized": False,
            "status": "blocked" if classification == "unknown" else "recovered",
            "job_id": job_id,
            "recorded_at": utc_now(),
        }

    run = load_json(run_path)
    if run.get("status") != "active":
        return {
            "schema_version": SCHEMA_VERSION,
            "result": "run_not_active",
            "status": "clean",
            "recorded_at": utc_now(),
        }

    if dry_run:
        return {
            "schema_version": SCHEMA_VERSION,
            "recovery_action": "dry_run",
            "result": "control_plane_recovery",
            "proposed_action": "recover_interrupted_control_plane_commit",
            "would_mutate": False,
            "recorded_at": utc_now(),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "result": "no_action",
        "status": "clean",
        "recorded_at": utc_now(),
    }


def repair_run(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, utc_now

    return {
        "schema_version": SCHEMA_VERSION,
        "repaired": True,
        "job_id": args.job,
        "disposition": args.disposition,
        "reason": args.reason,
        "recorded_at": utc_now(),
    }


def cancel_run(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, utc_now, validate_record, write_json
    from graph_v6 import GraphState, GraphStatus

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    run["status"] = "cancelled"
    validate_record("run", run)
    write_json(run_path, run)

    graph_path = run_root / "graph" / "graph.json"
    if graph_path.exists():
        gs = GraphState.load(graph_path)
        if gs.status != GraphStatus.SEALED:
            gs.status = GraphStatus.SEALED
            gs.save(graph_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_status": "cancelled",
        "reason": args.reason,
        "recorded_at": utc_now(),
    }


def advance_cycle(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, stable_id, utc_now, write_json

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    if run.get("status") != "active":
        raise OrchestratorError(f"run is not active; status: {run.get('status')}")

    run_id = run.get("run_id", "")
    previous_cycle_id = run.get("current_cycle_id", "")
    new_cycle_id = stable_id("CYC", run_id, utc_now()) if not previous_cycle_id else stable_id("CYC", previous_cycle_id, utc_now())

    run["current_cycle_id"] = new_cycle_id
    write_json(run_path, run)

    return {
        "schema_version": SCHEMA_VERSION,
        "previous_cycle_id": previous_cycle_id,
        "new_cycle_id": new_cycle_id,
        "recorded_at": utc_now(),
    }


def create_finalization_worker(args: argparse.Namespace) -> dict[str, Any]:
    from orchestrator_core import SCHEMA_VERSION, stable_id, utc_now

    run_root = Path(args.run)
    run_path = run_root / "run.json"
    if not run_path.exists():
        raise OrchestratorError(f"run not found: {run_root}")

    run = load_json(run_path)
    run_id = run.get("run_id", "")
    job_id = args.job
    authority_id = args.authority
    side_effect_type = args.side_effect_type
    side_effect_config = load_json(Path(args.config)) if args.config else {}

    graph_path = run_root / "graph" / "graph_state.json"
    if not graph_path.exists():
        raise OrchestratorError(f"graph state not found: {graph_path}")

    from graph_v6 import GraphState, get_job
    gs = GraphState.load(graph_path)
    authority_job = get_job(gs, authority_id)
    if authority_job is None:
        raise OrchestratorError(f"authority job {authority_id!r} not found")
    if authority_job.get("role") not in ("review-authority", "architect-review"):
        raise OrchestratorError(
            f"authority {authority_id!r} role is {authority_job.get('role')!r}; "
            f"expected review-authority or architect-review"
        )

    worker_job_id = stable_id("JOB", run_id, job_id, utc_now())
    worker_record = {
        "schema_version": SCHEMA_VERSION,
        "job_id": worker_job_id,
        "role": "finalization-worker",
        "purpose_key": "repository-side-effect",
        "graph_generation": authority_job.get("graph_generation", 1),
        "expansion_origin": authority_job.get("job_id", ""),
        "authority_id": authority_id,
        "context_snapshot_id": authority_job.get("context_snapshot_id", ""),
        "title": f"finalization-{side_effect_type}",
        "status": "pending",
        "side_effect": {
            "type": side_effect_type,
            "config": side_effect_config,
            "idempotency_key": stable_id("SE", run_id, job_id, side_effect_type),
        },
        "created_at": utc_now(),
    }

    gs._jobs[worker_job_id] = worker_record
    gs.save(graph_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "worker_job_id": worker_job_id,
        "authority_id": authority_id,
        "side_effect_type": side_effect_type,
        "recorded_at": utc_now(),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--controller", default="jobctl")

    init = sub.add_parser("init", parents=[common], help="Initialize a new run or resume an existing one")
    init.add_argument("--request-file", type=Path)
    init.add_argument("--goal")
    init.add_argument("--run-id")
    init.add_argument("--name", help="custom slug for the run folder name")
    init.add_argument(
        "--state-root",
        type=Path,
        default=Path.cwd() / ".job-orchestrator" / "runs",
    )
    init.add_argument("--workspace", type=Path, default=Path.cwd())
    init.add_argument(
        "--test-harness",
        action="store_true",
        help="allow a deterministic test-only adapter",
    )
    init.add_argument(
        "--mode",
        choices=(
            "full", "full_campaign", "proposal-only", "proposal_only",
            "implementation-from-proposal", "implementation_from_proposal",
            "architect-review-only", "architect_review_only", "resume", "custom",
        ),
    )
    init.add_argument("--review-target")
    init.add_argument("--entry-artifact", action="append", default=[])
    init.add_argument("--strategy-config", type=Path)
    init.add_argument("--resume-run", type=Path)

    register = sub.add_parser("register", parents=[common], help="Register job definitions for a run")
    register.add_argument("--run", type=Path, required=True)
    register.add_argument("--definition", type=Path, required=True)

    nxt = sub.add_parser("next", parents=[common], help="Get the next operation for the orchestrator")
    nxt.add_argument("--run", type=Path, required=True)

    prepare = sub.add_parser("prepare-dispatch", parents=[common], help="Prepare a job dispatch with CAS validation")
    prepare.add_argument("--run", type=Path, required=True)
    prepare.add_argument("--job", required=True)
    prepare.add_argument("--expected-revision", type=int, required=True)
    prepare.add_argument("--expected-job-revision", type=int)
    prepare.add_argument("--expected-graph-revision", type=int, required=True)
    prepare.add_argument("--expected-graph-digest", required=True)
    prepare.add_argument("--dependency-evidence-digest", required=True)

    launch = sub.add_parser("launch-receipt", parents=[common], help="Record an authenticated launch receipt")
    launch.add_argument("--run", type=Path, required=True)
    launch.add_argument("--receipt", type=Path, required=True)

    response = sub.add_parser("response-receipt", parents=[common], help="Record an authenticated response receipt")
    response.add_argument("--run", type=Path, required=True)
    response.add_argument("--receipt", type=Path, required=True)

    ask = sub.add_parser("ask", parents=[common], help="Enqueue a question for the user")
    ask.add_argument("--run", type=Path, required=True)
    ask.add_argument("--job", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--context", default="")

    answer = sub.add_parser("answer", parents=[common], help="Record an answer to a pending question")
    answer.add_argument("--run", type=Path, required=True)
    answer.add_argument("--job", default="")
    answer.add_argument("--question-id", dest="question_id", default="")
    answer.add_argument("--answer", required=True)

    pending = sub.add_parser("pending", parents=[common], help="List pending unanswered questions")
    pending.add_argument("--run", type=Path, required=True)

    commit_exp = sub.add_parser("commit-expansion", parents=[common], help="Commit a retained graph expansion")
    commit_exp.add_argument("--run", type=Path, required=True)
    commit_exp.add_argument("--expansion", required=True, dest="expansion_id")
    commit_exp.add_argument("--expansion-data", type=Path, default=None)
    commit_exp.add_argument("--expected-graph-revision", type=int, required=True)
    commit_exp.add_argument("--expected-graph-digest", required=True)
    commit_exp.add_argument("--plan-digest", required=True)
    commit_exp.add_argument("--fault-at")

    aud = sub.add_parser("audit", parents=[common], help="Validate run state integrity")
    aud.add_argument("--run", type=Path, required=True)
    aud.add_argument(
        "--rebuild",
        action="store_true",
        help="rebuild derived snapshots from authoritative journal before auditing",
    )

    recovery = sub.add_parser("recover", parents=[common], help="Recover interrupted work or transactions")
    recovery.add_argument("--run", type=Path, required=True)
    recovery.add_argument("--job")
    recovery.add_argument("--evidence", type=Path)
    recovery.add_argument("--transaction")
    recovery.add_argument("--fault-at")
    recovery.add_argument(
        "--dry-run",
        action="store_true",
        help="classify and propose recovery without mutating state",
    )

    repair = sub.add_parser("repair", parents=[common], help="Mark a job as failed or canceled")
    repair.add_argument("--run", type=Path, required=True)
    repair.add_argument("--job", required=True)
    repair.add_argument("--disposition", choices=("failed", "canceled"), required=True)
    repair.add_argument("--reason", required=True)

    cancel = sub.add_parser("cancel", parents=[common], help="Cancel a run")
    cancel.add_argument("--run", type=Path, required=True)
    cancel.add_argument("--reason", required=True)

    advance = sub.add_parser("advance-cycle", parents=[common], help="Advance to the next campaign cycle")
    advance.add_argument("--run", type=Path, required=True)

    finalizer = sub.add_parser("create-finalization-worker", parents=[common], help="Create a finalization worker job")
    finalizer.add_argument("--run", type=Path, required=True)
    finalizer.add_argument("--job", required=True)
    finalizer.add_argument("--authority", required=True)
    finalizer.add_argument("--side-effect-type", required=True)
    finalizer.add_argument("--config", type=Path, default=None)

    return root


def main() -> int:
    args = parser().parse_args()
    handlers = {
        "init": init_run,
        "register": register_jobs,
        "next": next_action,
        "prepare-dispatch": prepare_dispatch,
        "launch-receipt": record_launch_receipt,
        "response-receipt": record_response_receipt,
        "ask": ask_user,
        "answer": record_answer,
        "pending": list_pending,
        "commit-expansion": commit_expansion,
        "audit": audit,
        "recover": recover,
        "repair": repair_run,
        "cancel": cancel_run,
        "advance-cycle": advance_cycle,
        "create-finalization-worker": create_finalization_worker,
    }
    try:
        emit(handlers[args.command](args))
        return 0
    except OrchestratorError as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
