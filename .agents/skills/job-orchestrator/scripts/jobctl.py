#!/usr/bin/env python3
"""Deterministic, transport-neutral job-orchestrator control plane."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from orchestrator_core import (
    ACTIVE_DISPATCHES, PROTOCOL_VERSION, SCHEMA_VERSION, TERMINAL_JOBS,
    OrchestratorError, append_event, atomic_write, content_hash, effective_policy,
    load_json, make_event, mutate, parse_time, read_jsonl, replay, run_lease,
    stable_id, utc_now, validate_dispatch, validate_record, write_json,
    write_snapshots,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_ROOT / "assets" / "prompts"
PROTOCOL = SKILL_ROOT / "references" / "job-protocol.md"
TERMINAL_RUNS = {"completed", "failed", "cancelled"}
RECOVERY_CLASSIFICATION_TO_FINDING = {
    "recorded_unsent": "interrupted_dispatch_recorded_not_sent",
    "completed_unrecorded": "completed_result_not_applied",
    "externally_effective_unacknowledged": "external_effect_unknown",
    "running_resumable": "interrupted_dispatch_sent_no_result",
    "safe_retry": "interrupted_dispatch_sent_no_result",
    "sent_unstarted": "interrupted_dispatch_sent_no_result",
    "unsafe_retry": "external_effect_unknown",
    "unanswered_status": "interrupted_dispatch_sent_no_result",
    "no_interrupted_dispatch": "clean",
}
AUTOMATIC_RECOVERY_FINDINGS = {
    "clean",
    "derived_snapshot_drift",
    "stale_index_or_queue",
    "interrupted_dispatch_recorded_not_sent",
    "completed_result_not_applied",
}


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def render(name: str, **values: Any) -> str:
    text = (TEMPLATES / f"{name}.txt").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def init_run(args: argparse.Namespace) -> dict[str, Any]:
    now = utc_now()
    run_id = args.run_id or stable_id("RUN", args.goal, now)
    run_root = args.state_root.resolve() / run_id
    if run_root.exists():
        raise OrchestratorError(f"run already exists: {run_root}")
    (run_root / "jobs").mkdir(parents=True)
    (run_root / "protocol").mkdir()
    protocol_bytes = PROTOCOL.read_bytes()
    protocol_hash = content_hash(protocol_bytes)
    shutil.copyfile(PROTOCOL, run_root / "protocol" / "job-protocol.md")
    request = args.request_file.read_text(encoding="utf-8") if args.request_file else args.request
    (run_root / "request.md").write_text(request, encoding="utf-8")
    for name in ("events.jsonl", "decisions.jsonl", "improvements.jsonl"):
        (run_root / name).touch()
    write_json(run_root / "protocol" / "manifest.json", {
        "protocol_version": 3, "file": "job-protocol.md", "sha256": protocol_hash,
        "source": "references/job-protocol.md", "snapshotted_at": now,
    })
    setup = {
        "goal": args.goal, "requirements": [], "acceptance_criteria": [],
        "roles": {}, "job_types": {},
        "policies": json.loads(json.dumps(effective_policy(Path("__missing__")))),
    }
    write_json(run_root / "setup.json", setup)
    run_seed = {
        "schema_version": 3, "run_id": run_id, "status": "initializing",
        "goal": args.goal, "created_at": now, "updated_at": now,
        "workspace": str(args.workspace.resolve()), "state_root": str(args.state_root.resolve()),
        "protocol": {"manifest_path": "protocol/manifest.json", "version": 3, "sha256": protocol_hash},
        "skill_source": {"path": str(SKILL_ROOT), "update_scope": "future_runs"},
        "revision": 0, "mode": "sequential",
        "active_job_id": None, "active_dispatch_id": None,
    }
    write_json(run_root / "protocol" / "run-seed.json", run_seed)
    write_json(run_root / "run.json", run_seed)
    event = make_event(run_root, "run_status", run_id, {"status": "active"})
    mutate(run_root, args.controller, event)
    return {"run_root": str(run_root), "run_id": run_id}


def _validate_jobs(document: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = document.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise OrchestratorError("definition must contain a non-empty jobs array")
    ids = [job.get("id") for job in jobs]
    if None in ids or len(ids) != len(set(ids)):
        raise OrchestratorError("job IDs must be present and unique")
    known = set(ids)
    for sequence, job in enumerate(jobs, 1):
        for field in ("title", "goal", "role", "workflow"):
            if not job.get(field):
                raise OrchestratorError(f"job {job['id']} missing {field}")
        if any(dep not in known for dep in job.get("depends_on", [])):
            raise OrchestratorError(f"job {job['id']} has unknown dependency")
        nodes = job["workflow"].get("nodes", [])
        positions = [node.get("position") for node in nodes]
        if not nodes or None in positions or len(positions) != len(set(positions)):
            raise OrchestratorError(f"job {job['id']} needs unique workflow positions")
        for node in nodes:
            if node.get("run_in", "job_session") not in {"job_session", "child_job"}:
                raise OrchestratorError("unsupported workflow execution target")
            if not node.get("work_units"):
                raise OrchestratorError(f"node {node.get('id')} requires work_units")
        job.setdefault("sequence", sequence)
    visiting: set[str] = set()
    visited: set[str] = set()
    graph = {job["id"]: job.get("depends_on", []) for job in jobs}
    def visit(job_id: str) -> None:
        if job_id in visiting:
            raise OrchestratorError("job dependency cycle detected")
        if job_id not in visited:
            visiting.add(job_id)
            for dependency in graph[job_id]:
                visit(dependency)
            visiting.remove(job_id)
            visited.add(job_id)
    for job_id in graph:
        visit(job_id)
    return jobs


def compile_jobs(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    document = load_json(args.definition)
    jobs = _validate_jobs(document)
    for raw in jobs:
        now = utc_now()
        nodes = sorted(raw["workflow"]["nodes"], key=lambda item: item["position"])
        for index, node in enumerate(nodes):
            node.setdefault("status", "ready" if index == 0 else "pending")
            node.setdefault("completed_work_units", [])
            node.setdefault("dispatch_ids", [])
        job = {
            "id": raw["id"], "title": raw["title"], "goal": raw["goal"],
            "job_type": raw.get("job_type", "implement"), "role": raw["role"],
            "priority": raw.get("priority", 50), "sequence": raw["sequence"],
            "depends_on": raw.get("depends_on", []), "status": "queued",
            "current_workflow_node_id": nodes[0]["id"], "session": None,
            "report_path": f"jobs/{raw['id']}/report.md",
            "checkpoint_path": f"jobs/{raw['id']}/checkpoint.md",
            "created_at": now, "updated_at": now, "revision": 1,
        }
        workflow = {"session_policy": "persistent", "nodes": nodes}
        steps = {"steps": [
            {"id": node["id"], "workflow_node_id": node["id"], "status": node["status"],
             "attempts": [], "result_path": None} for node in nodes
        ]}
        contract = {
            "contract_version": 3, "revision": 1, "job_id": raw["id"],
            "role": raw["role"], "goal": raw["goal"],
            "protocol": {"path": "../../protocol/job-protocol.md", "version": 3,
                         "sha256": load_json(run_root / "run.json")["protocol"]["sha256"]},
            "workspace": raw.get("workspace", load_json(run_root / "run.json")["workspace"]),
            "allowed_edit_roots": raw.get("allowed_edit_roots", []),
            "capabilities": raw.get("capabilities", []),
            "artifact_paths": raw.get("artifact_paths", ["report.md", "checkpoint.md", "progress.json", "results"]),
            "report_path": "report.md", "checkpoint_path": "checkpoint.md",
            "may_propose_jobs": True, "may_contact_user": False,
            "may_spawn_untracked_agents": False,
        }
        job["contract_sha256"] = content_hash(contract)
        job_root = run_root / "jobs" / raw["id"]
        job_root.mkdir(parents=True, exist_ok=True)
        write_json(job_root / "contract.json", contract)
        (job_root / "report.md").touch()
        (job_root / "checkpoint.md").touch()
        event = make_event(run_root, "job_compiled", raw["id"], {
            "job": job, "workflow": workflow, "steps": steps,
        })
        mutate(run_root, args.controller, event)
    return {"compiled": [job["id"] for job in jobs]}


def _unresolved(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((action for action in state["actions"].values()
                 if action["status"] == "unresolved"), None)


def _within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _job_children(state: dict[str, Any], parent_id: str) -> list[dict[str, Any]]:
    return [job for job in state["jobs"].values()
            if job.get("parent_job_id") == parent_id]


def _pending_child_requests(
    state: dict[str, Any], parent_id: str,
) -> list[dict[str, Any]]:
    return [
        request for request in state.get("child_requests", {}).values()
        if request["parent_job_id"] == parent_id
        and request["status"] != "acknowledged"
    ]


def _dependency_reaches(
    state: dict[str, Any], start: str, target: str,
) -> bool:
    pending = [start]
    seen: set[str] = set()
    while pending:
        job_id = pending.pop()
        if job_id == target:
            return True
        if job_id in seen:
            continue
        seen.add(job_id)
        pending.extend(state["jobs"].get(job_id, {}).get("depends_on", []))
    return False


def _validate_acknowledgement(
    run_root: Path, state: dict[str, Any], action: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    ack = dict(response.get("protocol_ack", response))
    validate_record("acknowledgement", ack)
    contract = load_json(run_root / "jobs" / action["job_id"] / "contract.json")
    manifest = load_json(run_root / "protocol" / "manifest.json")
    session_id = response.get("session_id") or ack.get("session_id")
    if (
        response.get("session_id") is not None
        and ack.get("session_id") is not None
        and response["session_id"] != ack["session_id"]
    ):
        raise OrchestratorError(
            "acknowledgement session_id disagrees with transport session_id"
        )
    expected = (
        PROTOCOL_VERSION, manifest["sha256"], contract["job_id"],
        contract["revision"], state["jobs"][action["job_id"]][
            "current_workflow_node_id"
        ],
    )
    actual = (
        ack.get("protocol_version"), ack.get("protocol_sha256"),
        ack.get("job_id"), ack.get("contract_revision"),
        ack.get("current_workflow_node_id"),
    )
    if actual != expected:
        raise OrchestratorError(
            "acknowledgement protocol, job, revision, or workflow node mismatch"
        )
    if not isinstance(session_id, str) or not session_id.strip():
        raise OrchestratorError("acknowledgement requires a non-empty session_id")
    bound = state["sessions"].get(action["job_id"])
    if bound and bound.get("session_id") not in {None, session_id}:
        raise OrchestratorError("acknowledgement session does not match active session")
    ack["session_id"] = session_id
    return ack


def _artifact_entry(
    item: Any, root: Path, roots: list[Path],
) -> tuple[Path, str | None]:
    if isinstance(item, str):
        raw, expected_hash = item, None
    elif isinstance(item, dict) and isinstance(item.get("path"), str):
        raw, expected_hash = item["path"], item.get("sha256")
    else:
        raise OrchestratorError("artifact entries require a path and optional sha256")
    path = Path(raw)
    path = path if path.is_absolute() else root / path
    if not _within(path, roots) or not path.is_file():
        raise OrchestratorError(f"artifact is missing or outside worker-owned paths: {raw}")
    return path, expected_hash


def _validate_worker_result(
    run_root: Path, state: dict[str, Any], action: dict[str, Any],
    response: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = response["result"]
    validate_record("result", result)
    dispatch = state["dispatches"].get(action.get("dispatch_id"))
    if not dispatch:
        raise OrchestratorError("result action has no projected dispatch")
    validate_dispatch(dispatch, effective_policy(run_root))
    session = state["sessions"].get(dispatch["job_id"])
    bindings = (
        result.get("dispatch_id"), result.get("nonce"),
        result.get("session_id", session.get("session_id") if session else None),
    )
    expected = (
        dispatch["dispatch_id"], dispatch["nonce"],
        session.get("session_id") if session else None,
    )
    if bindings != expected or expected[2] is None:
        raise OrchestratorError("result dispatch, nonce, or session binding mismatch")
    job_root = run_root / "jobs" / dispatch["job_id"]
    contract = load_json(job_root / "contract.json")
    if (
        dispatch["contract_revision"] != contract["revision"]
        or dispatch["protocol_sha256"] != contract["protocol"]["sha256"]
    ):
        raise OrchestratorError("dispatch no longer matches contract or protocol")
    report = (job_root / contract["report_path"]).resolve()
    checkpoint = (job_root / contract["checkpoint_path"]).resolve()
    progress_path = job_root / "progress.json"
    if not report.is_file() or not report.read_text(encoding="utf-8").strip():
        raise OrchestratorError("result requires a non-empty report")
    if not checkpoint.is_file() or not progress_path.is_file():
        raise OrchestratorError("result requires checkpoint and progress artifacts")
    progress = load_json(progress_path)
    validate_record("progress", progress)
    if (progress["dispatch_id"], progress["nonce"]) != (
        dispatch["dispatch_id"], dispatch["nonce"]
    ):
        raise OrchestratorError("progress is not bound to this dispatch")
    checkpoint_hash = content_hash(checkpoint.read_bytes())
    if checkpoint_hash != progress["checkpoint_sha256"] or checkpoint_hash != result[
        "checkpoint_sha256"
    ]:
        raise OrchestratorError("result checkpoint/progress hash mismatch")
    supplied_progress = response.get("progress")
    if supplied_progress is not None and content_hash(supplied_progress) != content_hash(progress):
        raise OrchestratorError("supplied progress does not match persisted progress")
    for label, path in (("report", report), ("checkpoint", checkpoint)):
        evidence = response.get(label)
        if isinstance(evidence, dict) and evidence.get("sha256") != content_hash(
            path.read_bytes()
        ):
            raise OrchestratorError(f"{label} hash mismatch")
    roots = [(job_root / item).resolve() for item in contract["artifact_paths"]]
    for artifact in result["artifacts"]:
        path, expected_hash = _artifact_entry(artifact, job_root, roots)
        if expected_hash and content_hash(path.read_bytes()) != expected_hash:
            raise OrchestratorError(f"artifact hash mismatch: {path}")
    evidence = result.get("acceptance_evidence", [])
    blockers = [item for item in result.get("blocking_issues", [])
                if isinstance(item, str) and item.strip()]
    if result["status"] in {"completed", "partial"} and not evidence:
        raise OrchestratorError("completed and partial results require acceptance evidence")
    if result["status"] == "completed" and blockers:
        raise OrchestratorError("completed result cannot contain blocking evidence")
    if result["status"] == "blocked" and not blockers:
        raise OrchestratorError("blocked result requires a precise blocking issue")
    completed = set(result.get("completed_work_units", []))
    if not completed.issubset(set(dispatch["work_units"])):
        raise OrchestratorError("result claims work units outside its dispatch")
    if result["status"] == "completed" and completed != set(dispatch["work_units"]):
        raise OrchestratorError("completed result omits dispatched work units")
    result_path = response.get("result_path")
    if result_path:
        persisted = Path(result_path)
        persisted = persisted if persisted.is_absolute() else job_root / persisted
        if not _within(persisted, roots) or load_json(persisted) != result:
            raise OrchestratorError("persisted result path or content mismatch")
    return dispatch, result


def _ready_job(state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for job in state["jobs"].values():
        if job["status"] in TERMINAL_JOBS or job["status"] == "blocked":
            continue
        dependencies = [state["jobs"][dep]["status"] for dep in job.get("depends_on", [])]
        if all(status in {"completed", "completed_with_concerns"} for status in dependencies):
            candidates.append(job)
    return min(candidates, key=lambda item: (-item["priority"], item["sequence"]), default=None)


def _make_action(run_root: Path, state: dict[str, Any], kind: str, job: dict[str, Any] | None,
                 prompt: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    run_id = state["run"]["run_id"]
    correlation = f"{job['id']}:{job.get('current_workflow_node_id')}" if job else run_id
    action = {
        "schema_version": 3,
        "action_id": stable_id("ACT", run_id, kind, correlation, len(state["actions"])),
        "type": kind, "run_id": run_id, "job_id": job["id"] if job else None,
        "status": "unresolved", "correlation_id": correlation, "created_at": utc_now(),
        "prompt": prompt,
    }
    action.update(extra or {})
    validate_record("action", action)
    return action


def _next_dispatch(run_root: Path, state: dict[str, Any], job: dict[str, Any],
                   action_id: str) -> dict[str, Any]:
    workflow = state["workflows"][job["id"]]
    node = next(item for item in workflow["nodes"]
                if item["id"] == job["current_workflow_node_id"])
    remaining = [unit for unit in node["work_units"]
                 if unit not in node.get("completed_work_units", [])]
    policy = effective_policy(run_root)
    batch = (
        remaining if node.get("unbounded_override")
        else remaining[:policy["dispatch_bounds"]["max_work_units"]]
    )
    contract = load_json(run_root / "jobs" / job["id"] / "contract.json")
    dispatch_id = stable_id("DSP", job["id"], node["id"], batch, len(node["dispatch_ids"]))
    dispatch = {
        "schema_version": 3, "dispatch_id": dispatch_id, "action_id": action_id,
        "job_id": job["id"], "workflow_node_id": node["id"],
        "nonce": stable_id("NONCE", dispatch_id, contract["revision"]),
        "contract_revision": contract["revision"],
        "protocol_sha256": contract["protocol"]["sha256"],
        "workspace": contract["workspace"],
        "allowed_edit_roots": contract.get("allowed_edit_roots", []),
        "capabilities": contract.get("capabilities", []), "work_units": batch,
        "acceptance_criteria": node.get("acceptance_criteria", ["Complete assigned work units"]),
        "required_checks": node.get("required_checks", ["Validate produced artifacts"]),
        "prohibited_actions": node.get("prohibited_actions", ["Do not begin later workflow nodes"]),
        "checkpoint_policy": node.get("checkpoint_policy", ["after_discovery", "after_each_batch", "before_blocker"]),
        "side_effect_class": node.get("side_effect_class", "workspace_write"),
        "recovery_check": node.get("recovery_check", "Inspect workspace changes and checkpoint before retry"),
        "estimated_minutes": node.get("estimated_minutes", 60),
        "unbounded_override": node.get("unbounded_override"), "status": "recorded",
        "created_at": utc_now(), "started_at": None, "last_progress_at": None,
        "checkpoint_sha256": None, "session_id": state["sessions"][job["id"]].get("session_id"),
        "transport": {},
    }
    validate_dispatch(dispatch, policy)
    return dispatch


def _materialize_child_jobs(
    run_root: Path, controller: str, state: dict[str, Any],
    parent: dict[str, Any], proposals: list[Any],
) -> list[str]:
    if not isinstance(proposals, list):
        raise OrchestratorError("proposed_jobs must be an array")
    created: list[str] = []
    known = set(state["jobs"])
    for offset, proposal in enumerate(proposals, 1):
        if not isinstance(proposal, dict):
            raise OrchestratorError("each child_job request must be an object")
        child_id = proposal.get("id") or stable_id(
            "CHILD", parent["id"], proposal, offset
        )
        if child_id in known:
            raise OrchestratorError(f"duplicate child job ID: {child_id}")
        nodes = copy.deepcopy(proposal.get("workflow", {}).get("nodes", []))
        if not nodes or any(not node.get("work_units") for node in nodes):
            raise OrchestratorError("child_job requires a bounded workflow")
        dependencies = proposal.get("depends_on", list(parent.get("depends_on", [])))
        if parent["id"] in dependencies or child_id in dependencies:
            raise OrchestratorError("child_job dependency would create a cycle")
        if any(dependency not in known for dependency in dependencies):
            raise OrchestratorError("child_job has an unknown dependency")
        if any(_dependency_reaches(state, dependency, parent["id"])
               for dependency in dependencies):
            raise OrchestratorError("child_job dependency would create a parent wait cycle")
        request_id = stable_id(
            "CHREQ", parent["id"], proposal.get("parent_dispatch_id"), proposal, offset
        )
        tracked = state.get("child_requests", {}).get(request_id)
        if tracked and tracked.get("child_job_id") not in {None, child_id}:
            raise OrchestratorError("child request identity changed during replay")
        if tracked and tracked["status"] in {"materialized", "acknowledged"}:
            created.append(child_id)
            known.add(child_id)
            continue
        if not tracked:
            mutate(run_root, controller, make_event(
                run_root, "child_job_requested", request_id,
                {"request": {
                    "request_id": request_id,
                    "parent_job_id": parent["id"],
                    "parent_dispatch_id": proposal.get("parent_dispatch_id"),
                    "proposal": proposal,
                }},
            ))
            state = replay(run_root)
            tracked = state["child_requests"][request_id]
        if tracked["status"] == "proposed":
            mutate(run_root, controller, make_event(
                run_root, "child_job_validated", request_id,
                {"request_id": request_id, "child_job_id": child_id},
            ))
            state = replay(run_root)
        now = utc_now()
        ordered = sorted(nodes, key=lambda item: item["position"])
        for index, node in enumerate(ordered):
            node.setdefault("status", "ready" if index == 0 else "pending")
            node.setdefault("completed_work_units", [])
            node.setdefault("dispatch_ids", [])
        child = {
            "id": child_id, "title": proposal.get("title", f"Child work for {parent['id']}"),
            "goal": proposal.get("goal", "Complete requested child work"),
            "job_type": proposal.get("job_type", "child"),
            "role": proposal.get("role", parent["role"]),
            "priority": proposal.get("priority", parent.get("priority", 50) + 1),
            "sequence": max((item.get("sequence", 0) for item in state["jobs"].values()),
                            default=0) + offset,
            "depends_on": dependencies, "status": "queued",
            "current_workflow_node_id": ordered[0]["id"], "session": None,
            "report_path": f"jobs/{child_id}/report.md",
            "checkpoint_path": f"jobs/{child_id}/checkpoint.md",
            "parent_job_id": parent["id"], "parent_dispatch_id": proposal.get(
                "parent_dispatch_id"
            ),
            "created_at": now, "updated_at": now, "revision": 1,
        }
        workflow = {"session_policy": "persistent", "nodes": ordered}
        steps = {"steps": [
            {"id": node["id"], "workflow_node_id": node["id"],
             "status": node["status"], "attempts": [], "result_path": None}
            for node in ordered
        ]}
        parent_contract = load_json(run_root / "jobs" / parent["id"] / "contract.json")
        contract = {
            **parent_contract, "job_id": child_id, "revision": 1,
            "goal": child["goal"], "role": child["role"],
        }
        child["contract_sha256"] = content_hash(contract)
        child_root = run_root / "jobs" / child_id
        child_root.mkdir(parents=True, exist_ok=True)
        write_json(child_root / "contract.json", contract)
        (child_root / "report.md").touch()
        (child_root / "checkpoint.md").touch()
        if child_id not in state["jobs"]:
            mutate(run_root, controller, make_event(run_root, "job_compiled", child_id, {
                "job": child, "workflow": workflow, "steps": steps,
            }))
            state = replay(run_root)
        mutate(run_root, controller, make_event(
            run_root, "child_job_materialized", request_id,
            {"request_id": request_id, "child_job_id": child_id,
             "report_path": child["report_path"]},
        ))
        known.add(child_id)
        created.append(child_id)
        state = replay(run_root)
    return created


def next_action(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    state = replay(run_root)
    if state["run"].get("status") in TERMINAL_RUNS:
        terminal = next(
            (action for action in reversed(list(state["actions"].values()))
             if action["type"] == "run_complete"),
            None,
        )
        return terminal or {
            "type": "run_complete", "status": "resolved",
            "run_id": state["run"]["run_id"],
        }
    existing = _unresolved(state)
    if existing:
        if existing["type"] == "request_status":
            elapsed = (parse_time(utc_now()) - parse_time(
                existing["created_at"]
            )).total_seconds()
            if elapsed >= effective_policy(run_root)["liveness"].get(
                "status_timeout_seconds",
                effective_policy(run_root)["liveness"]["stale_after_seconds"],
            ):
                return {**existing, "expired": True,
                        "recovery_required": "unanswered_status"}
        return existing
    if _active_idle_contradictions(run_root, state):
        raise OrchestratorError(
            "state integrity audit blocks normal dispatch: active-idle contradiction"
        )
    blocked = next((item for item in state["jobs"].values()
                    if item["status"] == "blocked"), None)
    if blocked:
        requests = _pending_child_requests(state, blocked["id"])
        children = _job_children(state, blocked["id"])
        pending_children = [
            child for child in children if child["status"] not in TERMINAL_JOBS
        ]
        if pending_children:
            blocked = None
        elif children and requests:
            reports = [
                {"job_id": child["id"], "status": child["status"],
                 "report_path": child["report_path"]}
                for child in children
            ]
            prompt = render("resolution", resolution=json.dumps(
                {"child_reports": reports, "acknowledgement_required": True},
                separators=(",", ":"),
            ))
            action = _make_action(run_root, state, "route_resolution", blocked, prompt,
                                  {"child_request_ids": [
                                      request["request_id"] for request in requests
                                  ]})
            mutate(run_root, args.controller, make_event(
                run_root, "action_created", action["action_id"], {"action": action}
            ))
            return action
    if blocked:
        dispatch = next(
            (item for item in reversed(list(state["dispatches"].values()))
             if item["job_id"] == blocked["id"] and item.get("result")),
            None,
        )
        result = dispatch.get("result", {}) if dispatch else {}
        if result.get("proposed_jobs"):
            prompt = render("resolution", resolution=json.dumps(
                result["proposed_jobs"], separators=(",", ":")
            ))
            action = _make_action(run_root, state, "route_resolution", blocked, prompt)
        else:
            question = (result.get("questions") or result.get("blocking_issues")
                        or ["Provide the missing authority or information."])[0]
            prompt = render("user-question", question=question)
            action = _make_action(run_root, state, "ask_user", blocked, prompt)
        mutate(run_root, args.controller, make_event(
            run_root, "action_created", action["action_id"], {"action": action}
        ))
        return action
    job = _ready_job(state)
    if not job:
        kind = "run_complete" if state["jobs"] and all(
            item["status"] in TERMINAL_JOBS for item in state["jobs"].values()
        ) else "wait"
        action = _make_action(run_root, state, kind, None, None)
    elif job["id"] not in state["sessions"]:
        contract = run_root / "jobs" / job["id"] / "contract.json"
        checkpoint = run_root / "jobs" / job["id"] / "checkpoint.md"
        node = next(item for item in state["workflows"][job["id"]]["nodes"]
                    if item["id"] == job["current_workflow_node_id"])
        prompt = render("bootstrap", protocol=run_root / "protocol" / "job-protocol.md",
                        contract=contract, workerctl=Path(__file__).with_name("workerctl.py"),
                        node=job["current_workflow_node_id"], checkpoint=checkpoint,
                        completed=", ".join(node.get("completed_work_units", [])) or "none",
                        next_permitted="acknowledge; do not resume domain work yet",
                        protocol_version=PROTOCOL_VERSION,
                        protocol_sha256=load_json(
                            run_root / "protocol" / "manifest.json"
                        )["sha256"],
                        job_id=job["id"],
                        contract_revision=load_json(contract)["revision"])
        action = _make_action(run_root, state, "spawn_and_bootstrap", job, prompt)
    elif state["run"].get("active_dispatch_id"):
        dispatch = state["dispatches"][state["run"]["active_dispatch_id"]]
        if dispatch.get("status") == "interrupted":
            replacement_session_id = state["sessions"][job["id"]]["session_id"]
            mutate(run_root, args.controller, make_event(
                run_root,
                "dispatch_updated",
                f"{dispatch['dispatch_id']}:replacement-session",
                {
                    "dispatch_id": dispatch["dispatch_id"],
                    "changes": {
                        "status": "recorded",
                        "session_id": replacement_session_id,
                    },
                },
            ))
            state = replay(run_root)
            dispatch = state["dispatches"][dispatch["dispatch_id"]]
            prompt = render("execution", dispatch=(
                run_root / "jobs" / job["id"] / "dispatches"
                / f"{dispatch['dispatch_id']}.json"
            ), workerctl=Path(__file__).with_name("workerctl.py"),
                nonce=dispatch["nonce"],
                session_id=replacement_session_id,
                node=dispatch["workflow_node_id"])
            action = _make_action(
                run_root, state, "send_dispatch", job, prompt,
                {"dispatch_id": dispatch["dispatch_id"]},
            )
            mutate(run_root, args.controller, make_event(
                run_root, "action_created", action["action_id"], {"action": action}
            ))
            return action
        last = dispatch.get("last_progress_at") or dispatch.get("started_at") or dispatch["created_at"]
        stale = (parse_time(utc_now()) - parse_time(last)).total_seconds()
        if stale >= effective_policy(run_root)["liveness"]["stale_after_seconds"]:
            prompt = render("status", dispatch=dispatch["dispatch_id"],
                            progress=run_root / "jobs" / job["id"] / "progress.json")
            action = _make_action(run_root, state, "request_status", job, prompt,
                                  {"dispatch_id": dispatch["dispatch_id"]})
        else:
            action = _make_action(run_root, state, "wait", job, None,
                                  {"dispatch_id": dispatch["dispatch_id"]})
    else:
        provisional = _make_action(run_root, state, "send_dispatch", job, "")
        dispatch = _next_dispatch(run_root, state, job, provisional["action_id"])
        dispatch_path = (run_root / "jobs" / job["id"] / "dispatches"
                         / f"{dispatch['dispatch_id']}.json")
        prompt = render("execution", dispatch=dispatch_path,
                        workerctl=Path(__file__).with_name("workerctl.py"),
                        nonce=dispatch["nonce"],
                        session_id=state["sessions"][job["id"]]["session_id"],
                        node=dispatch["workflow_node_id"])
        provisional.update(prompt=prompt, dispatch_id=dispatch["dispatch_id"])
        action = provisional
        event = make_event(run_root, "dispatch_created", dispatch["dispatch_id"],
                           {"dispatch": dispatch})
        mutate(run_root, args.controller, event)
        state = replay(run_root)
    event = make_event(run_root, "action_created", action["action_id"], {"action": action})
    mutate(run_root, args.controller, event)
    return action


def record(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    response = load_json(args.response)
    state = replay(run_root)
    action = state["actions"].get(args.action_id)
    if not action:
        raise OrchestratorError("unknown action")
    response_hash = content_hash(response)
    if action["status"] == "resolved":
        if action.get("response_hash") != response_hash:
            raise OrchestratorError("action already resolved with a different response")
        return {"duplicate": True, "action_id": args.action_id}
    # Validate the complete external response before journaling its identity.
    # Failed attempts remain retryable with corrected evidence.
    if action["type"] == "spawn_and_bootstrap":
        _validate_acknowledgement(run_root, state, action, response)
    elif action["type"] in {
        "send_dispatch", "wait", "request_status", "reconcile_result",
    } and response.get("result"):
        dispatch, result = _validate_worker_result(run_root, state, action, response)
        proposals = result.get("proposed_jobs", [])
        if proposals and result["status"] != "blocked":
            raise OrchestratorError(
                "child_job requests require a blocked parent result"
            )
        if not isinstance(proposals, list):
            raise OrchestratorError("proposed_jobs must be an array")
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise OrchestratorError("each child_job request must be an object")
            nodes = proposal.get("workflow", {}).get("nodes", [])
            if not nodes or any(not node.get("work_units") for node in nodes):
                raise OrchestratorError("child_job requires a bounded workflow")
            dependencies = proposal.get(
                "depends_on",
                list(state["jobs"][dispatch["job_id"]].get("depends_on", [])),
            )
            if any(dependency not in state["jobs"] for dependency in dependencies):
                raise OrchestratorError("child_job has an unknown dependency")
            if any(_dependency_reaches(
                state, dependency, dispatch["job_id"]
            ) for dependency in dependencies):
                raise OrchestratorError(
                    "child_job dependency would create a parent wait cycle"
                )
    elif action["type"] in {"send_dispatch", "wait", "request_status"}:
        progress = response.get("progress")
        if progress is not None:
            validate_record("progress", progress)
            dispatch = state["dispatches"][action["dispatch_id"]]
            if (progress["dispatch_id"], progress["nonce"]) != (
                dispatch["dispatch_id"], dispatch["nonce"]
            ):
                raise OrchestratorError("status progress is not bound to dispatch")
            progress_path = (
                run_root / "jobs" / dispatch["job_id"] / "progress.json"
            )
            if not progress_path.is_file() or load_json(progress_path) != progress:
                raise OrchestratorError(
                    "status progress does not match persisted progress"
                )
    elif (
        action["type"] in {"route_resolution", "ask_user"}
        and _job_children(state, action["job_id"])
        and not response.get("acknowledged")
    ):
        raise OrchestratorError("child reports require explicit acknowledgement")
    recorded_hash = state.get("record_responses", {}).get(args.action_id)
    if recorded_hash and recorded_hash != response_hash:
        raise OrchestratorError("action record resumed with a different response")
    if not recorded_hash:
        mutate(run_root, args.controller, make_event(
            run_root, "action_response_received", f"record:{args.action_id}",
            {"action_id": args.action_id, "response_hash": response_hash},
        ))
        state = replay(run_root)
        action = state["actions"][args.action_id]
    applied_types = {
        "spawn_and_bootstrap": {"session_acknowledged"},
        "send_dispatch": {"worker_result", "dispatch_updated"},
        "wait": {"worker_result", "dispatch_updated"},
        "request_status": {"worker_result", "dispatch_updated"},
        "reconcile_result": {"worker_result"},
        "route_resolution": {"resolution_recorded"},
        "ask_user": {"user_answered"},
        "run_complete": {"run_status"},
    }
    already_applied = any(
        event["correlation_id"] == args.action_id
        and event["type"] in applied_types.get(action["type"], set())
        for event in read_jsonl(run_root / "events.jsonl")
    )
    if already_applied:
        if action["type"] == "route_resolution":
            current = replay(run_root)
            for request_id in action.get("child_request_ids", []):
                request = current["child_requests"].get(request_id)
                if request and request["status"] == "materialized":
                    mutate(run_root, args.controller, make_event(
                        run_root, "child_job_acknowledged",
                        f"{args.action_id}:{request_id}",
                        {"request_id": request_id, "job_id": action["job_id"]},
                    ))
    elif action["type"] == "spawn_and_bootstrap":
        ack = _validate_acknowledgement(run_root, state, action, response)
        mutate(run_root, args.controller, make_event(
            run_root, "session_acknowledged", args.action_id, ack
        ))
    elif action["type"] in {
        "send_dispatch", "wait", "request_status", "reconcile_result",
    } and response.get("result"):
        dispatch, result = _validate_worker_result(
            run_root, state, action, response
        )
        proposals = result.get("proposed_jobs", [])
        child_ids: list[str] = []
        if proposals:
            if result["status"] != "blocked":
                raise OrchestratorError(
                    "child_job requests require a blocked parent result"
                )
            child_ids = _materialize_child_jobs(
                run_root, args.controller, state,
                state["jobs"][dispatch["job_id"]], proposals,
            )
        mutate(run_root, args.controller, make_event(run_root, "worker_result",
            args.action_id, {"dispatch_id": dispatch["dispatch_id"],
                             "result": result, "child_job_ids": child_ids}))
    elif action["type"] in {"send_dispatch", "wait", "request_status"}:
        changes: dict[str, Any] = {}
        progress = response.get("progress")
        if progress is not None:
            validate_record("progress", progress)
            dispatch = state["dispatches"][action["dispatch_id"]]
            if (progress["dispatch_id"], progress["nonce"]) != (
                dispatch["dispatch_id"], dispatch["nonce"]
            ):
                raise OrchestratorError("status progress is not bound to dispatch")
            progress_path = run_root / "jobs" / dispatch["job_id"] / "progress.json"
            if not progress_path.is_file() or load_json(progress_path) != progress:
                raise OrchestratorError("status progress does not match persisted progress")
            changes.update(
                last_progress_at=progress["updated_at"],
                checkpoint_sha256=progress["checkpoint_sha256"],
            )
        transport = response.get("transport_ack", response.get("transport", {}))
        if transport:
            changes["transport"] = transport
            if transport.get("sent") and not state["dispatches"][
                action["dispatch_id"]
            ].get("started_at"):
                changes["started_at"] = transport.get("sent_at", utc_now())
        if "status" in response:
            changes["status"] = response["status"]
        elif action["type"] == "send_dispatch":
            changes["status"] = "sent"
        # A wait timestamp is controller activity, never worker progress.
        if not changes:
            changes["transport"] = {"controller_waited_at": utc_now()}
        mutate(run_root, args.controller, make_event(run_root, "dispatch_updated",
            args.action_id, {"dispatch_id": action["dispatch_id"], "changes": changes}))
    elif action["type"] in {"route_resolution", "ask_user"}:
        if _job_children(state, action["job_id"]) and not response.get("acknowledged"):
            raise OrchestratorError("child reports require explicit acknowledgement")
        event_type = "resolution_recorded" if action["type"] == "route_resolution" else "user_answered"
        mutate(run_root, args.controller, make_event(
            run_root, event_type, args.action_id,
            {"job_id": action["job_id"], "response": response},
        ))
        for request_id in action.get("child_request_ids", []):
            mutate(run_root, args.controller, make_event(
                run_root, "child_job_acknowledged",
                f"{args.action_id}:{request_id}",
                {"request_id": request_id, "job_id": action["job_id"]},
            ))
    elif action["type"] == "run_complete":
        if state["run"].get("status") not in TERMINAL_RUNS:
            mutate(run_root, args.controller, make_event(
                run_root, "run_status", args.action_id, {"status": "completed"}
            ))
    mutate(run_root, args.controller, make_event(run_root, "action_resolved",
        args.action_id, {"action_id": args.action_id, "response_hash": response_hash}))
    return {"recorded": True, "action_id": args.action_id}


def classify(dispatch: dict[str, Any], evidence: dict[str, Any]) -> str:
    if not dispatch.get("transport", {}).get("sent"):
        return "recorded_unsent"
    if evidence.get("result"):
        return "completed_unrecorded"
    if evidence.get("external_effect"):
        return "externally_effective_unacknowledged"
    if evidence.get("session_available") and evidence.get("checkpoint_valid"):
        return "running_resumable"
    if not evidence.get("started") and dispatch["side_effect_class"] == "read_only":
        return "safe_retry"
    if not evidence.get("started"):
        return "sent_unstarted"
    return "unsafe_retry"


def _finding_for_classification(classification: str) -> str:
    return RECOVERY_CLASSIFICATION_TO_FINDING.get(
        classification, "journal_corrupt_or_insufficient"
    )


def _safe_next_action_for_finding(
    finding: str, classification: str | None = None,
) -> str:
    if finding == "clean":
        return "continue normal jobctl next loop"
    if finding in {"derived_snapshot_drift", "stale_index_or_queue"}:
        return "run jobctl audit --rebuild, then audit again"
    if finding == "interrupted_dispatch_recorded_not_sent":
        return "replace or rebootstrap the session before reusing the recorded dispatch"
    if finding == "interrupted_dispatch_sent_no_result":
        if classification == "running_resumable":
            return "request status from the existing session"
        return "classify transport and worker evidence before retry or replacement"
    if finding == "completed_result_not_applied":
        return "validate and reconcile the worker result through jobctl recover"
    if finding == "external_effect_unknown":
        return "run the configured recovery check before retry, acceptance, or replacement"
    return "create a recovery investigation job or ask the user for authority"


def _finding(
    classification: str, issue: str, *, safe: bool | None = None,
    classification_detail: str | None = None,
) -> dict[str, Any]:
    automatic = classification in AUTOMATIC_RECOVERY_FINDINGS if safe is None else safe
    return {
        "classification": classification,
        "issue": issue,
        "safe_for_automatic_recovery": automatic,
        "proposed_safe_next_action": _safe_next_action_for_finding(
            classification, classification_detail
        ),
    }


def _result_response_from_evidence(
    evidence: dict[str, Any], run_root: Path,
) -> dict[str, Any] | None:
    response = evidence.get("response")
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        return response
    result_path = evidence.get("result_path")
    if isinstance(result_path, str) and result_path.strip():
        path = Path(result_path)
        path = path if path.is_absolute() else run_root / path
        return {"result": load_json(path), "result_path": str(path)}
    result = evidence.get("result")
    if isinstance(result, dict) and result.get("schema_version"):
        return {"result": result}
    return None


def _validate_unapplied_result(
    run_root: Path, state: dict[str, Any], dispatch: dict[str, Any],
    response: dict[str, Any],
) -> bool:
    action = state["actions"].get(dispatch["action_id"])
    if not action or action.get("status") != "unresolved":
        return False
    try:
        _validate_worker_result(run_root, state, action, response)
    except OrchestratorError:
        return False
    return True


def _validated_unapplied_results(
    run_root: Path, state: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence = []
    for path in sorted((run_root / "jobs").glob("*/results/*.json")):
        try:
            result = load_json(path)
        except OrchestratorError:
            continue
        dispatch = state["dispatches"].get(result.get("dispatch_id"))
        if not dispatch or dispatch.get("result"):
            continue
        response = {"result": result, "result_path": str(path)}
        if _validate_unapplied_result(run_root, state, dispatch, response):
            evidence.append({
                "dispatch_id": dispatch["dispatch_id"],
                "action_id": dispatch["action_id"],
                "result_path": str(path.relative_to(run_root)),
            })
    return evidence


def _progress_without_result_evidence(
    run_root: Path, state: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence = []
    for path in sorted((run_root / "jobs").glob("*/progress.json")):
        try:
            progress = load_json(path)
        except OrchestratorError:
            continue
        dispatch = state["dispatches"].get(progress.get("dispatch_id"))
        if not dispatch or dispatch.get("result"):
            continue
        result_path = (
            run_root / "jobs" / dispatch["job_id"] / "results"
            / f"{dispatch['dispatch_id']}.json"
        )
        if not result_path.is_file():
            evidence.append({
                "dispatch_id": dispatch["dispatch_id"],
                "progress_path": str(path.relative_to(run_root)),
            })
    return evidence


def _active_idle_contradictions(
    run_root: Path, state: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        run_snapshot = load_json(run_root / "run.json")
    except OrchestratorError:
        return []
    try:
        queue_snapshot = load_json(run_root / "queue.json")
    except OrchestratorError:
        queue_snapshot = {"entries": []}
    unresolved = [
        action["action_id"] for action in state["actions"].values()
        if action.get("status") == "unresolved"
    ]
    worker_evidence = _validated_unapplied_results(
        run_root, state
    ) + _progress_without_result_evidence(run_root, state)
    if (
        run_snapshot.get("status") == "active"
        and run_snapshot.get("active_job_id") is None
        and run_snapshot.get("active_dispatch_id") is None
        and state["run"].get("active_job_id") is None
        and state["run"].get("active_dispatch_id") is None
        and not queue_snapshot.get("entries")
        and (unresolved or worker_evidence)
    ):
        return [{
            "unresolved_actions": unresolved,
            "worker_evidence": worker_evidence,
        }]
    return []


def _apply_recovered_result(
    run_root: Path, controller: str, state: dict[str, Any],
    dispatch: dict[str, Any], response: dict[str, Any],
) -> dict[str, Any]:
    action = state["actions"].get(dispatch["action_id"])
    if not action or action.get("status") != "unresolved":
        raise OrchestratorError("completed recovery requires an unresolved action")
    validated_dispatch, result = _validate_worker_result(
        run_root, state, action, response
    )
    if validated_dispatch["dispatch_id"] != dispatch["dispatch_id"]:
        raise OrchestratorError("recovered result dispatch mismatch")
    response_hash = content_hash(response)
    if not state.get("record_responses", {}).get(action["action_id"]):
        mutate(run_root, controller, make_event(
            run_root, "action_response_received",
            f"recover:{action['action_id']}",
            {"action_id": action["action_id"], "response_hash": response_hash},
        ))
        state = replay(run_root)
    mutate(run_root, controller, make_event(
        run_root, "worker_result", action["action_id"],
        {"dispatch_id": dispatch["dispatch_id"], "result": result, "child_job_ids": []},
    ))
    mutate(run_root, controller, make_event(
        run_root, "action_resolved", action["action_id"],
        {"action_id": action["action_id"], "response_hash": response_hash},
    ))
    write_snapshots(run_root, replay(run_root))
    return {"action_id": action["action_id"], "dispatch_id": dispatch["dispatch_id"]}


def _create_recovery_action(
    run_root: Path, controller: str, state: dict[str, Any],
    dispatch: dict[str, Any],
) -> dict[str, Any]:
    job = state["jobs"][dispatch["job_id"]]
    existing = _unresolved(state)
    if existing:
        mutate(run_root, controller, make_event(
            run_root, "action_resolved", existing["action_id"],
            {"action_id": existing["action_id"],
             "response_hash": content_hash({
                 "recovery": "completed_unrecorded",
                 "dispatch_id": dispatch["dispatch_id"],
             })},
        ))
        state = replay(run_root)
    result_path = run_root / "jobs" / job["id"] / "results" / (
        dispatch["dispatch_id"] + ".json"
    )
    action = _make_action(
        run_root, state, "reconcile_result", job,
        f"Record and validate the recovered result at {result_path}.",
        {"dispatch_id": dispatch["dispatch_id"]},
    )
    mutate(run_root, controller, make_event(
        run_root, "action_created", action["action_id"], {"action": action}
    ))
    return action


def recover(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    manifest = load_json(run_root / "protocol" / "manifest.json")
    run_document = load_json(run_root / "run.json")
    if (
        manifest.get("protocol_version") == 2
        and (
            run_document.get("schema_version") != 3
            or not read_jsonl(run_root / "events.jsonl")
        )
    ):
        return {
            "classification": "legacy_v2_unchanged",
            "protocol_version": 2,
            "apply": False,
            "required_action": "continue with the frozen v2 protocol or migrate explicitly",
        }
    state = replay(run_root)
    active = next((item for item in state["dispatches"].values()
                   if item["status"] in ACTIVE_DISPATCHES), None)
    if not active:
        return {"classification": "no_interrupted_dispatch", "apply": not args.dry_run}
    evidence = load_json(args.evidence) if args.evidence else {}
    unresolved = _unresolved(state)
    unanswered = (
        unresolved and unresolved["type"] == "request_status"
        and (parse_time(utc_now()) - parse_time(unresolved["created_at"])).total_seconds()
        >= effective_policy(run_root)["liveness"].get(
            "status_timeout_seconds",
            effective_policy(run_root)["liveness"]["stale_after_seconds"],
        )
    )
    # An expired status request is itself evidence only when no newer recovery
    # observations were supplied. Once evidence arrives, classify it and
    # resolve the stale request before applying the recovery transition.
    supplied_result_response = _result_response_from_evidence(evidence, run_root)
    classification = (
        "unanswered_status" if unanswered and not evidence
        else "completed_unrecorded" if supplied_result_response else classify(active, evidence)
    )
    finding = _finding_for_classification(classification)
    sent = bool(active.get("transport", {}).get("sent"))
    if sent and classification not in {
        "completed_unrecorded", "unanswered_status"
    }:
        if active["side_effect_class"] == "read_only":
            if classification in {"safe_retry", "sent_unstarted"} and not (
                isinstance(evidence.get("unstarted_proof"), str)
                and evidence["unstarted_proof"].strip()
            ):
                raise OrchestratorError(
                    "read-only unstarted recovery requires explicit unstarted_proof"
                )
        elif (
            evidence.get("recovery_check") != active["recovery_check"]
            or not isinstance(evidence.get("recovery_check_passed"), bool)
        ):
            raise OrchestratorError(
                "sent side-effecting recovery requires matching recovery_check "
                "and boolean recovery_check_passed"
            )
        elif (
            classification in {"safe_retry", "sent_unstarted", "running_resumable"}
            and evidence["recovery_check_passed"] is not True
        ):
            raise OrchestratorError(
                "sent side-effecting recovery check must pass before continuation"
            )
    result = {
        "dispatch_id": active["dispatch_id"],
        "classification": classification,
        "finding": finding,
        "apply": not args.dry_run,
        "safe_next_action": _safe_next_action_for_finding(finding, classification),
        "automatic_recovery_safe": finding in AUTOMATIC_RECOVERY_FINDINGS,
    }
    if classification == "completed_unrecorded":
        response = supplied_result_response
        if response and _validate_unapplied_result(
            run_root, state, active, response
        ):
            result["safe_next_action"] = "apply validated worker result"
        elif response:
            result["automatic_recovery_safe"] = False
            result["safe_next_action"] = (
                "create recovery investigation job; supplied result did not validate"
            )
    if args.dry_run:
        return result
    if result["classification"] == "completed_unrecorded":
        response = supplied_result_response
        if response:
            applied = _apply_recovered_result(
                run_root, args.controller, state, active, response
            )
            result["reconciled"] = applied
            result["required_action"] = "continue normal jobctl next loop"
        else:
            recovery = _create_recovery_action(
                run_root, args.controller, state, active
            )
            result["required_action"] = recovery
    elif result["classification"] in {"unsafe_retry", "externally_effective_unacknowledged"}:
        result["required_action"] = "reconcile external effects; retry is prohibited"
    elif result["classification"] == "unanswered_status":
        result["required_action"] = (
            "classify persisted and external evidence before session replacement"
        )
    elif not evidence.get("session_available"):
        if unresolved:
            mutate(run_root, args.controller, make_event(
                run_root, "action_resolved",
                f"{active['dispatch_id']}:recovery-invalidated",
                {"action_id": unresolved["action_id"],
                 "response_hash": content_hash({
                     "recovery": result["classification"],
                     "dispatch_id": active["dispatch_id"],
                 })},
            ))
        mutate(run_root, args.controller, make_event(run_root, "dispatch_updated",
            active["dispatch_id"] + ":interrupted",
            {"dispatch_id": active["dispatch_id"],
             "changes": {"status": "interrupted",
                         "interrupted_at": utc_now(),
                         "interruption_class": result["classification"]}}))
        mutate(run_root, args.controller, make_event(run_root, "session_lost",
            active["dispatch_id"], {"job_id": active["job_id"],
                                    "checkpoint_sha256": active.get("checkpoint_sha256")}))
        result["required_action"] = "bootstrap replacement session"
    return result


def _expected_snapshots(
    run_root: Path, state: dict[str, Any],
) -> dict[Path, Any]:
    expected: dict[Path, Any] = {
        run_root / "run.json": state["run"],
        run_root / "queue.json": {
            "mode": "sequential",
            "entries": [{
                "job_id": job_id, "priority": job.get("priority", 50),
                "sequence": job.get("sequence", 0),
                "depends_on": job.get("depends_on", []),
            } for job_id, job in sorted(state["jobs"].items())],
        },
        run_root / "jobs" / "index.json": {"jobs": sorted(state["jobs"])},
    }
    for job_id, job in state["jobs"].items():
        root = run_root / "jobs" / job_id
        expected[root / "job.json"] = job
        expected[root / "workflow.json"] = state["workflows"][job_id]
        expected[root / "steps.json"] = state["steps"][job_id]
    for action in state["actions"].values():
        expected[run_root / "actions" / f"{action['action_id']}.json"] = action
    for dispatch in state["dispatches"].values():
        expected[
            run_root / "jobs" / dispatch["job_id"] / "dispatches"
            / f"{dispatch['dispatch_id']}.json"
        ] = dispatch
    return expected


def _reconstruct_run_seed(run_root: Path) -> dict[str, Any]:
    seed_path = run_root / "protocol" / "run-seed.json"
    if seed_path.is_file():
        return load_json(seed_path)
    events = read_jsonl(run_root / "events.jsonl")
    if not events:
        raise OrchestratorError("cannot rebuild run snapshot without journal events")
    setup = load_json(run_root / "setup.json")
    manifest = load_json(run_root / "protocol" / "manifest.json")
    contract_paths = list((run_root / "jobs").glob("*/contract.json"))
    workspace = (
        load_json(contract_paths[0])["workspace"] if contract_paths else str(run_root)
    )
    first = events[0]
    return {
        "schema_version": 3, "run_id": first["run_id"],
        "status": "initializing", "goal": setup.get("goal", ""),
        "created_at": first["created_at"], "updated_at": first["created_at"],
        "workspace": workspace, "state_root": str(run_root.parent.resolve()),
        "protocol": {
            "manifest_path": "protocol/manifest.json",
            "version": manifest["protocol_version"], "sha256": manifest["sha256"],
        },
        "skill_source": {"path": str(SKILL_ROOT), "update_scope": "future_runs"},
        "revision": 0, "mode": "sequential",
        "active_job_id": None, "active_dispatch_id": None,
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    issues: list[str] = []
    findings: list[dict[str, Any]] = []
    run_path = run_root / "run.json"
    required_run = {
        "schema_version", "run_id", "status", "goal", "created_at", "updated_at",
        "workspace", "state_root", "protocol", "revision", "mode",
    }
    run_corrupt = False
    try:
        run_corrupt = not required_run.issubset(load_json(run_path))
    except (OSError, ValueError, json.JSONDecodeError, OrchestratorError):
        run_corrupt = True
    if run_corrupt:
        issues.append("run.json snapshot missing or structurally corrupt")
        if not args.rebuild:
            findings.append(_finding(
                "journal_corrupt_or_insufficient",
                "run.json snapshot missing or structurally corrupt",
                safe=False,
            ))
            return {
                "ok": False,
                "issues": issues,
                "findings": findings,
                "replay_health": {
                    "replayable": False,
                    "events": len(read_jsonl(run_root / "events.jsonl")),
                },
                "events": len(read_jsonl(run_root / "events.jsonl")),
            }
        write_json(run_path, _reconstruct_run_seed(run_root))
    try:
        state = replay(run_root)
    except (OrchestratorError, KeyError, TypeError, ValueError) as exc:
        findings.append(_finding(
            "journal_corrupt_or_insufficient", str(exc), safe=False,
        ))
        return {
            "ok": False,
            "issues": [str(exc)],
            "findings": findings,
            "replay_health": {"replayable": False, "error": str(exc)},
        }
    migration = next(
        (event["data"] for event in reversed(read_jsonl(run_root / "events.jsonl"))
         if event["type"] == "protocol_migrated"),
        None,
    )
    if migration and args.rebuild:
        static_mismatch = (
            not (run_root / "protocol" / "job-protocol.md").is_file()
            or content_hash(
                (run_root / "protocol" / "job-protocol.md").read_bytes()
            ) != migration["protocol_sha256"]
            or any(
                not (run_root / "jobs" / job_id / "contract.json").is_file()
                or content_hash(load_json(
                    run_root / "jobs" / job_id / "contract.json"
                )) != migration["contract_hashes"][job_id]
                for job_id in migration.get("contract_hashes", {})
            )
        )
        if static_mismatch:
            _install_migration_static(run_root, migration)
    manifest = load_json(run_root / "protocol" / "manifest.json")
    protocol_path = run_root / "protocol" / manifest["file"]
    actual_protocol_hash = (
        content_hash(protocol_path.read_bytes()) if protocol_path.is_file() else None
    )
    protocol_hash_status = {
        "expected": manifest["sha256"],
        "actual": actual_protocol_hash,
        "matches": actual_protocol_hash == manifest["sha256"],
        "safe_for_automatic_recovery": actual_protocol_hash == manifest["sha256"],
    }
    if not protocol_hash_status["matches"]:
        issues.append("frozen protocol hash mismatch")
        findings.append(_finding(
            "journal_corrupt_or_insufficient",
            "frozen protocol hash mismatch",
            safe=False,
        ))
    expected = _expected_snapshots(run_root, state)
    snapshot_issues: list[str] = []
    for path, projected in expected.items():
        relative = path.relative_to(run_root)
        if not path.is_file():
            snapshot_issues.append(f"{relative} snapshot missing")
        else:
            try:
                actual = load_json(path)
            except OrchestratorError:
                snapshot_issues.append(f"{relative} snapshot is malformed")
                continue
            if content_hash(projected) != content_hash(actual):
                snapshot_issues.append(f"{relative} snapshot disagrees with journal")
    issues.extend(snapshot_issues)
    derived_snapshot_drift: list[str] = []
    stale_index_or_queue: list[str] = []
    for issue in snapshot_issues:
        if issue.startswith("queue.json ") or issue.startswith("jobs\\index.json ") or issue.startswith("jobs/index.json "):
            stale_index_or_queue.append(issue)
        else:
            derived_snapshot_drift.append(issue)
    for issue in stale_index_or_queue:
        findings.append(_finding("stale_index_or_queue", issue))
    for issue in derived_snapshot_drift:
        findings.append(_finding("derived_snapshot_drift", issue))
    unapplied_results = _validated_unapplied_results(run_root, state)
    for item in unapplied_results:
        findings.append(_finding(
            "completed_result_not_applied",
            f"{item['dispatch_id']} has a validated result that is not applied",
        ))
    progress_evidence = _progress_without_result_evidence(run_root, state)
    for item in progress_evidence:
        findings.append(_finding(
            "interrupted_dispatch_sent_no_result",
            f"{item['dispatch_id']} has progress evidence without a validated result",
            safe=False,
            classification_detail="sent_unstarted",
        ))
    unresolved_action_dispatch_contradictions = []
    side_effect_blockers = []
    for dispatch in state["dispatches"].values():
        if dispatch.get("status") in ACTIVE_DISPATCHES:
            classification = classify(dispatch, {})
            finding = _finding_for_classification(classification)
            action = state["actions"].get(dispatch["action_id"])
            contradiction = {
                "dispatch_id": dispatch["dispatch_id"],
                "action_id": dispatch["action_id"],
                "dispatch_status": dispatch.get("status"),
                "action_status": action.get("status") if action else None,
                "classification": finding,
            }
            unresolved_action_dispatch_contradictions.append(contradiction)
            findings.append(_finding(
                finding,
                f"{dispatch['dispatch_id']} is active without resolved worker result",
                safe=finding in AUTOMATIC_RECOVERY_FINDINGS,
                classification_detail=classification,
            ))
            if (
                dispatch.get("transport", {}).get("sent")
                and dispatch.get("side_effect_class") != "read_only"
            ):
                blocker = {
                    "dispatch_id": dispatch["dispatch_id"],
                    "side_effect_class": dispatch.get("side_effect_class"),
                    "recovery_check": dispatch.get("recovery_check"),
                }
                side_effect_blockers.append(blocker)
                findings.append(_finding(
                    "external_effect_unknown",
                    f"{dispatch['dispatch_id']} requires side-effect recovery check",
                    safe=False,
                ))
    active_idle_contradictions = _active_idle_contradictions(run_root, state)
    for _item in active_idle_contradictions:
        findings.append(_finding(
            "journal_corrupt_or_insufficient",
            "active run has no active job, no active dispatch, empty queue, and unresolved evidence",
            safe=False,
        ))
    for job in state["jobs"].values():
        for name in ("contract.json", "workflow.json", "steps.json"):
            if not (run_root / "jobs" / job["id"] / name).exists():
                issues.append(f"{job['id']} missing {name}")
        if job["status"] in {"completed", "completed_with_concerns"} and not (
            run_root / job["report_path"]
        ).exists():
            issues.append(f"{job['id']} missing report")
        contract_path = run_root / "jobs" / job["id"] / "contract.json"
        if contract_path.is_file():
            contract = load_json(contract_path)
            authoritative_hash = job.get("contract_sha256")
            if (
                authoritative_hash
                and content_hash(contract) != authoritative_hash
            ):
                issues.append(f"{job['id']} static contract hash mismatch")
            protocol = (contract_path.parent / contract["protocol"]["path"]).resolve()
            if (
                not protocol.is_file()
                or content_hash(protocol.read_bytes()) != contract["protocol"]["sha256"]
                or contract["protocol"]["sha256"] != manifest["sha256"]
                or contract["protocol"]["version"] != manifest["protocol_version"]
            ):
                issues.append(f"{job['id']} contract protocol hash mismatch")
    if args.rebuild and snapshot_issues:
        write_snapshots(run_root, state)
        issues = [item for item in issues if item not in snapshot_issues]
        findings = [
            item for item in findings
            if item["classification"] not in {
                "derived_snapshot_drift", "stale_index_or_queue"
            }
        ]
        derived_snapshot_drift = []
        stale_index_or_queue = []
    if args.rebuild and run_corrupt:
        write_snapshots(run_root, state)
        issues = [item for item in issues
                  if item != "run.json snapshot missing or structurally corrupt"]
    if not findings:
        findings.append(_finding("clean", "state integrity audit passed"))
    blocks_normal_resume = any(
        not item["safe_for_automatic_recovery"]
        or item["classification"] not in {"clean"}
        for item in findings
    )
    return {
        "ok": not issues and not active_idle_contradictions,
        "issues": issues,
        "findings": findings,
        "replay_health": {
            "replayable": True,
            "events": len(read_jsonl(run_root / "events.jsonl")),
        },
        "protocol_hash_status": protocol_hash_status,
        "derived_snapshot_drift": derived_snapshot_drift,
        "stale_index_or_queue": stale_index_or_queue,
        "unresolved_action_dispatch_contradictions": unresolved_action_dispatch_contradictions,
        "active_idle_contradictions": active_idle_contradictions,
        "side_effect_blockers": side_effect_blockers,
        "blocks_normal_resume": blocks_normal_resume,
        "events": len(read_jsonl(run_root / "events.jsonl")),
    }


def _upgrade_contract(
    contract: dict[str, Any], run: dict[str, Any], digest: str,
) -> dict[str, Any]:
    upgraded = dict(contract)
    upgraded.update(
        contract_version=3,
        revision=int(contract.get("revision", 0)) + 1,
        workspace=contract.get("workspace", run["workspace"]),
        allowed_edit_roots=contract.get("allowed_edit_roots", []),
        capabilities=contract.get("capabilities", []),
        artifact_paths=contract.get(
            "artifact_paths",
            ["report.md", "checkpoint.md", "progress.json", "results"],
        ),
    )
    upgraded["protocol"] = {
        **contract.get("protocol", {}),
        "path": contract.get("protocol", {}).get(
            "path", "../../protocol/job-protocol.md"
        ),
        "version": 3,
        "sha256": digest,
    }
    upgraded.setdefault("report_path", "report.md")
    upgraded.setdefault("checkpoint_path", "checkpoint.md")
    upgraded.setdefault("may_propose_jobs", True)
    upgraded.setdefault("may_contact_user", False)
    upgraded.setdefault("may_spawn_untracked_agents", False)
    return upgraded


def _legacy_job_projection(
    run_root: Path, run: dict[str, Any], contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Import an eventless v2 snapshot without discarding its jobs."""
    queue = load_json(run_root / "queue.json")
    entries = {item["job_id"]: item for item in queue.get("entries", [])}
    projected = []
    for sequence, job_root in enumerate(sorted((run_root / "jobs").glob("J*")), 1):
        if not (job_root / "job.json").is_file():
            continue
        legacy = load_json(job_root / "job.json")
        workflow_raw = load_json(job_root / "workflow.json")
        entry = entries.get(legacy["id"], {})
        terminal = legacy.get("status") in TERMINAL_JOBS
        nodes = []
        for position, raw_node in enumerate(workflow_raw.get("nodes", []), 1):
            node = dict(raw_node)
            node.update(
                position=position,
                work_units=node.get("work_units") or [
                    node.get("command") or node["id"]
                ],
                completed_work_units=(
                    node.get("work_units")
                    or [node.get("command") or node["id"]]
                ) if terminal else [],
                dispatch_ids=node.get("dispatch_ids", []),
                status="completed" if terminal else (
                    "ready" if position == 1 else "pending"
                ),
            )
            nodes.append(node)
        if not nodes:
            raise OrchestratorError(f"legacy job {legacy['id']} has no workflow nodes")
        job = {
            **legacy,
            "status": legacy["status"] if terminal else "queued",
            "sequence": entry.get("sequence", sequence),
            "depends_on": entry.get("depends_on", []),
            "current_workflow_node_id": None if terminal else nodes[0]["id"],
            "session": None,
            "contract_sha256": content_hash(contracts[legacy["id"]]),
        }
        workflow = {"session_policy": workflow_raw.get(
            "session_policy", "persistent"), "nodes": nodes}
        steps = {"steps": [
            {"id": node["id"], "workflow_node_id": node["id"],
             "status": node["status"], "attempts": [], "result_path": None}
            for node in nodes
        ]}
        projected.append({"job": job, "workflow": workflow, "steps": steps})
    return projected


