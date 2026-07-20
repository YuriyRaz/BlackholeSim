#!/usr/bin/env python3
"""Version-4 job-orchestrator control plane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator_core import (
    ADVISORY_FAILURE_DECISIONS,
    CURRENT_RUN_VERSION,
    OrchestratorError,
    atomic_write,
    audit_v4_state,
    inspect_v4_job_record_recovery,
    load_json,
    load_v4_state,
    reconcile_v4_transport_response,
    record_v4_advisory_decision,
    record_v4_answer,
    record_v4_outcome,
    record_v4_session,
    recover_v4_job_record,
    register_v4_jobs,
    repair_v4_job,
    select_v4_next_operation,
    stable_id,
    utc_now,
    validate_record,
    validate_v4_recovery_evidence,
    write_json,
    write_v4_document,
)


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def init_run(args: argparse.Namespace) -> dict[str, Any]:
    now = utc_now()
    run_id = args.run_id or stable_id("RUN", args.goal, now)
    run_root = args.state_root.resolve() / run_id
    if run_root.exists():
        raise OrchestratorError(f"run already exists: {run_root}")
    try:
        request = args.request_file.read_bytes()
    except OSError as exc:
        raise OrchestratorError(
            f"cannot read initialization request from {args.request_file}: {exc}"
        ) from exc

    setup = {
        "schema_version": CURRENT_RUN_VERSION,
        "request_path": "request.md",
        "workspace": str(args.workspace.resolve()),
        "execution_mode": "sequential",
        "jobs": [],
    }
    run = {
        "schema_version": CURRENT_RUN_VERSION,
        "protocol_version": CURRENT_RUN_VERSION,
        "run_id": run_id,
        "goal": args.goal,
        "status": "active",
        "job_ids": [],
        "created_at": now,
        "updated_at": now,
        "revision": 1,
    }
    validate_record("run", run)
    validate_record("setup", setup)
    (run_root / "jobs").mkdir(parents=True)
    atomic_write(run_root / "request.md", request)
    write_json(run_root / "setup.json", setup)
    write_json(run_root / "jobs" / "index.json", {"jobs": []})
    write_v4_document(run_root / "run.json", "run", run)
    return {"run_root": str(run_root), "run_id": run_id}


def register_jobs(args: argparse.Namespace) -> dict[str, Any]:
    return register_v4_jobs(
        args.run.resolve(),
        load_json(args.definition),
        controller=args.controller,
        advisory_for=args.advisory_for,
    )


def next_action(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    return select_v4_next_operation(load_v4_state(run_root), run_root=run_root)


def record_session(args: argparse.Namespace) -> dict[str, Any]:
    return record_v4_session(
        args.run.resolve(), args.job, args.session_ref, controller=args.controller
    )


def record_outcome(args: argparse.Namespace) -> dict[str, Any]:
    return record_v4_outcome(
        args.run.resolve(),
        args.job,
        load_json(args.outcome),
        controller=args.controller,
        session_ref=args.session_ref,
        evidence=load_json(args.evidence) if args.evidence else None,
    )


def record_answer(args: argparse.Namespace) -> dict[str, Any]:
    return record_v4_answer(
        args.run.resolve(), args.job, args.answer,
        source=args.source, controller=args.controller,
    )


def record_advisory_decision(args: argparse.Namespace) -> dict[str, Any]:
    return record_v4_advisory_decision(
        args.run.resolve(), args.origin, args.advisory, args.decision,
        controller=args.controller, replacement_job_id=args.replacement,
        reason=args.reason,
    )


def recover(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run.resolve()
    if args.dry_run:
        raise OrchestratorError("recover is read-only by default; omit --dry-run or use --apply")
    if not args.job:
        raise OrchestratorError("recover requires --job")
    try:
        load_v4_state(run_root)
    except OrchestratorError as state_error:
        inspection = inspect_v4_job_record_recovery(run_root, args.job)
        if not inspection["malformed"]:
            raise state_error
        evidence = load_json(args.evidence) if args.evidence else None
        if evidence is not None:
            validate_v4_recovery_evidence(
                evidence,
                job_id=args.job,
                session_ref=inspection["previous_version"]["session_ref"],
            )
        result = recover_v4_job_record(
            run_root, args.job, controller=args.controller, apply=args.apply
        )
        if not result["record_restored"] or evidence is None:
            return result
        result["fact_reconciliation"] = reconcile_v4_transport_response(
            run_root, args.job, evidence, controller=args.controller, apply=True
        )
        result["recommended_action"] = result["fact_reconciliation"]["recommended_action"]
        return result
    if not args.evidence:
        raise OrchestratorError("recover requires --evidence when the job record is valid")
    return reconcile_v4_transport_response(
        run_root, args.job, load_json(args.evidence),
        controller=args.controller, apply=args.apply,
    )


def audit(args: argparse.Namespace) -> dict[str, Any]:
    return audit_v4_state(
        args.run.resolve(),
        evidence=(
            load_json(args.evidence) if getattr(args, "evidence", None) else None
        ),
        rebuild_index=getattr(args, "rebuild_index", False),
    )


def repair_run(args: argparse.Namespace) -> dict[str, Any]:
    return repair_v4_job(
        args.run.resolve(), args.job, args.disposition, args.reason,
        controller=args.controller,
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--controller", default="jobctl")
    init = sub.add_parser("init", parents=[common])
    init.add_argument("--request-file", type=Path, required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--run-id")
    init.add_argument("--state-root", type=Path, default=Path.cwd() / ".job-orchestrator" / "runs")
    init.add_argument("--workspace", type=Path, default=Path.cwd())
    register = sub.add_parser("register", parents=[common])
    register.add_argument("--run", type=Path, required=True)
    register.add_argument("--definition", type=Path, required=True)
    register.add_argument("--advisory-for")
    nxt = sub.add_parser("next", parents=[common])
    nxt.add_argument("--run", type=Path, required=True)
    session = sub.add_parser("session", parents=[common])
    session.add_argument("--run", type=Path, required=True)
    session.add_argument("--job", required=True)
    session.add_argument("--session-ref", required=True)
    outcome = sub.add_parser("outcome", parents=[common])
    outcome.add_argument("--run", type=Path, required=True)
    outcome.add_argument("--job", required=True)
    outcome.add_argument("--outcome", type=Path, required=True)
    outcome.add_argument("--session-ref")
    outcome.add_argument("--evidence", type=Path)
    answer = sub.add_parser("answer", parents=[common])
    answer.add_argument("--run", type=Path, required=True)
    answer.add_argument("--job", required=True)
    answer.add_argument("--answer", required=True)
    answer.add_argument("--source", choices=("authoritative", "user"), required=True)
    decision = sub.add_parser("advisory-decision", parents=[common])
    decision.add_argument("--run", type=Path, required=True)
    decision.add_argument("--origin", required=True)
    decision.add_argument("--advisory", required=True)
    decision.add_argument("--decision", choices=ADVISORY_FAILURE_DECISIONS, required=True)
    decision.add_argument("--replacement")
    decision.add_argument("--reason")
    aud = sub.add_parser("audit")
    aud.add_argument("--run", type=Path, required=True)
    aud.add_argument("--evidence", type=Path)
    aud.add_argument(
        "--rebuild-index",
        action="store_true",
        help="rebuild only the derived version-4 jobs/index.json",
    )
    recovery = sub.add_parser("recover", parents=[common])
    recovery.add_argument("--run", type=Path, required=True)
    recovery.add_argument("--job")
    recovery.add_argument("--apply", action="store_true")
    recovery.add_argument("--dry-run", action="store_true")
    recovery.add_argument("--evidence", type=Path)
    repair = sub.add_parser("repair", parents=[common])
    repair.add_argument("--run", type=Path, required=True)
    repair.add_argument("--job", required=True)
    repair.add_argument("--disposition", metavar="{failed,canceled}", required=True)
    repair.add_argument("--reason", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    handlers = {
        "init": init_run, "register": register_jobs, "next": next_action,
        "session": record_session, "outcome": record_outcome,
        "answer": record_answer, "advisory-decision": record_advisory_decision,
        "audit": audit, "recover": recover, "repair": repair_run,
    }
    try:
        emit(handlers[args.command](args))
        return 0
    except OrchestratorError as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
