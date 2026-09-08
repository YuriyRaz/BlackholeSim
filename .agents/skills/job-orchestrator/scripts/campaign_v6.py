"""Production campaign initialization for the canonical v6 strategy compiler."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from orchestrator_core import (
    SCHEMA_VERSION,
    V6_REVISION,
    OrchestratorError,
    chronological_run_id,
    load_json,
    stable_id,
    utc_now,
    write_json,
)
from strategy_v6 import (
    CompilationMode,
    ContextModule,
    ContextModuleRegistry,
    PhaseContract,
    PhaseDefinition,
    StrategyCompiler,
    StrategyComposer,
    build_default_strategy_registry,
)


MODE_ALIASES = {
    None: "full_campaign",
    "full": "full_campaign",
    "full_campaign": "full_campaign",
    "proposal-only": "proposal_only",
    "proposal_only": "proposal_only",
    "implementation-from-proposal": "implementation_from_proposal",
    "implementation_from_proposal": "implementation_from_proposal",
    "architect-review-only": "architect_review_only",
    "architect_review_only": "architect_review_only",
    "custom": "custom",
}


def _entry_artifact_names(values: list[str]) -> tuple[str, ...]:
    names = []
    for value in values:
        name, separator, reference = value.partition("=")
        if not separator or not name or not reference:
            raise OrchestratorError("--entry-artifact must use NAME=REFERENCE")
        names.append(name)
    return tuple(names)


def _require_mode_entry(mode: str, inputs: tuple[str, ...], review_target: str | None) -> None:
    required = {
        "implementation_from_proposal": {"reviewed_proposal"},
        "architect_review_only": {"implementation_evidence"},
    }.get(mode, set())
    missing = required - set(inputs)
    if mode == "architect_review_only" and not review_target:
        missing.add("review_target")
    if missing:
        raise OrchestratorError(
            f"{mode} entry contract requires: {', '.join(sorted(missing))}"
        )


def _phase_from_config(value: Any) -> PhaseDefinition:
    if not isinstance(value, dict):
        raise OrchestratorError("custom phase must be an object")
    required = {"phase_id", "role", "inputs", "outputs", "prompt"}
    missing = sorted(required - set(value))
    if missing:
        raise OrchestratorError(f"custom phase is missing: {', '.join(missing)}")
    return PhaseDefinition(
        phase_id=value["phase_id"],
        prompt_fragment=value["prompt"],
        contract=PhaseContract(tuple(value["inputs"]), tuple(value["outputs"])),
        role=value["role"],
        purpose_key=value.get("purpose_key"),
        is_read_only=bool(value.get("read_only", False)),
        side_effect_class=value.get("side_effect_class", "none"),
    )


def _resolve_configuration(args: argparse.Namespace):
    config = load_json(Path(args.strategy_config)) if args.strategy_config else {}
    if not isinstance(config, dict):
        raise OrchestratorError("strategy configuration must be a JSON object")
    registry = build_default_strategy_registry()
    definition = registry.get_strategy("default_adaptive", 1)
    composer = StrategyComposer(registry)
    for operation in config.get("operations", []):
        if not isinstance(operation, dict):
            raise OrchestratorError("each strategy operation must be an object")
        op = operation.get("operation")
        target = operation.get("target_phase")
        if not isinstance(target, str):
            raise OrchestratorError("strategy operation target_phase is required")
        if op == "extend":
            phase = _phase_from_config(operation.get("phase"))
            composer.extend_phase(phase.phase_id, target, phase)
        elif op == "replace":
            composer.replace_phase(target, _phase_from_config(operation.get("phase")))
        elif op == "configure":
            composer.configure_phase(target, operation.get("config", {}))
        elif op == "disable":
            composer.disable_phase(target)
        else:
            raise OrchestratorError(f"invalid strategy composition operation {op!r}")
    if config.get("operations"):
        errors = composer.validate_composition(definition.strategy_id, definition.version)
        if errors:
            ambiguous = next((error for error in errors if "ambiguous" in error), None)
            if ambiguous:
                raise OrchestratorError(
                    f"initialization requires one user decision: {ambiguous}. Which operation should apply?"
                )
            raise OrchestratorError("strategy composition rejected: " + "; ".join(errors))
        definition = composer.apply_composition(definition.strategy_id, definition.version)
        registry.register_strategy(definition)

    context_registry = ContextModuleRegistry()
    contexts = []
    for value in config.get("context_modules", []):
        if not isinstance(value, dict):
            raise OrchestratorError("each context module must be an object")
        module = ContextModule(
            module_id=value["module_id"],
            namespace=value["namespace"],
            constraints=value.get("constraints"),
            version=value.get("version", 1),
            inherited_from=tuple(value.get("inherited_from", [])),
            applicable_roles=tuple(value.get("applicable_roles", [])),
            evidence_requirements=tuple(value.get("evidence_requirements", [])),
            source_rules=tuple(value.get("source_rules", [])),
            goal_gates=tuple(value.get("goal_gates", [])),
        )
        conflicts = context_registry.validate_module_conflicts(module)
        if conflicts:
            raise OrchestratorError(
                "initialization requires one user decision: "
                + conflicts[0]
                + ". Which context constraint should apply?"
            )
        context_registry.add_context_module(module)
        contexts.append(module)
    context_registry.freeze_module_versions([module.module_id for module in contexts])
    return registry, definition, tuple(contexts), config


def resume_frozen_campaign(args: argparse.Namespace) -> dict[str, Any]:
    from graph_v6 import GraphState, compute_graph_digest

    run_root = Path(args.resume_run) if args.resume_run else Path(args.state_root) / str(args.run_id or "")
    run_path = run_root / "run.json"
    strategy_path = run_root / "strategy.json"
    graph_path = run_root / "graph" / "graph.json"
    if not run_path.exists() or not strategy_path.exists() or not graph_path.exists():
        raise OrchestratorError("resume requires an existing frozen v6 campaign")
    run = load_json(run_path)
    strategy = load_json(strategy_path)
    graph = GraphState.load(graph_path)
    if run.get("schema_version") != 6 or run.get("protocol_revision") != V6_REVISION:
        raise OrchestratorError("resume rejected incompatible campaign protocol")
    if compute_graph_digest(graph) != run.get("graph_digest"):
        raise OrchestratorError("resume audit found a graph digest mismatch")
    if not strategy.get("compilation_digest"):
        raise OrchestratorError("resume audit found no frozen strategy compilation")
    return {
        "schema_version": 6,
        "operation": "resume",
        "run_root": str(run_root),
        "run_id": run["run_id"],
        "strategy_mode": strategy["strategy_mode"],
        "strategy_id": strategy["strategy_id"],
        "strategy_version": strategy["strategy_version"],
        "compilation_digest": strategy["compilation_digest"],
        "graph_revision": graph.graph_revision,
        "graph_digest": graph.graph_digest,
        "audit": {"trusted": True, "frozen_strategy": True, "graph_coherent": True},
    }


def initialize_compiled_campaign(
    args: argparse.Namespace,
    authority_scope_factory: Callable[[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    from graph_v6 import GraphState, add_edge_to_graph, add_job_to_graph, compute_graph_digest

    if args.mode not in MODE_ALIASES:
        raise OrchestratorError(f"unsupported strategy mode {args.mode!r}")
    mode = MODE_ALIASES[args.mode]
    if not args.goal or args.request_file is None:
        raise OrchestratorError("--goal and --request-file are required for campaign initialization")
    request_file = Path(args.request_file)
    if not request_file.exists():
        raise OrchestratorError(f"request file not found: {request_file}")
    run_id = args.run_id or chronological_run_id(args.goal, args.name)
    run_root = Path(args.state_root) / run_id
    if run_root.exists() and any(run_root.iterdir()):
        raise OrchestratorError(f"run already exists: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(args.workspace)
    registry, definition, contexts, config = _resolve_configuration(args)
    entry_inputs = _entry_artifact_names(args.entry_artifact)
    _require_mode_entry(mode, entry_inputs, args.review_target)
    compiled = StrategyCompiler(registry).compile_mode(
        CompilationMode(mode),
        definition.strategy_id,
        definition.version,
        args.goal,
        run_id,
        limits=config.get("limits"),
        custom_phases=config.get("custom_phases"),
        context_modules=contexts,
        entry_inputs=entry_inputs,
    )
    now = utc_now()
    campaign_id = stable_id("CAMP", run_id).upper()
    root = compiled.graph.initial_jobs[0]
    snapshot = {**compiled.envelope.to_dict(), "compilation_digest": compiled.compilation_digest}
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "envelope_id": compiled.envelope.envelope_id,
        "campaign_id": campaign_id,
        "goal": args.goal,
        "strategy": definition.strategy_id,
        "version": definition.version,
        "authority_id": root["authority_id"],
        "limits": compiled.envelope.limits,
        "created_at": now,
        **{key: snapshot[key] for key in (
            "strategy_mode", "strategy_digest", "compilation_digest", "phase_sequence",
            "entry_contract", "exit_contract", "context_snapshots", "safety_invariants", "mutating",
            "phase_configurations",
        )},
        "repository_target": str(workspace),
        "branch_policy": {
            "required": compiled.envelope.mutating,
            "branch": f"campaign/{campaign_id.lower()}",
            "baseline_commit": "reported_by_branch_init_worker",
        },
        "publication_policy": {
            "pull_request": False,
            "merge": False,
            "release": False,
            "deployment": False,
            "destructive_migration": False,
        },
    }
    from orchestrator_core import validate_record

    validate_record("campaign-envelope", envelope)
    graph = GraphState(envelope=envelope, status="open", limits=compiled.envelope.limits)
    root_record = {
        "schema_version": SCHEMA_VERSION,
        "job_id": root["job_id"],
        "title": "Trusted campaign root",
        "prompt_path": "ROOT",
        "role": "control_root",
        "purpose_key": "campaign-root",
        "graph_generation": 1,
        "expansion_origin": "ROOT",
        "authority_id": root["authority_id"],
        "created_at": now,
    }
    add_job_to_graph(graph, root_record)
    graph._jobs[root["job_id"]].update({
        "status": "completed",
        "revision": 0,
        "execution_status": "success",
        "completion_status": "success",
        "report_accepted": True,
    })
    graph._authorities[root["authority_id"]] = {
        "schema_version": SCHEMA_VERSION,
        "authority_id": root["authority_id"],
        "campaign_id": campaign_id,
        "job_identity": root["job_id"],
        "role": "control_root",
        "depth": 0,
        "status": "active",
        "scope": {
            "allowed_expansion_kinds": [],
            "allowed_child_roles": [],
            "owned_batch_ids": [],
            "side_effects": ["none"],
            "max_child_jobs": 0,
            "max_child_depth": 0,
            "limits": {},
        },
        "granted_at": now,
        "expires_at": "9999-12-31T23:59:59Z",
    }
    prompt_by_phase = {prompt.phase_id: prompt.prompt_text for prompt in compiled.prompts}
    for job in compiled.graph.initial_jobs[1:]:
        job_id = job["job_id"]
        prompt_path = f"jobs/{job_id}/prompt.md"
        definition_record = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "title": job["phase_id"].replace("_", " ").title(),
            "prompt_path": prompt_path,
            "role": job["role"],
            "purpose_key": job["purpose_key"],
            "graph_generation": 1,
            "expansion_origin": root["job_id"],
            "authority_id": job["authority_id"],
            "created_at": now,
        }
        add_job_to_graph(graph, definition_record)
        graph._jobs[job_id].update({"status": "pending", "revision": 0, "cycle_id": ""})
        scope = authority_scope_factory(job["role"], graph)
        if job["read_only"]:
            scope["side_effects"] = ["none"]
        graph._authorities[job["authority_id"]] = {
            "schema_version": SCHEMA_VERSION,
            "authority_id": job["authority_id"],
            "campaign_id": campaign_id,
            "job_identity": job_id,
            "role": job["role"],
            "depth": 1,
            "parent_authority_id": root["authority_id"],
            "status": "active",
            "scope": scope,
            "granted_at": now,
            "expires_at": "9999-12-31T23:59:59Z",
        }
        job_dir = run_root / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        write_json(job_dir / "definition.json", definition_record)
        write_json(job_dir / "job.json", {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "role": job["role"],
            "purpose_key": job["purpose_key"],
            "status": "pending",
            "revision": 0,
            "created_at": now,
        })
        (job_dir / "prompt.md").write_text(prompt_by_phase[job["phase_id"]], encoding="utf-8")
    for edge in compiled.graph.initial_edges:
        add_edge_to_graph(graph, {
            "schema_version": SCHEMA_VERSION,
            **edge,
            "edge_type": "success",
            "graph_revision": 1,
            "created_at": now,
        })
    goal_judges = [job["job_id"] for job in compiled.graph.initial_jobs if job["role"] == "goal_judge"]
    graph.current_goal_judge_id = goal_judges[-1] if goal_judges else None
    graph.graph_digest = compute_graph_digest(graph)
    graph_path = run_root / "graph" / "graph.json"
    graph_path.parent.mkdir(exist_ok=True)
    graph.save(graph_path)
    job_ids = [job["job_id"] for job in compiled.graph.initial_jobs]
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "goal": args.goal,
        "protocol_revision": V6_REVISION,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "job_ids": job_ids,
        "graph_revision": 1,
        "graph_digest": graph.graph_digest,
        "campaign_envelope_id": compiled.envelope.envelope_id,
    }
    adapter = (
        {"adapter_id": "deterministic-test", "adapter_secret": "test-secret"}
        if args.test_harness else {}
    )
    setup = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "request_path": str(request_file),
        "workspace": str(workspace),
        "execution_mode": "hybrid",
        "jobs": [{"job_id": job_id, "title": root.get("title", job_id), "prompt_path": job_id} for job_id in job_ids],
        "graph_revision": 1,
        "graph_generation_id": root["graph_generation_id"] if "graph_generation_id" in root else stable_id("GEN", run_id, "1").upper(),
        "campaign_envelope_id": compiled.envelope.envelope_id,
        "adapter_binding": adapter,
        "created_at": now,
    }
    validate_record("run", run)
    validate_record("setup", setup)
    write_json(run_root / "run.json", run)
    write_json(run_root / "setup.json", setup)
    write_json(run_root / "campaign-envelope.json", envelope)
    write_json(run_root / "strategy.json", snapshot)
    return {
        "run_root": str(run_root),
        "run_id": run_id,
        "goal": args.goal,
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "root_job_id": root["job_id"],
        "graph_digest": graph.graph_digest,
        "strategy_mode": mode,
        "strategy_id": definition.strategy_id,
        "strategy_version": definition.version,
        "compilation_digest": compiled.compilation_digest,
        "job_ids": job_ids,
        "adapter_binding": adapter,
    }