def _install_migration_static(run_root: Path, data: dict[str, Any]) -> None:
    atomic_write(
        run_root / "protocol" / "job-protocol.md",
        data["protocol_text"].encode("utf-8"),
    )
    write_json(run_root / "protocol" / "manifest.json", data["manifest"])
    for job_id, contract in data["contracts"].items():
        write_json(run_root / "jobs" / job_id / "contract.json", contract)


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    manifest = load_json(run_root / "protocol" / "manifest.json")
    if manifest["protocol_version"] != 2:
        raise OrchestratorError("only version-2 runs can be migrated")
    if not args.authorized_by or not args.reason:
        raise OrchestratorError("migration requires --authorized-by and --reason")
    digest = content_hash(PROTOCOL.read_bytes())
    with run_lease(run_root, args.controller):
        existing_migration = next(
            (event for event in reversed(read_jsonl(run_root / "events.jsonl"))
             if event["type"] == "protocol_migrated"
             and event["data"].get("to") == 3),
            None,
        )
        if existing_migration:
            _install_migration_static(run_root, existing_migration["data"])
            write_snapshots(run_root, replay(run_root))
            return {
                "migrated": True, "resumed": True, "from": 2, "to": 3,
                "sessions_require_bootstrap": True,
            }
        run = load_json(run_root / "run.json")
        contract_documents = {
            path.parent.name: _upgrade_contract(load_json(path), run, digest)
            for path in (run_root / "jobs").glob("*/contract.json")
        }
        imported_events = read_jsonl(run_root / "events.jsonl")
        if not any(event["type"] == "run_status" for event in imported_events):
            append_event(run_root, make_event(
                run_root, "run_status", f"{run['run_id']}:legacy-import",
                {"status": run.get("status", "active")},
            ))
            imported_events = read_jsonl(run_root / "events.jsonl")
        compiled_job_ids = {
            event["data"]["job"]["id"]
            for event in imported_events
            if event["type"] == "job_compiled"
        }
        for item in _legacy_job_projection(
            run_root, run, contract_documents
        ):
            if item["job"]["id"] not in compiled_job_ids:
                append_event(run_root, make_event(
                    run_root, "job_compiled", item["job"]["id"], item
                ))
        migration_id = stable_id("MIG", run["run_id"], 3)
        migrated_at = utc_now()
        manifest = {
            **manifest,
            "protocol_version": 3,
            "sha256": digest,
            "migrated_at": migrated_at,
            "authorized_by": args.authorized_by,
            "reason": args.reason,
        }
        migration_data = {
            "from": 2, "to": 3, "authorized_by": args.authorized_by,
            "reason": args.reason, "protocol_sha256": digest,
            "protocol_text": PROTOCOL.read_text(encoding="utf-8"),
            "manifest": manifest,
            "contracts": contract_documents,
            "contract_hashes": {
                job_id: content_hash(contract)
                for job_id, contract in contract_documents.items()
            },
        }
        event = make_event(
            run_root, "protocol_migrated", migration_id,
            migration_data,
        )
        append_event(run_root, event)
        _install_migration_static(run_root, migration_data)
        write_snapshots(run_root, replay(run_root))
    return {"migrated": True, "from": 2, "to": 3, "sessions_require_bootstrap": True}


