#!/usr/bin/env python3
"""Restricted worker-side protocol v3 helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import orchestrator_core as core
from orchestrator_core import (
    OrchestratorError, SCHEMA_VERSION, atomic_write, content_hash, load_json,
    utc_now, validate_dispatch, write_json,
)


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def contract_root(path: Path) -> Path:
    return path.resolve().parent


def allowed_paths(contract_path: Path, contract: dict[str, Any]) -> list[Path]:
    root = contract_root(contract_path)
    paths = [(root / item).resolve() for item in contract["artifact_paths"]]
    if not paths or any(not within(path, [root]) for path in paths):
        raise OrchestratorError("contract artifact paths must stay within the job artifact root")
    return paths


def validate_schema(kind: str, value: dict[str, Any]) -> None:
    """Use the shared schema validator when present, with legacy fallback."""
    validator = getattr(core, "validate_schema", core.validate_record)
    validator(kind, value)


def require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestratorError(f"{label} must be a non-empty string")
    return value.strip()


def current_job(contract_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    job_path = contract_path.parent / "job.json"
    if not job_path.exists():
        raise OrchestratorError("current job snapshot is missing")
    job = load_json(job_path)
    if job.get("id") != contract.get("job_id"):
        raise OrchestratorError("job snapshot identity does not match contract")
    return job


def validate_contract(contract_path: Path, contract: dict[str, Any]) -> Path:
    required = {
        "contract_version", "revision", "job_id", "protocol", "workspace",
        "allowed_edit_roots", "capabilities", "artifact_paths", "report_path",
        "checkpoint_path",
    }
    missing = sorted(required - contract.keys())
    if missing:
        raise OrchestratorError(f"contract missing fields: {', '.join(missing)}")
    if contract["contract_version"] != SCHEMA_VERSION:
        raise OrchestratorError(f"contract must use version {SCHEMA_VERSION}")
    if not isinstance(contract["revision"], int) or contract["revision"] < 1:
        raise OrchestratorError("contract revision must be a positive integer")
    require_nonempty(contract["job_id"], "contract job_id")
    protocol = contract.get("protocol")
    if not isinstance(protocol, dict):
        raise OrchestratorError("contract protocol must be an object")
    for field in ("path", "version", "sha256"):
        if field not in protocol:
            raise OrchestratorError(f"contract protocol missing field: {field}")
    allowed_paths(contract_path, contract)
    protocol_path = (contract_path.parent / protocol["path"]).resolve()
    if not protocol_path.is_file():
        raise OrchestratorError("frozen protocol file is missing")
    return protocol_path


def file_evidence(path: Path, root: Path, purpose: str | None = None) -> dict[str, str]:
    evidence = {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": content_hash(path.read_bytes()),
    }
    if purpose is not None:
        evidence["purpose"] = purpose
    return evidence


def acknowledge(args: argparse.Namespace) -> dict[str, Any]:
    contract_path = args.contract.resolve()
    contract = load_json(contract_path)
    protocol = validate_contract(contract_path, contract)
    job = current_job(contract_path, contract)
    actual = content_hash(protocol.read_bytes())
    if contract["protocol"]["version"] != 3 or actual != contract["protocol"]["sha256"]:
        raise OrchestratorError("frozen protocol version or hash mismatch")
    expected = {
        "protocol_version": getattr(args, "protocol_version", None),
        "protocol_sha256": getattr(args, "protocol_sha256", None),
        "job_id": getattr(args, "job_id", None),
        "contract_revision": getattr(args, "contract_revision", None),
        "current_workflow_node_id": getattr(args, "current_node", None),
    }
    authoritative = {
        "protocol_version": contract["protocol"]["version"],
        "protocol_sha256": actual,
        "job_id": contract["job_id"],
        "contract_revision": contract["revision"],
        "current_workflow_node_id": job.get("current_workflow_node_id"),
    }
    mismatches = [
        field for field, value in expected.items()
        if value is not None and value != authoritative[field]
    ]
    if mismatches:
        raise OrchestratorError(
            f"bootstrap acknowledgement mismatch: {', '.join(sorted(mismatches))}"
        )
    session_id = getattr(args, "session_id", None)
    if session_id is not None:
        session_id = require_nonempty(session_id, "session_id")
    ack = {
        "schema_version": 3, "protocol_version": 3, "protocol_sha256": actual,
        "job_id": contract["job_id"], "contract_revision": contract["revision"],
        "current_workflow_node_id": authoritative["current_workflow_node_id"],
        "acknowledged_at": utc_now(),
    }
    if session_id is not None:
        ack["session_id"] = session_id
    validate_schema("acknowledgement", ack)
    result = {"protocol_ack": ack}
    if session_id is not None:
        result["session_id"] = session_id
    return result


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    dispatch_path = args.dispatch.resolve()
    if dispatch_path.parent.name != "dispatches":
        raise OrchestratorError("dispatch must be read from the job dispatches directory")
    dispatch = load_json(dispatch_path)
    validate_dispatch(dispatch, {
        "dispatch_bounds": {
            "max_work_units": 8, "max_edit_roots": 4,
            "max_estimated_minutes": 90, "require_override_when_exceeded": True,
        }
    })
    contract_path = dispatch_path.parents[1] / "contract.json"
    contract = load_json(contract_path)
    protocol_path = validate_contract(contract_path, contract)
    job = current_job(contract_path, contract)
    if dispatch_path.name != f"{dispatch['dispatch_id']}.json":
        raise OrchestratorError("dispatch filename does not match dispatch identity")
    expected = (
        contract["job_id"], contract["revision"], contract["protocol"]["sha256"],
        str(Path(contract["workspace"]).resolve()),
    )
    actual = (
        dispatch["job_id"], dispatch["contract_revision"],
        dispatch["protocol_sha256"], str(Path(dispatch["workspace"]).resolve()),
    )
    if expected != actual:
        raise OrchestratorError("dispatch identity, revision, protocol, or workspace mismatch")
    if content_hash(protocol_path.read_bytes()) != dispatch["protocol_sha256"]:
        raise OrchestratorError("dispatch protocol hash does not match frozen protocol")
    current_node = getattr(args, "current_node", None)
    authoritative_node = job.get("current_workflow_node_id")
    if dispatch["workflow_node_id"] != authoritative_node:
        raise OrchestratorError("dispatch is not for the current workflow node")
    if current_node is not None and current_node != authoritative_node:
        raise OrchestratorError("dispatch workflow node mismatch")
    session_id = getattr(args, "session_id", None)
    if session_id is not None and session_id != dispatch.get("session_id"):
        raise OrchestratorError("dispatch session identity mismatch")
    if session_id is not None:
        require_nonempty(session_id, "session_id")
    contract_roots = {str(Path(item).resolve()) for item in contract.get("allowed_edit_roots", [])}
    dispatch_roots = {str(Path(item).resolve()) for item in dispatch.get("allowed_edit_roots", [])}
    if not dispatch_roots.issubset(contract_roots):
        raise OrchestratorError("dispatch edit roots exceed contract")
    if not set(dispatch.get("capabilities", [])).issubset(contract.get("capabilities", [])):
        raise OrchestratorError("dispatch capabilities exceed contract")
    nonce = getattr(args, "nonce", None)
    if nonce is not None and nonce != dispatch["nonce"]:
        raise OrchestratorError("dispatch nonce mismatch")
    return {
        "valid": True, "dispatch_id": dispatch["dispatch_id"],
        "job_id": dispatch["job_id"],
        "workflow_node_id": dispatch["workflow_node_id"],
        "session_id": dispatch.get("session_id"),
        "work_units": dispatch["work_units"],
        "prohibited_actions": dispatch["prohibited_actions"],
        "worker_owned_paths": [str(item) for item in allowed_paths(contract_path, contract)],
    }


def checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    dispatch_path = args.dispatch.resolve()
    dispatch = load_json(dispatch_path)
    inspect(argparse.Namespace(
        dispatch=dispatch_path,
        nonce=dispatch["nonce"],
        session_id=dispatch.get("session_id"),
        current_node=dispatch["workflow_node_id"],
    ))
    contract_path = args.dispatch.resolve().parents[1] / "contract.json"
    contract = load_json(contract_path)
    root = contract_root(contract_path)
    checkpoint_path = (root / contract["checkpoint_path"]).resolve()
    progress_path = (root / "progress.json").resolve()
    roots = allowed_paths(contract_path, contract)
    if not within(checkpoint_path, roots) or not within(progress_path, roots):
        raise OrchestratorError("checkpoint outputs are outside worker-owned paths")
    completed = args.completed_work_unit or []
    if not set(completed).issubset(set(dispatch["work_units"])):
        raise OrchestratorError("checkpoint contains work outside its dispatch")
    machine = {
        "schema_version": 3, "dispatch_id": dispatch["dispatch_id"],
        "phase": args.phase, "completed_work_units": completed,
        "decisions": args.decision or [], "unresolved_issues": args.issue or [],
        "artifact_paths": args.artifact or [],
        "next_permitted_action": args.next_action,
    }
    lines = [
        f"# Checkpoint: {dispatch['dispatch_id']}", "",
        f"Phase: {args.phase}", "",
        "Completed work units:", *[f"- {item}" for item in completed],
        "", "Decisions:", *[f"- {item}" for item in (args.decision or [])],
        "", "Unresolved issues:", *[f"- {item}" for item in (args.issue or [])],
        "", f"Next permitted action: {args.next_action}", "",
    ]
    checkpoint_bytes = "\n".join(lines).encode("utf-8")
    digest = content_hash(checkpoint_bytes)
    progress = {
        "schema_version": 3, "dispatch_id": dispatch["dispatch_id"],
        "nonce": dispatch["nonce"], "phase": args.phase,
        "completed_work_units": completed, "checkpoint_sha256": digest,
        "updated_at": utc_now(), "checkpoint": machine,
    }
    validate_schema("checkpoint", machine)
    validate_schema("progress", progress)
    atomic_write(checkpoint_path, checkpoint_bytes)
    write_json(progress_path, progress)
    return progress


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    dispatch_path = args.dispatch.resolve()
    dispatch = load_json(dispatch_path)
    inspect(argparse.Namespace(
        dispatch=dispatch_path,
        nonce=dispatch["nonce"],
        session_id=getattr(args, "session_id", dispatch.get("session_id")),
        current_node=dispatch["workflow_node_id"],
    ))
    contract_path = dispatch_path.parents[1] / "contract.json"
    contract = load_json(contract_path)
    root = contract_root(contract_path)
    roots = allowed_paths(contract_path, contract)
    progress_path = (root / contract.get("progress_path", "progress.json")).resolve()
    report_path = (root / contract["report_path"]).resolve()
    checkpoint_path = (root / contract["checkpoint_path"]).resolve()
    if any(not within(path, roots) for path in (progress_path, report_path, checkpoint_path)):
        raise OrchestratorError("required worker artifact path is outside worker-owned paths")
    if not progress_path.exists() or not report_path.exists() or not checkpoint_path.exists():
        raise OrchestratorError("finalization requires report, checkpoint, and progress")
    if not all(path.is_file() for path in (progress_path, report_path, checkpoint_path)):
        raise OrchestratorError("report, checkpoint, and progress must be regular files")
    if not report_path.read_text(encoding="utf-8").strip():
        raise OrchestratorError("report must not be empty")
    progress = load_json(progress_path)
    validate_schema("progress", progress)
    if (progress["dispatch_id"], progress["nonce"]) != (
        dispatch["dispatch_id"], dispatch["nonce"]
    ):
        raise OrchestratorError("progress is not bound to dispatch")
    if content_hash(checkpoint_path.read_bytes()) != progress["checkpoint_sha256"]:
        raise OrchestratorError("checkpoint hash mismatch")
    checkpoint_record = progress.get("checkpoint")
    if not isinstance(checkpoint_record, dict):
        raise OrchestratorError("progress must contain the current checkpoint record")
    validate_schema("checkpoint", checkpoint_record)
    if checkpoint_record.get("dispatch_id") != dispatch["dispatch_id"]:
        raise OrchestratorError("checkpoint is not bound to dispatch")
    completed = progress["completed_work_units"]
    if not isinstance(completed, list) or any(unit not in dispatch["work_units"] for unit in completed):
        raise OrchestratorError("progress contains work units outside the dispatch")
    evidence = [require_nonempty(item, "acceptance evidence")
                for item in (args.acceptance_evidence or [])]
    if len(evidence) != len(set(evidence)):
        raise OrchestratorError("acceptance evidence must not contain duplicates")
    artifact_evidence = []
    for item in args.artifact or []:
        path = Path(item)
        path = (path if path.is_absolute() else root / path).resolve()
        if not within(path, roots) or not path.is_file():
            raise OrchestratorError(f"artifact is missing or outside worker-owned paths: {item}")
        artifact_evidence.append(file_evidence(path, root, "supporting artifact"))
    if args.status in {"completed", "partial"} and not evidence:
        raise OrchestratorError("completed and partial results require acceptance evidence")
    if args.status == "completed":
        missing = set(dispatch["work_units"]) - set(completed)
        if missing:
            raise OrchestratorError(f"completed result has unfinished work units: {sorted(missing)}")
    blocking_issues = [
        require_nonempty(item, "blocking issue") for item in (args.blocking_issue or [])
    ]
    if args.status == "blocked":
        if not blocking_issues:
            raise OrchestratorError("blocked result requires a precise blocking issue")
        checkpoint_issues = checkpoint_record.get("unresolved_issues")
        if not isinstance(checkpoint_issues, list) or not checkpoint_issues:
            raise OrchestratorError("blocked result requires a current checkpoint with the issue")
        if any(issue not in checkpoint_issues for issue in blocking_issues):
            raise OrchestratorError("blocking issue must be recorded in the current checkpoint")
    elif blocking_issues:
        raise OrchestratorError("blocking issues are only valid for blocked results")
    artifact_evidence = [
        file_evidence(report_path, root, "worker report"),
        file_evidence(checkpoint_path, root, "current checkpoint"),
        file_evidence(progress_path, root, "machine-readable progress"),
        *artifact_evidence,
    ]
    result = {
        "schema_version": 3, "dispatch_id": dispatch["dispatch_id"],
        "nonce": dispatch["nonce"], "status": args.status, "summary": args.summary,
        "completed_work_units": completed,
        "artifacts": artifact_evidence,
        "acceptance_evidence": evidence,
        "blocking_issues": blocking_issues,
        "proposed_jobs": [], "improvement_observations": [],
        "checkpoint_sha256": progress["checkpoint_sha256"], "created_at": utc_now(),
    }
    if "ready_for_next_step" in result:
        raise OrchestratorError("worker result must not assert workflow readiness")
    validate_schema("result", result)
    result_root = root / "results"
    result_root.mkdir(exist_ok=True)
    result_path = result_root / f"{dispatch['dispatch_id']}.json"
    if not within(result_path, roots):
        raise OrchestratorError("result output is outside worker-owned paths")
    write_json(result_path, result)
    return {"result": result, "result_path": str(result_path)}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    ack = sub.add_parser("acknowledge")
    ack.add_argument("--contract", type=Path, required=True)
    ack.add_argument("--protocol-version", type=int, required=True)
    ack.add_argument("--protocol-sha256", required=True)
    ack.add_argument("--job-id", required=True)
    ack.add_argument("--contract-revision", type=int, required=True)
    ack.add_argument("--current-node", required=True)
    ack.add_argument("--session-id")
    ins = sub.add_parser("inspect")
    ins.add_argument("--dispatch", type=Path, required=True)
    ins.add_argument("--nonce", required=True)
    ins.add_argument("--session-id", required=True)
    ins.add_argument("--current-node", required=True)
    check = sub.add_parser("checkpoint")
    check.add_argument("--dispatch", type=Path, required=True)
    check.add_argument("--phase", required=True)
    check.add_argument("--completed-work-unit", action="append")
    check.add_argument("--decision", action="append")
    check.add_argument("--issue", action="append")
    check.add_argument("--artifact", action="append")
    check.add_argument("--next-action", required=True)
    final = sub.add_parser("finalize")
    final.add_argument("--dispatch", type=Path, required=True)
    final.add_argument("--status", choices=["completed", "partial", "blocked", "failed"], required=True)
    final.add_argument("--summary", required=True)
    final.add_argument("--artifact", action="append")
    final.add_argument("--acceptance-evidence", action="append")
    final.add_argument("--blocking-issue", action="append")
    final.add_argument("--session-id", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    handlers = {"acknowledge": acknowledge, "inspect": inspect,
                "checkpoint": checkpoint, "finalize": finalize}
    try:
        emit(handlers[args.command](args))
        return 0
    except OrchestratorError as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
