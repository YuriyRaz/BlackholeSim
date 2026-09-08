"""Trusted protocol-v5 state engine.

Version 4 remains implemented by ``orchestrator_core``. This module deliberately
keeps the new trust model separate so legacy records cannot silently gain
provenance they never stored.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from orchestrator_core import (
    OrchestratorError,
    canonical_bytes,
    content_hash,
    load_json,
    random_id,
    stable_id,
    utc_now,
    validate_record,
    write_json,
)
from transport_v5 import TransportAdapter, TransportVerificationError, configured_adapter


V5 = 5
V5_STATUSES = frozenset({
    "queued", "starting", "running", "completion_claimed", "waiting_for_input",
    "waiting_for_job", "recovering", "blocked", "repair_required", "completed",
    "failed", "canceled",
})
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "canceled"})
TERMINAL_RUN_STATUSES = TERMINAL_JOB_STATUSES
CONDITION_STATUSES = frozenset({"passed", "failed", "not_run", "unavailable", "unknown"})
SIDE_EFFECT_CLASSES = frozenset({"none", "repository", "external_idempotent", "external_non_idempotent"})


def _ensure_v5(value: dict[str, Any], kind: str) -> None:
    if value.get("schema_version") != V5:
        raise OrchestratorError(f"{kind} must use schema_version 5")
    validate_record(kind, value)


def classify_run_protocol(run_root: Path) -> dict[str, Any]:
    """Report protocol trust without upgrading legacy state."""
    run = load_json(Path(run_root) / "run.json")
    version = run.get("schema_version")
    if version == 4:
        return {"version": 4, "trust": "legacy_unattested", "mutable": False}
    if version == V5:
        return {"version": V5, "trust": "authenticated_receipts", "mutable": True}
    return {"version": version, "trust": "unknown", "mutable": False}


def _write(path: Path, kind: str, value: dict[str, Any]) -> None:
    _ensure_v5(value, kind)
    write_json(path, value)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise OrchestratorError(f"cannot hash artifact {path}: {exc}") from exc
    return digest.hexdigest()


def artifact_ref(run_id: str, job_id: str, kind: str) -> str:
    if not all(
        isinstance(item, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item) is not None
        and item not in {".", ".."}
        for item in (run_id, job_id, kind)
    ):
        raise OrchestratorError("artifact reference components must be non-empty path-safe strings")
    return f"run://{run_id}/jobs/{job_id}/{kind}"


def resolve_artifact_ref(run_root: Path, reference: str) -> Path:
    match = re.fullmatch(r"run://([^/]+)/jobs/([^/]+)/([^/]+)", reference)
    if match is None:
        raise OrchestratorError(f"invalid run-scoped artifact reference: {reference!r}")
    run_id, job_id, kind = match.groups()
    if artifact_ref(run_id, job_id, kind) != reference:
        raise OrchestratorError("artifact reference contains an unsafe path component")
    run = load_json(Path(run_root) / "run.json")
    if run.get("run_id") != run_id:
        raise OrchestratorError("artifact reference belongs to another run")
    if kind not in {"prompt", "report", "checkpoint", "evidence"}:
        raise OrchestratorError(f"unsupported artifact kind: {kind}")
    filename = {"prompt": "prompt.md", "report": "report.md", "checkpoint": "checkpoint.md", "evidence": "evidence"}[kind]
    path = (Path(run_root) / "jobs" / job_id / filename).resolve()
    jobs_root = (Path(run_root) / "jobs").resolve()
    if jobs_root not in path.parents:
        raise OrchestratorError("artifact path escapes the run jobs directory")
    return path


@contextmanager
def v5_lock(run_root: Path, controller: str) -> Iterator[None]:
    """Small exclusive lock for v5 mutations, independent of v4 lock records."""
    if not controller:
        raise OrchestratorError("controller must not be empty")
    path = Path(run_root) / "orchestrator-v5.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise OrchestratorError("v5 run lock is held by another controller") from exc
    try:
        os.write(fd, canonical_bytes({"controller": controller, "created_at": utc_now()}))
        os.close(fd)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def init_v5_run(
    request_file: Path,
    goal: str,
    *,
    run_id: str | None = None,
    state_root: Path,
    workspace: Path,
) -> dict[str, str]:
    now = utc_now()
    effective_id = run_id or stable_id("RUN", goal, now)
    run_root = Path(state_root).resolve() / effective_id
    if run_root.exists():
        raise OrchestratorError(f"run already exists: {run_root}")
    try:
        request = Path(request_file).read_bytes()
    except OSError as exc:
        raise OrchestratorError(f"cannot read initialization request: {exc}") from exc
    run_root.joinpath("jobs").mkdir(parents=True)
    run = {
        "schema_version": V5, "protocol_version": V5, "run_id": effective_id,
        "goal": goal, "status": "active", "job_ids": [], "created_at": now,
        "updated_at": now, "revision": 1,
    }
    setup = {
        "schema_version": V5, "request_path": "request.md",
        "workspace": str(Path(workspace).resolve()), "execution_mode": "sequential", "jobs": [],
    }
    _ensure_v5(run, "run")
    _ensure_v5(setup, "setup")
    (run_root / "request.md").write_bytes(request)
    _write(run_root / "run.json", "run", run)
    _write(run_root / "setup.json", "setup", setup)
    write_json(run_root / "jobs" / "index.json", {"jobs": []})
    return {"run_root": str(run_root), "run_id": effective_id}


def _condition(value: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "description", "required", "evidence_required", "verification"}
    missing = required - set(value)
    if missing:
        raise OrchestratorError("completion condition missing fields: " + ", ".join(sorted(missing)))
    if not isinstance(value["id"], str) or not value["id"]:
        raise OrchestratorError("completion condition id must be non-empty")
    if value["verification"] not in {"self", "independent"}:
        raise OrchestratorError("completion condition verification must be self or independent")
    if value["verification"] == "independent" and not value.get("verifier_job_id"):
        raise OrchestratorError(f"independent condition {value['id']} requires verifier_job_id")
    return dict(value)


def _validate_definition(definition: dict[str, Any]) -> None:
    _ensure_v5(definition, "job-definition")
    ids: set[str] = set()
    job_ids = {job["id"] for job in definition["jobs"]}
    for job in definition["jobs"]:
        if job["id"] in ids:
            raise OrchestratorError(f"duplicate job id {job['id']}")
        ids.add(job["id"])
        if job["side_effect_class"] not in SIDE_EFFECT_CLASSES:
            raise OrchestratorError(f"job {job['id']} has invalid side-effect class")
        policy = job.get("recovery_policy")
        if job["side_effect_class"] != "none" and not isinstance(policy, dict):
            raise OrchestratorError(f"job {job['id']} requires a recovery policy")
        if job["side_effect_class"] == "external_idempotent" and not policy.get("idempotency_key"):
            raise OrchestratorError(f"job {job['id']} requires an idempotency key")
        condition_ids: set[str] = set()
        for raw in job["completion_conditions"]:
            condition = _condition(raw)
            if condition["id"] in condition_ids:
                raise OrchestratorError(f"job {job['id']} repeats condition {condition['id']}")
            condition_ids.add(condition["id"])
            verifier = condition.get("verifier_job_id")
            if verifier and verifier not in job_ids:
                raise OrchestratorError(f"condition {condition['id']} references unknown verifier {verifier}")
    for job in definition["jobs"]:
        for dependency in job.get("depends_on", []):
            if dependency not in job_ids:
                raise OrchestratorError(f"job {job['id']} depends on unknown job {dependency}")
        for condition in job["completion_conditions"]:
            verifier = condition.get("verifier_job_id")
            if verifier == job["id"]:
                raise OrchestratorError("a job cannot independently verify itself")
    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {job["id"]: job for job in definition["jobs"]}

    def visit(job_id: str) -> None:
        if job_id in visiting:
            raise OrchestratorError("job dependency cycle detected")
        if job_id in visited:
            return
        visiting.add(job_id)
        for dependency in by_id[job_id].get("depends_on", []):
            visit(dependency)
        visiting.remove(job_id)
        visited.add(job_id)

    for job_id in by_id:
        visit(job_id)


def _render_prompt(run_root: Path, job: dict[str, Any], definition: dict[str, Any], dependency_reports: list[dict[str, Any]]) -> str:
    workspace = load_json(run_root / "setup.json")["workspace"]
    report_ref = artifact_ref(load_json(run_root / "run.json")["run_id"], job["id"], "report")
    report_path = resolve_artifact_ref(run_root, report_ref)
    lines = [
        f"# {definition['title']}",
        f"Job ID: `{job['id']}`",
        "## Root Boundary",
        "The root is control-plane only. Perform domain work in this worker session and do not mutate orchestrator state.",
        "## Goal", definition["goal"],
        "## Workspace", f"`{workspace}`",
        "## Report Artifact",
        f"Reference: `{report_ref}`",
        f"Write path: `{report_path}`",
        "Semantic report content is owned by this worker and must not be authored or replaced by the root.",
        "## Completion Conditions",
    ]
    for condition in definition["completion_conditions"]:
        lines.append(f"- `{condition['id']}`: {condition['description']} (verification: {condition['verification']})")
    if dependency_reports:
        lines.extend(["## Dependency Reports"])
        for report in dependency_reports:
            lines.append(f"- `{report['ref']}` read path `{report['path']}` sha256 `{report['content_sha256']}`")
    if job.get("related_reports"):
        lines.append("## Related Reports")
        for reference in dict.fromkeys(job["related_reports"]):
            if reference.startswith("run://"):
                lines.append(f"- `{reference}`")
            else:
                lines.append(f"- advisory: `{reference}`")
    if definition.get("requirements"):
        lines.extend(["## Requirements", *[f"- {item}" for item in definition["requirements"]]])
    if definition.get("constraints"):
        lines.extend(["## Constraints", *[f"- {item}" for item in definition["constraints"]]])
    lines.extend([
        "## Return Contract",
        "Return exactly one normalized JSON outcome through the transport response.",
        "A completed outcome must include the report artifact digest and condition results.",
    ])
    return "\n\n".join(lines) + "\n"


def register_v5_jobs(run_root: Path, definition: dict[str, Any], *, controller: str) -> dict[str, Any]:
    _validate_definition(definition)
    run_root = Path(run_root)
    with v5_lock(run_root, controller):
        run = load_json(run_root / "run.json")
        setup = load_json(run_root / "setup.json")
        _ensure_v5(run, "run")
        _ensure_v5(setup, "setup")
        if run["job_ids"]:
            raise OrchestratorError("v5 jobs are already registered")
        now = utc_now()
        setup["jobs"] = definition["jobs"]
        jobs: dict[str, dict[str, Any]] = {}
        for sequence, item in enumerate(definition["jobs"], 1):
            job_id = item["id"]
            prompt_path = f"jobs/{job_id}/prompt.md"
            report_path = artifact_ref(run["run_id"], job_id, "report")
            job = {
                "schema_version": V5, "id": job_id, "title": item["title"], "status": "queued",
                "prompt_path": prompt_path, "priority": item.get("priority", 0),
                "creation_sequence": sequence, "depends_on": list(item.get("depends_on", [])),
                "parent_job_id": item.get("parent_job_id"), "waiting_on": [], "pending_question": None,
                "answers": [], "related_reports": list(item.get("related_reports", [])),
                "report_required": item["report_required"], "report_path": report_path,
                "checkpoint_path": artifact_ref(run["run_id"], job_id, "checkpoint"),
                "side_effect_class": item["side_effect_class"], "recovery_policy": item.get("recovery_policy"),
                "dispatches": [], "attempts": [], "active_attempt_id": None, "artifacts": [], "raw_responses": [],
                "outcome": None, "completion_claim": None,
                "completion_conditions": [_condition(value) for value in item["completion_conditions"]],
                "pending_dispatch_id": None, "created_at": now, "updated_at": now, "revision": 1,
            }
            _ensure_v5(job, "job")
            jobs[job_id] = job
        for job_id, job in jobs.items():
            path = run_root / job["prompt_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_render_prompt(run_root, job, setup["jobs"][job["creation_sequence"] - 1], []), encoding="utf-8")
            (run_root / "jobs" / job_id / "report.md").write_text("", encoding="utf-8")
            _write(run_root / "jobs" / job_id / "job.json", "job", job)
        run["job_ids"] = list(jobs)
        run["updated_at"] = now
        run["revision"] += 1
        _write(run_root / "run.json", "run", run)
        _write(run_root / "setup.json", "setup", setup)
        write_json(run_root / "jobs" / "index.json", {"jobs": list(jobs)})
    return {"run_id": run["run_id"], "job_ids": list(jobs), "registered": True}


def load_v5_state(run_root: Path) -> dict[str, Any]:
    run_root = Path(run_root)
    run = load_json(run_root / "run.json")
    setup = load_json(run_root / "setup.json")
    _ensure_v5(run, "run")
    _ensure_v5(setup, "setup")
    jobs: dict[str, dict[str, Any]] = {}
    for job_id in run["job_ids"]:
        job = load_json(run_root / "jobs" / job_id / "job.json")
        _ensure_v5(job, "job")
        if job["id"] != job_id:
            raise OrchestratorError("job path and identity do not match")
        jobs[job_id] = job
    return {"run": run, "setup": setup, "jobs": jobs, "run_root": run_root}


def _derive_run_status(jobs: dict[str, dict[str, Any]]) -> str:
    if not jobs or any(job["status"] not in TERMINAL_JOB_STATUSES for job in jobs.values()):
        return "active"
    if any(job["status"] == "failed" for job in jobs.values()):
        return "failed"
    if any(job["status"] == "canceled" for job in jobs.values()):
        return "canceled"
    return "completed"


def _is_verifier_for(job: dict[str, Any], target: dict[str, Any]) -> bool:
    return any(
        condition.get("verifier_job_id") == job["id"]
        for condition in target.get("completion_conditions", [])
    )


def _dependencies_complete(job: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> bool:
    return all(
        jobs[dependency]["status"] == "completed"
        or (jobs[dependency]["status"] == "completion_claimed" and _is_verifier_for(job, jobs[dependency]))
        for dependency in job["depends_on"]
    )


def _accepted_report(run_root: Path, job: dict[str, Any]) -> dict[str, Any] | None:
    for artifact in job.get("artifacts", []):
        if artifact.get("kind") == "report":
            return artifact
    return None


def _dependency_reports(job: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for dependency_id in job["depends_on"]:
        report = _accepted_report(Path("."), jobs[dependency_id])
        if report is None:
            raise OrchestratorError(f"completed dependency {dependency_id} lacks an accepted report")
        reports.append(report)
    return reports


def select_v5_next_operation(run_root: Path) -> dict[str, Any]:
    state = load_v5_state(run_root)
    run, jobs, setup = state["run"], state["jobs"], state["setup"]
    derived = _derive_run_status(jobs)
    if derived in TERMINAL_RUN_STATUSES:
        return {"operation": "run_complete", "run_status": derived, "successful": derived == "completed"}
    waiting = sorted((job for job in jobs.values() if job["status"] == "waiting_for_input"), key=lambda item: (-item["priority"], item["creation_sequence"]))
    if waiting:
        job = waiting[0]
        return {"operation": "ask_user", "job_id": job["id"], "question": job["pending_question"]}
    resumable = sorted(
        (job for job in jobs.values() if job["status"] == "running" and job.get("pending_dispatch_id")),
        key=lambda item: (-item["priority"], item["creation_sequence"]),
    )
    if resumable:
        job = resumable[0]
        dispatch = next(item for item in job["dispatches"] if item["dispatch_id"] == job["pending_dispatch_id"])
        prompt = (run_root / job["prompt_path"]).read_text(encoding="utf-8")
        return {
            "operation": "resume_job", "job_id": job["id"], "attempt_id": job["active_attempt_id"],
            "native_session_ref": next(item["native_session_ref"] for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"]),
            "prompt": prompt, "dispatch": dispatch,
        }
    ready = sorted((job for job in jobs.values() if job["status"] == "queued" and _dependencies_complete(job, jobs)), key=lambda item: (-item["priority"], item["creation_sequence"]))
    if ready:
        job = ready[0]
        definition = next(item for item in setup["jobs"] if item["id"] == job["id"])
        reports = []
        for dependency in job["depends_on"]:
            report = _accepted_report(run_root, jobs[dependency])
            if report is None:
                raise OrchestratorError(f"dependency {dependency} has no accepted report")
            reports.append(report)
        prompt = _render_prompt(run_root, job, definition, reports)
        prompt_path = run_root / job["prompt_path"]
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_digest = _sha_file(prompt_path)
        dispatch_id = stable_id(
            "DSP", run["run_id"], job["id"], prompt_digest,
            "replacement" if any(item["status"] == "rejected" for item in job["dispatches"]) else "initial",
            job["revision"],
        )
        dispatch = next((item for item in job["dispatches"] if item["dispatch_id"] == dispatch_id), None)
        if dispatch is None:
            dispatch = {
                "schema_version": V5, "dispatch_id": dispatch_id, "run_id": run["run_id"], "job_id": job["id"],
                "kind": "start", "prompt_ref": artifact_ref(run["run_id"], job["id"], "prompt"),
                "prompt_path": job["prompt_path"], "prompt_sha256": prompt_digest, "status": "pending", "created_at": utc_now(),
            }
            _ensure_v5(dispatch, "dispatch")
            job["dispatches"].append(dispatch)
            job["pending_dispatch_id"] = dispatch_id
            job["status"] = "starting"
            job["updated_at"] = utc_now()
            job["revision"] += 1
            _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
        return {
            "operation": "start_job", "job_id": job["id"], "title": job["title"], "prompt": prompt,
            "dispatch": dispatch, "correlation": {"run_id": run["run_id"], "job_id": job["id"], "dispatch_id": dispatch_id},
        }
    return {"operation": "wait"}


def record_v5_answer(run_root: Path, job_id: str, answer: str, *, controller: str) -> dict[str, Any]:
    if not isinstance(answer, str) or not answer.strip():
        raise OrchestratorError("answer must be a non-empty string")
    run_root = Path(run_root)
    with v5_lock(run_root, controller):
        state = load_v5_state(run_root)
        job = state["jobs"].get(job_id)
        if job is None or job["status"] != "waiting_for_input" or not job.get("pending_question"):
            raise OrchestratorError(f"job {job_id} is not waiting for input")
        question = job["pending_question"]
        job["answers"].append({"question": question["text"], "text": answer.strip()})
        job["pending_question"] = None
        job["outcome"] = None
        job["status"] = "running"
        if job.get("active_attempt_id"):
            attempt = next(item for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"])
            attempt["status"] = "active"
            attempt["resolved_at"] = None
        prompt = (run_root / job["prompt_path"]).read_text(encoding="utf-8")
        dispatch_id = stable_id("DSP", state["run"]["run_id"], job_id, "resume", len(job["answers"]), content_hash(prompt))
        dispatch = {
            "schema_version": V5, "dispatch_id": dispatch_id, "run_id": state["run"]["run_id"], "job_id": job_id,
            "kind": "resume", "prompt_ref": artifact_ref(state["run"]["run_id"], job_id, "prompt"),
            "prompt_path": job["prompt_path"], "prompt_sha256": _sha_file(run_root / job["prompt_path"]),
            "status": "pending", "created_at": utc_now(),
        }
        _ensure_v5(dispatch, "dispatch")
        job["dispatches"].append(dispatch)
        job["pending_dispatch_id"] = dispatch_id
        job["updated_at"] = utc_now()
        job["revision"] += 1
        _write(run_root / "jobs" / job_id / "job.json", "job", job)
    return {"operation": "resume_job", "job_id": job_id, "attempt_id": job["active_attempt_id"], "prompt": prompt, "dispatch": dispatch, "recorded": True}


def _verify_adapter(receipt: dict[str, Any], method: str, adapter: TransportAdapter | None) -> None:
    effective = adapter or configured_adapter()
    try:
        getattr(effective, method)(receipt)
    except TransportVerificationError as exc:
        raise OrchestratorError(str(exc)) from exc


def _queue_same_session_repair(run_root: Path, state: dict[str, Any], job: dict[str, Any], reason: str) -> dict[str, Any]:
    prompt_path = run_root / job["prompt_path"]
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt += f"\n## Transport Response Repair\nThe previous response was not accepted because: {reason}\nReturn the exact normalized JSON outcome now. Do not repeat domain work.\n"
    prompt_path.write_text(prompt, encoding="utf-8")
    dispatch_id = stable_id("DSP", state["run"]["run_id"], job["id"], "repair", job["revision"], content_hash(prompt))
    dispatch = {
        "schema_version": V5, "dispatch_id": dispatch_id, "run_id": state["run"]["run_id"], "job_id": job["id"],
        "kind": "resume", "prompt_ref": artifact_ref(state["run"]["run_id"], job["id"], "prompt"),
        "prompt_path": job["prompt_path"], "prompt_sha256": _sha_file(prompt_path), "status": "pending", "created_at": utc_now(),
    }
    _ensure_v5(dispatch, "dispatch")
    job["dispatches"].append(dispatch)
    job["pending_dispatch_id"] = dispatch_id
    job["status"] = "running"
    if job.get("active_attempt_id"):
        attempt = next(item for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"])
        attempt["status"] = "active"
        attempt["resolved_at"] = None
    job["updated_at"] = utc_now()
    job["revision"] += 1
    _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
    return {
        "operation": "resume_job", "job_id": job["id"], "attempt_id": job["active_attempt_id"],
        "native_session_ref": next(item["native_session_ref"] for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"]),
        "prompt": prompt, "dispatch": dispatch, "reason": reason,
    }


def record_v5_launch_receipt(run_root: Path, receipt: dict[str, Any], *, controller: str, adapter: TransportAdapter | None = None) -> dict[str, Any]:
    _ensure_v5(receipt, "launch-receipt")
    run_root = Path(run_root)
    with v5_lock(run_root, controller):
        state = load_v5_state(run_root)
        job = state["jobs"].get(receipt["job_id"])
        if job is None:
            raise OrchestratorError("launch receipt references an unknown job")
        dispatch = next((item for item in job["dispatches"] if item["dispatch_id"] == receipt["dispatch_id"]), None)
        if dispatch is None:
            raise OrchestratorError("launch receipt references an unknown dispatch")
        _verify_adapter(receipt, "verify_launch_receipt", adapter)
        if receipt["run_id"] != state["run"]["run_id"] or receipt["job_id"] != job["id"]:
            raise OrchestratorError("launch receipt correlation does not match the run")
        if receipt["prompt_sha256"] != dispatch["prompt_sha256"]:
            raise OrchestratorError("launch receipt prompt digest does not match the dispatch")
        if dispatch["kind"] == "resume":
            if job["active_attempt_id"] is None:
                raise OrchestratorError("resume dispatch has no active session attempt")
            attempt = next(item for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"])
            if receipt["native_session_ref"] != attempt["native_session_ref"]:
                raise OrchestratorError("resume receipt must use the existing native session")
            dispatch["status"] = "delivered"
            job["pending_dispatch_id"] = None
            job["updated_at"] = utc_now()
            job["revision"] += 1
            _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
            return {"job_id": job["id"], "attempt_id": attempt["attempt_id"], "native_session_ref": attempt["native_session_ref"], "recorded": True, "resumed": True}
        existing = next((attempt for attempt in job["attempts"] if attempt["dispatch_id"] == dispatch["dispatch_id"]), None)
        if existing is not None:
            if existing["native_session_ref"] != receipt["native_session_ref"]:
                raise OrchestratorError("dispatch already has a different native session")
            return {"job_id": job["id"], "attempt_id": existing["attempt_id"], "native_session_ref": existing["native_session_ref"], "recorded": False}
        attempt = {
            "schema_version": V5, "attempt_id": stable_id("ATT", receipt["dispatch_id"], receipt["native_session_ref"]),
            "dispatch_id": receipt["dispatch_id"], "transport": receipt["transport"],
            "native_session_ref": receipt["native_session_ref"], "run_id": receipt["run_id"], "job_id": receipt["job_id"],
            "prompt_sha256": receipt["prompt_sha256"], "status": "active", "created_at": receipt["created_at"],
            "resolved_at": None, "recovery_id": None,
        }
        _ensure_v5(attempt, "attempt")
        job["attempts"].append(attempt)
        job["active_attempt_id"] = attempt["attempt_id"]
        job["pending_dispatch_id"] = None
        job["status"] = "running"
        dispatch["status"] = "delivered"
        job["updated_at"] = utc_now()
        job["revision"] += 1
        _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
    return {"job_id": job["id"], "attempt_id": attempt["attempt_id"], "native_session_ref": attempt["native_session_ref"], "recorded": True}


def _validate_condition_results(job: dict[str, Any], results: list[dict[str, Any]], verifier_job_id: str) -> None:
    expected = {condition["id"]: condition for condition in job["completion_conditions"]}
    seen: set[str] = set()
    for result in results:
        _ensure_v5({"schema_version": V5, **result}, "condition-result")
        condition_id = result["condition_id"]
        if condition_id not in expected or condition_id in seen:
            raise OrchestratorError(f"unknown or duplicate condition result {condition_id}")
        seen.add(condition_id)
        condition = expected[condition_id]
        if condition["verification"] == "independent" and verifier_job_id != job["id"] and condition.get("verifier_job_id") != verifier_job_id:
            raise OrchestratorError(f"condition {condition_id} must be verified by {condition.get('verifier_job_id')}")
        if result["status"] == "passed" and condition.get("evidence_required") and not result.get("evidence"):
            raise OrchestratorError(f"passed condition {condition_id} requires evidence")


def _apply_verifier_results(run_root: Path, state: dict[str, Any], verifier: dict[str, Any], results: list[dict[str, Any]]) -> None:
    """Attach verifier-owned results to claims without letting the verifier self-approve."""
    for target in state["jobs"].values():
        if target["status"] != "completion_claimed":
            continue
        assigned = {
            condition["id"]: condition
            for condition in target["completion_conditions"]
            if condition.get("verifier_job_id") == verifier["id"]
        }
        if not assigned:
            continue
        matching = [result for result in results if result.get("condition_id") in assigned]
        for result in matching:
            _ensure_v5({"schema_version": V5, **result}, "condition-result")
            if result["status"] == "passed" and assigned[result["condition_id"]].get("evidence_required") and not result.get("evidence"):
                raise OrchestratorError(f"verifier result {result['condition_id']} requires evidence")
        existing = list((target.get("completion_claim") or {}).get("condition_results", []))
        existing_by_id = {result["condition_id"]: result for result in existing}
        for result in matching:
            existing_by_id[result["condition_id"]] = result
        if target.get("completion_claim") is not None:
            target["completion_claim"]["condition_results"] = list(existing_by_id.values())
        statuses = {result["condition_id"]: result["status"] for result in existing_by_id.values()}
        if any(statuses.get(condition["id"]) == "failed" for condition in target["completion_conditions"] if condition.get("required")):
            target["status"] = "repair_required"
        elif any(statuses.get(condition["id"]) in {"not_run", "unavailable", "unknown"} for condition in target["completion_conditions"] if condition.get("required")):
            target["status"] = "blocked"
        elif all(statuses.get(condition["id"]) == "passed" for condition in target["completion_conditions"] if condition.get("required")):
            target["status"] = "completed"
        target["updated_at"] = utc_now()
        target["revision"] += 1
        _write(run_root / "jobs" / target["id"] / "job.json", "job", target)


def record_v5_response_receipt(run_root: Path, receipt: dict[str, Any], *, controller: str, adapter: TransportAdapter | None = None) -> dict[str, Any]:
    _ensure_v5(receipt, "response-receipt")
    actual_hash = hashlib.sha256(receipt["raw_response"].encode("utf-8")).hexdigest()
    if actual_hash != receipt["response_sha256"]:
        raise OrchestratorError("response receipt hash does not match raw response")
    run_root = Path(run_root)
    with v5_lock(run_root, controller):
        state = load_v5_state(run_root)
        job = state["jobs"].get(receipt["job_id"])
        if job is None:
            raise OrchestratorError("response receipt references an unknown job")
        attempt = next((item for item in job["attempts"] if item["attempt_id"] == receipt["attempt_id"]), None)
        if attempt is None or job["active_attempt_id"] != attempt["attempt_id"]:
            raise OrchestratorError("response receipt does not reference the active attempt")
        if attempt["status"] == "returned":
            if any(item.get("response_id") == receipt["response_id"] for item in job.get("raw_responses", [])):
                return {"job_id": job["id"], "status": job["status"], "response_id": receipt["response_id"], "recorded": False}
            raise OrchestratorError("active attempt already has a returned response; resume it before sending another response")
        if receipt["run_id"] != state["run"]["run_id"] or receipt["native_session_ref"] != attempt["native_session_ref"]:
            raise OrchestratorError("response receipt correlation does not match the active attempt")
        _verify_adapter(receipt, "verify_response_receipt", adapter)
        raw = {
            "schema_version": V5, "response_id": receipt["response_id"], "attempt_id": attempt["attempt_id"],
            "response_sha256": receipt["response_sha256"], "raw_response": receipt["raw_response"], "received_at": receipt["received_at"],
        }
        _ensure_v5(raw, "raw-response")
        job.setdefault("raw_responses", []).append(raw)
        if receipt["status"] == "empty" and receipt.get("session_liveness") == "live":
            return _queue_same_session_repair(run_root, state, job, "the transport returned an empty response")
        if receipt["status"] != "returned" or not receipt["raw_response"]:
            attempt["status"] = receipt["status"] if receipt["status"] in {"canceled", "lost", "unknown"} else "unknown"
            job["status"] = "recovering"
            job["updated_at"] = utc_now()
            job["revision"] += 1
            _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
            return {"job_id": job["id"], "status": "recovering", "recovery_required": True}
        try:
            normalized = json.loads(receipt["raw_response"])
        except json.JSONDecodeError:
            return _queue_same_session_repair(run_root, state, job, "the worker response was malformed JSON")
        if not isinstance(normalized, dict):
            return _queue_same_session_repair(run_root, state, job, "the worker response was not a JSON object")
        normalized.setdefault("schema_version", V5)
        normalized["response_id"] = receipt["response_id"]
        _ensure_v5(normalized, "outcome")
        artifacts = []
        for item in normalized.get("artifacts", []):
            if not isinstance(item, dict) or not isinstance(item.get("ref"), str) or not isinstance(item.get("content_sha256"), str):
                raise OrchestratorError("worker artifact claims require ref and content_sha256")
            path = resolve_artifact_ref(run_root, item["ref"])
            if path.resolve() not in {resolve_artifact_ref(run_root, job["report_path"]).resolve()} and item["ref"] != job["checkpoint_path"] and "/evidence" not in item["ref"]:
                raise OrchestratorError("worker artifact is not owned by the active job")
            digest = _sha_file(path)
            if digest != item["content_sha256"]:
                raise OrchestratorError("worker artifact digest does not match current bytes")
            kind = item["ref"].rsplit("/", 1)[-1]
            if kind not in {"report", "checkpoint", "evidence"}:
                raise OrchestratorError("unsupported worker artifact kind")
            artifact = {
                "schema_version": V5, "ref": item["ref"], "path": str(path), "kind": kind,
                "producer_job_id": job["id"], "attempt_id": attempt["attempt_id"],
                "response_sha256": receipt["response_sha256"], "content_sha256": digest, "accepted_at": utc_now(),
            }
            _ensure_v5(artifact, "artifact")
            artifacts.append(artifact)
        if normalized["status"] == "completed":
            report_missing = job["report_required"] and not any(item["kind"] == "report" for item in artifacts)
            results = normalized.get("condition_results", [])
            _validate_condition_results(job, results, job["id"])
            claim = {
                "schema_version": V5, "response_id": receipt["response_id"], "condition_results": results, "claimed_at": utc_now(),
            }
            _ensure_v5(claim, "completion-claim")
            job["completion_claim"] = claim
            self_results = {
                result["condition_id"]: result
                for result in results
                if result.get("verified_by") == job["id"]
            }
            self_unmet = any(
                condition["required"]
                and condition["verification"] == "self"
                and self_results.get(condition["id"], {}).get("status") != "passed"
                for condition in job["completion_conditions"]
            )
            self_required_statuses = {
                condition["id"]: self_results.get(condition["id"], {}).get("status")
                for condition in job["completion_conditions"]
                if condition["required"] and condition["verification"] == "self"
            }
            independent_pending = any(
                condition["required"] and condition["verification"] == "independent"
                and not any(
                    result["condition_id"] == condition["id"]
                    and result["status"] == "passed"
                    and result.get("verified_by") == condition.get("verifier_job_id")
                    for result in results
                )
                for condition in job["completion_conditions"]
            )
            if any(status == "failed" for status in self_required_statuses.values()):
                job["status"] = "repair_required"
            elif any(status in {None, "not_run", "unavailable", "unknown"} for status in self_required_statuses.values()):
                job["status"] = "blocked"
            else:
                job["status"] = "completion_claimed" if independent_pending or self_unmet or report_missing else "completed"
        elif normalized["status"] == "needs_input":
            if not normalized.get("question"):
                raise OrchestratorError("needs_input outcome requires a question")
            job["status"] = "waiting_for_input"
            job["pending_question"] = {"text": normalized["question"], "context": normalized.get("context", normalized["summary"])}
        else:
            job["status"] = "failed"
        job["outcome"] = normalized
        job["artifacts"].extend(artifacts)
        attempt["status"] = "returned"
        attempt["resolved_at"] = utc_now()
        job["updated_at"] = utc_now()
        job["revision"] += 1
        _write(run_root / "jobs" / job["id"] / "job.json", "job", job)
        _apply_verifier_results(run_root, state, job, normalized.get("condition_results", []))
    return {"job_id": job["id"], "status": job["status"], "response_id": receipt["response_id"], "recorded": True}


def audit_v5_state(run_root: Path) -> dict[str, Any]:
    state = load_v5_state(run_root)
    issues: list[str] = []
    for job in state["jobs"].values():
        if job["active_attempt_id"] is not None and not any(item["attempt_id"] == job["active_attempt_id"] for item in job["attempts"]):
            issues.append(f"job {job['id']} active attempt is missing")
        for artifact in job["artifacts"]:
            try:
                if _sha_file(Path(artifact["path"])) != artifact["content_sha256"]:
                    issues.append(f"job {job['id']} artifact changed: {artifact['ref']}")
            except OrchestratorError as exc:
                issues.append(str(exc))
    return {"valid": not issues, "issues": issues, "protocol": "v5", "legacy_unattested": False}


def recover_v5_job(run_root: Path, job_id: str, evidence: dict[str, Any], *, controller: str) -> dict[str, Any]:
    _ensure_v5(evidence, "recovery-evidence")
    with v5_lock(Path(run_root), controller):
        state = load_v5_state(run_root)
        job = state["jobs"].get(job_id)
        if job is None:
            raise OrchestratorError(f"unknown job {job_id}")
        if evidence["classification"] in {"unknown", "contradictory"}:
            job["status"] = "blocked"
        elif evidence["classification"] in {"lost", "canceled"}:
            if job["active_attempt_id"]:
                attempt = next(item for item in job["attempts"] if item["attempt_id"] == job["active_attempt_id"])
                attempt["status"] = "replaced"
                attempt["resolved_at"] = utc_now()
                attempt["recovery_id"] = evidence["recovery_id"]
                for dispatch in job["dispatches"]:
                    if dispatch["dispatch_id"] == attempt["dispatch_id"]:
                        dispatch["status"] = "rejected"
            job["active_attempt_id"] = None
            job["pending_dispatch_id"] = None
            job["status"] = "queued"
        else:
            job["status"] = "running"
        job["updated_at"] = utc_now()
        job["revision"] += 1
        _write(Path(run_root) / "jobs" / job_id / "job.json", "job", job)
    return {"job_id": job_id, "status": job["status"], "recovery_id": evidence["recovery_id"], "replacement_authorized": job["status"] == "queued"}


def repair_v5_job(run_root: Path, job_id: str, disposition: str, reason: str, *, controller: str) -> dict[str, Any]:
    if disposition not in {"failed", "canceled"}:
        raise OrchestratorError("v5 repair disposition must be failed or canceled")
    if not isinstance(reason, str) or not reason.strip():
        raise OrchestratorError("repair reason must be non-empty")
    with v5_lock(Path(run_root), controller):
        state = load_v5_state(run_root)
        job = state["jobs"].get(job_id)
        if job is None:
            raise OrchestratorError(f"unknown job {job_id}")
        if job["status"] in TERMINAL_JOB_STATUSES:
            raise OrchestratorError(f"job {job_id} is already terminal")
        job["status"] = disposition
        job["pending_question"] = None
        job["updated_at"] = utc_now()
        job["revision"] += 1
        _write(Path(run_root) / "jobs" / job_id / "job.json", "job", job)
    return {"job_id": job_id, "status": disposition, "reason": reason, "recorded": True}