def abort_dangling_dispatch(run_root: Path, dispatch_id: str) -> dict[str, Any]:
    events = read_jsonl(run_root / "events.jsonl")
    
    dispatch_event = next((e for e in events if e["type"] == "dispatch_created" and e["data"]["dispatch"]["dispatch_id"] == dispatch_id), None)
    if not dispatch_event:
        raise OrchestratorError(f"dispatch not found: {dispatch_id}")
    
    worker_result_event = next((e for e in events if e["type"] == "worker_result" and e["data"]["dispatch_id"] == dispatch_id), None)
    if worker_result_event:
        raise OrchestratorError(f"dispatch is already resolved or not active: {dispatch_id}")
    
    action_event = next((e for e in events if e["type"] == "action_created" and e["data"]["action"].get("dispatch_id") == dispatch_id), None)
    if not action_event:
        raise OrchestratorError(f"action for dispatch not found: {dispatch_id}")
    action_id = action_event["data"]["action"]["action_id"]
    nonce = dispatch_event["data"]["dispatch"]["nonce"]

    result_data = {
        "schema_version": 3,
        "dispatch_id": dispatch_id,
        "nonce": nonce,
        "status": "failed",
        "summary": "aborted_by_operator",
        "completed_work_units": [],
        "artifacts": [],
        "acceptance_evidence": ["aborted by operator"],
        "blocking_issues": ["aborted by operator"],
        "proposed_jobs": [],
        "improvement_observations": [],
        "checkpoint_sha256": content_hash(b"aborted"),
        "created_at": utc_now(),
    }
    worker_result = make_event(
        run_root, "worker_result", action_id,
        {"dispatch_id": dispatch_id, "result": result_data}
    )
    append_event(run_root, worker_result)

    action_resolved = make_event(
        run_root, "action_resolved", action_id,
        {"action_id": action_id, "response_hash": content_hash(result_data)}
    )
    append_event(run_root, action_resolved)
    
    return {"repaired": True, "dispatch_id": dispatch_id, "action_id": action_id}


def repair_run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    with run_lease(run_root, args.controller):
        if args.abort_dispatch:
            res = abort_dangling_dispatch(run_root, args.abort_dispatch)
            write_snapshots(run_root, replay(run_root))
            return res
        else:
            raise OrchestratorError("repair requires a specific action flag, e.g., --abort-dispatch")



def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--controller", default="jobctl")
    init = sub.add_parser("init", parents=[common])
    request = init.add_mutually_exclusive_group(required=True)
    request.add_argument("--request-file", type=Path)
    request.add_argument("--request")
    init.add_argument("--goal", required=True)
    init.add_argument("--run-id")
    init.add_argument("--state-root", type=Path, default=SKILL_ROOT / "runs")
    init.add_argument("--workspace", type=Path, default=Path.cwd())
    compile_p = sub.add_parser("compile", parents=[common])
    compile_p.add_argument("--run", type=Path, required=True)
    compile_p.add_argument("--definition", type=Path, required=True)
    nxt = sub.add_parser("next", parents=[common])
    nxt.add_argument("--run", type=Path, required=True)
    rec = sub.add_parser("record", parents=[common])
    rec.add_argument("--run", type=Path, required=True)
    rec.add_argument("--action-id", required=True)
    rec.add_argument("--response", type=Path, required=True)
    aud = sub.add_parser("audit")
    aud.add_argument("--run", type=Path, required=True)
    aud.add_argument("--rebuild", action="store_true")
    recovery = sub.add_parser("recover", parents=[common])
    recovery.add_argument("--run", type=Path, required=True)
    recovery.add_argument("--dry-run", action="store_true")
    recovery.add_argument("--evidence", type=Path)
    migration = sub.add_parser("migrate-v2", parents=[common])
    migration.add_argument("--run", type=Path, required=True)
    migration.add_argument("--authorized-by", required=True)
    migration.add_argument("--reason", required=True)
    repair = sub.add_parser("repair", parents=[common])
    repair.add_argument("--run", type=Path, required=True)
    repair.add_argument("--abort-dispatch", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    handlers = {"init": init_run, "compile": compile_jobs, "next": next_action,
                "record": record, "audit": audit, "recover": recover,
                "migrate-v2": migrate, "repair": repair_run}
    try:
        emit(handlers[args.command](args))
        return 0
    except OrchestratorError as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
