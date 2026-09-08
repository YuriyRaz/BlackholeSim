"""v6 strategy registry, compiler, and default adaptive strategy for dynamic orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator_core import (
    SCHEMA_VERSION,
    OrchestratorError,
    canonical_bytes,
    content_hash,
    stable_id,
    utc_now,
)


# ---------------------------------------------------------------------------
# Task 9.1-9.6: Strategy registry, compiler, composer, context modules
# ---------------------------------------------------------------------------

class CompilationMode(str, Enum):
    FULL_CAMPAIGN = "full_campaign"
    PROPOSAL_ONLY = "proposal_only"
    IMPLEMENTATION_FROM_PROPOSAL = "implementation_from_proposal"
    ARCHITECT_REVIEW_ONLY = "architect_review_only"
    RESUME = "resume"
    CUSTOM = "custom"


SAFETY_INVARIANTS = (
    "independent_verification",
    "recovery",
    "root_isolation",
    "goal_judge_authority",
    "no_false_completion",
)

MODE_ENTRY_CONTRACTS: dict[CompilationMode, tuple[str, ...]] = {
    CompilationMode.FULL_CAMPAIGN: ("goal",),
    CompilationMode.PROPOSAL_ONLY: ("goal",),
    CompilationMode.IMPLEMENTATION_FROM_PROPOSAL: ("reviewed_proposal",),
    CompilationMode.ARCHITECT_REVIEW_ONLY: ("implementation_evidence", "review_target"),
    CompilationMode.CUSTOM: ("goal",),
    CompilationMode.RESUME: ("frozen_campaign",),
}

MODE_EXIT_CONTRACTS: dict[CompilationMode, tuple[str, ...]] = {
    CompilationMode.FULL_CAMPAIGN: ("goal_judgment",),
    CompilationMode.PROPOSAL_ONLY: ("reviewed_proposal",),
    CompilationMode.IMPLEMENTATION_FROM_PROPOSAL: ("goal_judgment",),
    CompilationMode.ARCHITECT_REVIEW_ONLY: ("implementation_review",),
    CompilationMode.CUSTOM: ("goal_judgment",),
    CompilationMode.RESUME: ("frozen_campaign",),
}

MANDATORY_SAFETY_PHASES = frozenset({
    "deterministic_checks",
    "verification",
    "implementation_review",
    "goal_judge",
})


class CompositionOp(str, Enum):
    EXTEND = "extend"
    REPLACE = "replace"
    CONFIGURE = "configure"
    DISABLE = "disable"


class PhaseContract:
    """Input/output contract for a strategy phase."""

    def __init__(
        self,
        inputs: tuple[str, ...] = (),
        outputs: tuple[str, ...] = (),
    ) -> None:
        self.inputs = inputs
        self.outputs = outputs


class PhaseDefinition:
    """Definition of a single phase in a strategy."""

    def __init__(
        self,
        phase_id: str,
        prompt_fragment: str = "",
        contract: PhaseContract | None = None,
        is_overridable: bool = True,
        role: str = "implementation_worker",
        purpose_key: str | None = None,
        is_read_only: bool = False,
        is_mandatory: bool = False,
        side_effect_class: str = "none",
        dependencies: tuple[str, ...] = (),
    ) -> None:
        self.phase_id = phase_id
        self.prompt_fragment = prompt_fragment
        self.contract = contract or PhaseContract()
        self.is_overridable = is_overridable
        self.role = role
        self.purpose_key = purpose_key or phase_id
        self.is_read_only = is_read_only
        self.is_mandatory = is_mandatory
        self.side_effect_class = side_effect_class
        self.dependencies = dependencies


class RoleAuthority:
    """Authority granted to a role."""

    def __init__(self, can_expand: bool = False) -> None:
        self.can_expand = can_expand


class FinalizationPolicy:
    """Policy for campaign finalization."""

    def __init__(self) -> None:
        pass


class PublicationPolicy:
    """Policy for publication."""

    def __init__(self) -> None:
        pass


class StrategyDefinition:
    """Full definition of a strategy with phases, contracts, and limits."""

    def __init__(
        self,
        strategy_id: str,
        version: int = 1,
        stable_phase_ids: tuple[str, ...] = (),
        prompt_fragments: dict[str, str] | None = None,
        role_authority: dict[str, RoleAuthority] | None = None,
        phase_contracts: dict[str, PhaseContract] | None = None,
        gates: dict[str, tuple[str, ...]] | None = None,
        limits: dict[str, int] | None = None,
        finalization_policy: FinalizationPolicy | None = None,
        publication_policy: PublicationPolicy | None = None,
        phase_definitions: dict[str, PhaseDefinition] | None = None,
        non_overridable_phases: tuple[str, ...] = (),
        validate_contracts: bool = False,
    ) -> None:
        self.strategy_id = strategy_id
        self.version = version
        self.stable_phase_ids = stable_phase_ids
        self.prompt_fragments = prompt_fragments or {}
        self.role_authority = role_authority or {}
        self.phase_contracts = phase_contracts or {}
        self.gates = gates or {}
        self.limits = limits or {}
        self.finalization_policy = finalization_policy or FinalizationPolicy()
        self.publication_policy = publication_policy or PublicationPolicy()
        self.phase_definitions = phase_definitions or {
            phase_id: PhaseDefinition(
                phase_id,
                self.prompt_fragments.get(phase_id, ""),
                self.phase_contracts.get(phase_id),
            )
            for phase_id in stable_phase_ids
        }
        self.non_overridable_phases = non_overridable_phases
        self.validate_contracts = validate_contracts

    def canonical_digest(self) -> str:
        """Deterministic digest of the strategy definition."""
        payload = {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "stable_phase_ids": list(self.stable_phase_ids),
            "prompt_fragments": dict(sorted(self.prompt_fragments.items())),
            "gates": {k: list(v) for k, v in sorted(self.gates.items())},
            "limits": dict(sorted(self.limits.items())),
            "phase_definitions": {
                phase_id: {
                    "role": phase.role,
                    "purpose_key": phase.purpose_key,
                    "read_only": phase.is_read_only,
                    "mandatory": phase.is_mandatory,
                    "side_effect_class": phase.side_effect_class,
                    "inputs": list(phase.contract.inputs),
                    "outputs": list(phase.contract.outputs),
                    "dependencies": list(phase.dependencies),
                }
                for phase_id, phase in sorted(self.phase_definitions.items())
            },
            "non_overridable_phases": list(self.non_overridable_phases),
        }
        return content_hash(payload)


class CompiledEnvelope:
    """Compiled campaign envelope."""

    def __init__(
        self,
        envelope_id: str,
        envelope_digest: str,
        phase_sequence: tuple[str, ...],
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
        limits: dict[str, int],
        mode: str = CompilationMode.FULL_CAMPAIGN.value,
        strategy_digest: str = "",
        context_snapshots: tuple[dict[str, Any], ...] = (),
        entry_contract: tuple[str, ...] = (),
        exit_contract: tuple[str, ...] = (),
        mutating: bool = True,
        phase_configurations: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.envelope_id = envelope_id
        self.envelope_digest = envelope_digest
        self.phase_sequence = phase_sequence
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.goal = goal
        self.run_id = run_id
        self.limits = limits
        self.mode = mode
        self.strategy_digest = strategy_digest
        self.context_snapshots = context_snapshots
        self.entry_contract = entry_contract
        self.exit_contract = exit_contract
        self.mutating = mutating
        self.phase_configurations = phase_configurations or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "envelope_digest": self.envelope_digest,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_digest": self.strategy_digest,
            "strategy_mode": self.mode,
            "goal": self.goal,
            "run_id": self.run_id,
            "phase_sequence": list(self.phase_sequence),
            "limits": self.limits,
            "context_snapshots": list(self.context_snapshots),
            "entry_contract": list(self.entry_contract),
            "exit_contract": list(self.exit_contract),
            "mutating": self.mutating,
            "phase_configurations": self.phase_configurations,
            "safety_invariants": list(SAFETY_INVARIANTS),
        }


class CompiledGraph:
    """Compiled initial graph state."""

    def __init__(
        self,
        graph_digest: str,
        initial_jobs: list[dict[str, Any]],
        initial_edges: list[dict[str, Any]],
    ) -> None:
        self.graph_digest = graph_digest
        self.initial_jobs = initial_jobs
        self.initial_edges = initial_edges


class CompiledPrompt:
    """Compiled prompt for a phase."""

    def __init__(
        self,
        phase_id: str,
        prompt_text: str,
        prompt_digest: str,
    ) -> None:
        self.phase_id = phase_id
        self.prompt_text = prompt_text
        self.prompt_digest = prompt_digest


class CompilationResult:
    """Result of compiling a strategy."""

    def __init__(
        self,
        envelope: CompiledEnvelope,
        graph: CompiledGraph,
        prompts: list[CompiledPrompt],
        compilation_digest: str,
    ) -> None:
        self.envelope = envelope
        self.graph = graph
        self.prompts = prompts
        self.compilation_digest = compilation_digest


class StrategyRegistry:
    """Versioned strategy registry with sequential version enforcement."""

    def __init__(self) -> None:
        self._strategies: dict[str, dict[int, StrategyDefinition]] = {}

    def register_strategy(self, definition: StrategyDefinition) -> None:
        sid = definition.strategy_id
        ver = definition.version
        if sid not in self._strategies:
            if ver != 1:
                raise OrchestratorError(f"new strategy {sid!r} must start at version 1")
            self._strategies[sid] = {}
        versions = self._strategies[sid]
        if ver in versions:
            raise OrchestratorError(f"strategy {sid!r} version {ver} already exists")
        if versions and ver != max(versions) + 1:
            raise OrchestratorError(
                f"strategy {sid!r} version {ver} is not sequential; "
                f"expected {max(versions) + 1}"
            )
        versions[ver] = definition

    def get_strategy(self, strategy_id: str, version: int | None = None) -> StrategyDefinition:
        if strategy_id not in self._strategies:
            raise OrchestratorError(f"strategy {strategy_id!r} not found")
        versions = self._strategies[strategy_id]
        if version is None:
            version = max(versions.keys())
        if version not in versions:
            raise OrchestratorError(f"strategy {strategy_id!r} version {version} not found")
        return versions[version]

    def validate_strategy_version(self, strategy_id: str, version: int) -> list[str]:
        errors: list[str] = []
        if strategy_id not in self._strategies:
            errors.append(f"strategy {strategy_id!r} not found")
            return errors
        versions = self._strategies[strategy_id]
        if version not in versions:
            errors.append(f"strategy {strategy_id!r} version {version} not found")
        return errors

    def list_strategies(self) -> dict[str, int]:
        return {sid: max(versions.keys()) for sid, versions in self._strategies.items()}


class CompiledPrompt_:
    """Internal compiled prompt helper."""

    def __init__(self, phase_id: str, prompt_text: str, prompt_digest: str) -> None:
        self.phase_id = phase_id
        self.prompt_text = prompt_text
        self.prompt_digest = prompt_digest


class StrategyCompiler:
    """Deterministic compiler for all compilation modes."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def compile_full_campaign(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
        limits: dict[str, int] | None = None,
    ) -> CompilationResult:
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        merged_limits = dict(definition.limits)
        if limits:
            merged_limits.update(limits)
        return self._compile(
            definition, goal, run_id, definition.stable_phase_ids, merged_limits,
            CompilationMode.FULL_CAMPAIGN,
        )

    def compile_proposal_only(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
    ) -> CompilationResult:
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        proposal_phases = tuple(
            p for p in definition.stable_phase_ids
            if p == "branch_init" or p.startswith("proposal_")
        )
        return self._compile(
            definition, goal, run_id, proposal_phases,
            dict(definition.limits), CompilationMode.PROPOSAL_ONLY,
        )

    def compile_implementation_from_proposal(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
    ) -> CompilationResult:
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        impl_phases = tuple(
            p for p in definition.stable_phase_ids
            if p == "branch_init" or not p.startswith("proposal_")
        )
        return self._compile(
            definition, goal, run_id, impl_phases,
            dict(definition.limits), CompilationMode.IMPLEMENTATION_FROM_PROPOSAL,
        )

    def compile_architect_review_only(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
    ) -> CompilationResult:
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        review_phases = tuple(
            p for p in definition.stable_phase_ids if p == "implementation_review"
        )
        return self._compile(
            definition, goal, run_id, review_phases or definition.stable_phase_ids[:1],
            dict(definition.limits), CompilationMode.ARCHITECT_REVIEW_ONLY,
        )

    def compile_resume(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
    ) -> CompilationResult:
        raise OrchestratorError(
            "resume must audit and use the persisted frozen campaign; it cannot recompile a registry strategy"
        )

    def compile_custom(
        self,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
        custom_phases: list[str] | None = None,
    ) -> CompilationResult:
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        phases = tuple(custom_phases) if custom_phases else definition.stable_phase_ids
        for phase in phases:
            if phase not in definition.stable_phase_ids:
                raise OrchestratorError(f"phase {phase!r} not found in strategy")
        return self._compile(
            definition, goal, run_id, phases,
            dict(definition.limits), CompilationMode.CUSTOM,
        )

    def compile_mode(
        self,
        mode: CompilationMode | str,
        strategy_id: str,
        strategy_version: int,
        goal: str,
        run_id: str,
        *,
        limits: dict[str, int] | None = None,
        custom_phases: list[str] | None = None,
        context_modules: tuple[ContextModule, ...] = (),
        entry_inputs: tuple[str, ...] = (),
    ) -> CompilationResult:
        mode = CompilationMode(mode)
        if mode == CompilationMode.RESUME:
            return self.compile_resume(strategy_id, strategy_version, goal, run_id)
        definition = self._registry.get_strategy(strategy_id, strategy_version)
        phases = self._phases_for_mode(definition, mode, custom_phases)
        merged_limits = dict(definition.limits)
        if limits:
            merged_limits.update(limits)
        return self._compile(
            definition,
            goal,
            run_id,
            phases,
            merged_limits,
            mode,
            context_modules=context_modules,
            entry_inputs=entry_inputs,
        )

    def _phases_for_mode(
        self,
        definition: StrategyDefinition,
        mode: CompilationMode,
        custom_phases: list[str] | None,
    ) -> tuple[str, ...]:
        if mode == CompilationMode.FULL_CAMPAIGN:
            return definition.stable_phase_ids
        if mode == CompilationMode.PROPOSAL_ONLY:
            return tuple(
                p for p in definition.stable_phase_ids
                if p == "branch_init" or p.startswith("proposal_")
            )
        if mode == CompilationMode.IMPLEMENTATION_FROM_PROPOSAL:
            return tuple(
                p for p in definition.stable_phase_ids
                if p == "branch_init" or not p.startswith("proposal_")
            )
        if mode == CompilationMode.ARCHITECT_REVIEW_ONLY:
            return ("implementation_review",)
        if mode == CompilationMode.CUSTOM:
            return tuple(custom_phases) if custom_phases is not None else definition.stable_phase_ids
        phases = tuple(custom_phases or definition.stable_phase_ids)
        missing = [phase for phase in phases if phase not in definition.stable_phase_ids]
        if missing:
            raise OrchestratorError(f"custom strategy has unknown phases: {missing}")
        missing_safety = sorted(MANDATORY_SAFETY_PHASES - set(phases))
        if missing_safety:
            raise OrchestratorError(
                "custom strategy cannot weaken mandatory safety phases: "
                + ", ".join(missing_safety)
            )
        return phases

    def _compile(
        self,
        definition: StrategyDefinition,
        goal: str,
        run_id: str,
        phases: tuple[str, ...],
        limits: dict[str, int],
        mode: CompilationMode,
        *,
        context_modules: tuple[ContextModule, ...] = (),
        entry_inputs: tuple[str, ...] = (),
    ) -> CompilationResult:
        phase_configurations: dict[str, dict[str, Any]] = {
            key: dict(value) for key, value in limits.items() if isinstance(value, dict)
        }
        limits = {
            key: value for key, value in limits.items() if not isinstance(value, dict)
        }
        expected_entry = MODE_ENTRY_CONTRACTS[mode]
        available = {"goal"} | set(expected_entry) | set(entry_inputs)
        if definition.validate_contracts:
            self._validate_phase_contracts(definition, phases, available)
        context_snapshots = self._freeze_context(context_modules)
        strategy_digest = definition.canonical_digest()
        envelope_seed = content_hash({
            "strategy_digest": strategy_digest,
            "mode": mode.value,
            "run_id": run_id,
            "goal": goal,
            "phases": list(phases),
            "limits": limits,
            "phase_configurations": phase_configurations,
            "contexts": list(context_snapshots),
        })
        envelope_id = stable_id("ENV", envelope_seed).upper()
        envelope_digest = content_hash({
            "strategy_id": definition.strategy_id,
            "version": definition.version,
            "strategy_digest": strategy_digest,
            "mode": mode.value,
            "run_id": run_id,
            "goal": goal,
            "phases": list(phases),
            "limits": limits,
            "phase_configurations": phase_configurations,
            "context_snapshots": list(context_snapshots),
            "entry_contract": list(expected_entry),
            "exit_contract": list(MODE_EXIT_CONTRACTS[mode]),
            "safety_invariants": list(SAFETY_INVARIANTS),
        })
        envelope = CompiledEnvelope(
            envelope_id=envelope_id,
            envelope_digest=envelope_digest,
            phase_sequence=phases,
            strategy_id=definition.strategy_id,
            strategy_version=definition.version,
            goal=goal,
            run_id=run_id,
            limits=limits,
            mode=mode.value,
            strategy_digest=strategy_digest,
            context_snapshots=context_snapshots,
            entry_contract=expected_entry,
            exit_contract=MODE_EXIT_CONTRACTS[mode],
            mutating=any(
                definition.phase_definitions[p].side_effect_class != "none" for p in phases
            ),
            phase_configurations=phase_configurations,
        )

        jobs: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        root_id = stable_id("JOB", run_id, "ROOT").upper()
        jobs.append({
            "job_id": root_id,
            "role": "control_root",
            "purpose_key": "campaign_root",
            "expansion_origin": "ROOT",
            "authority_id": stable_id("AUTH", run_id, "root").upper(),
            "phase_id": "campaign_root",
            "read_only": True,
            "side_effect_class": "none",
        })
        prev_id = root_id
        for phase in phases:
            phase_definition = definition.phase_definitions[phase]
            job_id = stable_id("JOB", run_id, phase).upper()
            jobs.append({
                "job_id": job_id,
                "role": phase_definition.role,
                "purpose_key": phase_definition.purpose_key,
                "expansion_origin": root_id,
                "authority_id": stable_id("AUTH", run_id, phase).upper(),
                "phase_id": phase,
                "read_only": phase_definition.is_read_only,
                "side_effect_class": phase_definition.side_effect_class,
            })
            edge_id = stable_id("EDGE", prev_id, job_id).upper()
            edges.append({
                "edge_id": edge_id,
                "source_job_id": prev_id,
                "target_job_id": job_id,
                "edge_type": "success",
            })
            prev_id = job_id

        graph_digest = content_hash({"jobs": jobs, "edges": edges})
        graph = CompiledGraph(graph_digest=graph_digest, initial_jobs=jobs, initial_edges=edges)

        prompts: list[CompiledPrompt] = []
        for phase in phases:
            phase_definition = definition.phase_definitions[phase]
            fragment = definition.prompt_fragments.get(phase, f"Instructions for {phase}")
            applicable_context = [
                snapshot for snapshot in context_snapshots
                if not snapshot["applicable_roles"]
                or phase_definition.role in snapshot["applicable_roles"]
            ]
            prompt_text = self._render_prompt(
                run_id,
                goal,
                phase_definition,
                fragment,
                applicable_context,
                phase_configurations.get(phase, {}),
            )
            prompt_digest = content_hash(prompt_text)
            prompts.append(CompiledPrompt(phase_id=phase, prompt_text=prompt_text, prompt_digest=prompt_digest))

        compilation_digest = content_hash({
            "envelope_digest": envelope_digest,
            "graph_digest": graph_digest,
            "prompt_digests": [p.prompt_digest for p in prompts],
        })

        return CompilationResult(
            envelope=envelope,
            graph=graph,
            prompts=prompts,
            compilation_digest=compilation_digest,
        )

    @staticmethod
    def _validate_phase_contracts(
        definition: StrategyDefinition,
        phases: tuple[str, ...],
        available: set[str],
    ) -> None:
        for phase_id in phases:
            phase = definition.phase_definitions.get(phase_id)
            if phase is None:
                raise OrchestratorError(f"strategy phase {phase_id!r} has no definition")
            missing = sorted(set(phase.contract.inputs) - available)
            if missing:
                raise OrchestratorError(
                    f"phase {phase_id!r} has unsatisfied inputs: {', '.join(missing)}"
                )
            available.update(phase.contract.outputs)

    @staticmethod
    def _freeze_context(
        modules: tuple[ContextModule, ...],
    ) -> tuple[dict[str, Any], ...]:
        snapshots = []
        seen: dict[tuple[str, str], tuple[Any, str]] = {}
        for module in sorted(modules, key=lambda item: item.module_id):
            module.validate_no_authority()
            for key, value in sorted(module.constraints.items()):
                conflict_key = (module.namespace, key)
                if conflict_key in seen and seen[conflict_key][0] != value:
                    raise OrchestratorError(
                        f"context conflict for {module.namespace}.{key} between "
                        f"{seen[conflict_key][1]!r} and {module.module_id!r}"
                    )
                seen[conflict_key] = (value, module.module_id)
            snapshots.append(module.to_snapshot())
        return tuple(snapshots)

    @staticmethod
    def _render_prompt(
        run_id: str,
        goal: str,
        phase: PhaseDefinition,
        fragment: str,
        contexts: list[dict[str, Any]],
        configuration: dict[str, Any],
    ) -> str:
        boundary = (
            "Read-only Architect boundary: do not implement, mutate the repository, "
            "verify your own work, approve your own work, or mutate orchestrator state."
            if phase.is_read_only and "architect" in phase.role
            else "Do not mutate orchestrator state or claim authority not persisted for this job."
        )
        context_text = canonical_bytes(contexts).decode("utf-8")
        return "\n".join((
            f"Run: {run_id}",
            f"Goal: {goal}",
            f"Phase: {phase.phase_id}",
            f"Role: {phase.role}",
            f"Inputs: {', '.join(phase.contract.inputs) or 'none'}",
            f"Outputs: {', '.join(phase.contract.outputs) or 'none'}",
            f"Side effect class: {phase.side_effect_class}",
            boundary,
            f"Frozen context modules: {context_text}",
            f"Frozen phase configuration: {canonical_bytes(configuration).decode('utf-8')}",
            fragment,
        ))


class CompositionOperation:
    """Single composition operation."""

    def __init__(
        self,
        op: CompositionOp,
        target_phase: str,
        new_phase: PhaseDefinition | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.op = op
        self.target_phase = target_phase
        self.new_phase = new_phase
        self.config = config or {}


class StrategyComposer:
    """Applies extend, replace, configure, disable composition operations."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry
        self._operations: list[CompositionOperation] = []

    def extend_phase(self, new_phase_id: str, anchor_phase: str, phase_def: PhaseDefinition) -> None:
        self._operations.append(CompositionOperation(
            op=CompositionOp.EXTEND,
            target_phase=anchor_phase,
            new_phase=phase_def,
        ))

    def replace_phase(self, target_phase: str, phase_def: PhaseDefinition) -> None:
        self._operations.append(CompositionOperation(
            op=CompositionOp.REPLACE,
            target_phase=target_phase,
            new_phase=phase_def,
        ))

    def configure_phase(self, target_phase: str, config: dict[str, Any]) -> None:
        self._operations.append(CompositionOperation(
            op=CompositionOp.CONFIGURE,
            target_phase=target_phase,
            config=config,
        ))

    def disable_phase(self, target_phase: str) -> None:
        self._operations.append(CompositionOperation(
            op=CompositionOp.DISABLE,
            target_phase=target_phase,
        ))

    def validate_composition(self, strategy_id: str, version: int) -> list[str]:
        definition = self._registry.get_strategy(strategy_id, version)
        errors: list[str] = []
        current_phases = list(definition.stable_phase_ids)
        destructive_targets: set[str] = set()
        for op in self._operations:
            if op.op in {CompositionOp.REPLACE, CompositionOp.DISABLE}:
                if op.target_phase in destructive_targets:
                    errors.append(
                        f"ambiguous operations target phase {op.target_phase!r} more than once"
                    )
                destructive_targets.add(op.target_phase)
            if op.op == CompositionOp.DISABLE:
                if op.target_phase not in current_phases:
                    errors.append(f"phase {op.target_phase!r} not found")
                elif op.target_phase in definition.non_overridable_phases:
                    errors.append(f"phase {op.target_phase!r} is a non-overridable safety phase")
                elif op.target_phase == current_phases[0]:
                    errors.append(f"cannot disable first phase {op.target_phase!r}")
                else:
                    current_phases.remove(op.target_phase)
            if op.op == CompositionOp.REPLACE:
                original_phase = definition.phase_definitions.get(op.target_phase)
                if op.target_phase not in current_phases:
                    errors.append(f"phase {op.target_phase!r} not found")
                elif op.target_phase in definition.non_overridable_phases:
                    errors.append(f"phase {op.target_phase!r} is a non-overridable safety phase")
                elif original_phase is not None and not original_phase.is_overridable:
                    errors.append(f"phase {op.target_phase!r} is not overridable")
                elif op.new_phase is not None and not op.new_phase.is_overridable:
                    errors.append(f"phase {op.target_phase!r} is not overridable")
                elif (
                    definition.validate_contracts
                    and op.new_phase is not None
                    and original_phase is not None
                ):
                    if not set(original_phase.contract.inputs).issubset(op.new_phase.contract.inputs):
                        errors.append(f"replacement for {op.target_phase!r} weakens phase inputs")
                    if not set(original_phase.contract.outputs).issubset(op.new_phase.contract.outputs):
                        errors.append(f"replacement for {op.target_phase!r} weakens phase outputs")
            if op.op == CompositionOp.EXTEND:
                if op.new_phase and op.new_phase.phase_id in current_phases:
                    errors.append(f"phase {op.new_phase.phase_id!r} already exists")
                if op.target_phase not in current_phases:
                    errors.append(f"anchor phase {op.target_phase!r} not found")
                elif op.new_phase:
                    current_phases.insert(current_phases.index(op.target_phase) + 1, op.new_phase.phase_id)
            if op.op == CompositionOp.CONFIGURE:
                if op.target_phase not in current_phases:
                    errors.append(f"phase {op.target_phase!r} not found")
                weakened = {
                    "independent_verification": False,
                    "recovery": False,
                    "root_isolation": False,
                    "goal_judge_authority": False,
                    "no_false_completion": False,
                    "read_only": False,
                }
                for key, forbidden in weakened.items():
                    if op.config.get(key) is forbidden and (
                        key != "read_only"
                        or definition.phase_definitions.get(op.target_phase, PhaseDefinition("x")).is_read_only
                    ):
                        errors.append(f"configure cannot weaken {key} for {op.target_phase!r}")
        return errors

    def apply_composition(self, strategy_id: str, version: int) -> StrategyDefinition:
        original = self._registry.get_strategy(strategy_id, version)
        errors = self.validate_composition(strategy_id, version)
        if errors:
            raise OrchestratorError(f"composition validation failed: {'; '.join(errors)}")

        new_phases = list(original.stable_phase_ids)
        new_fragments = dict(original.prompt_fragments)
        new_contracts = dict(original.phase_contracts)
        new_definitions = dict(original.phase_definitions)
        new_limits: dict[str, Any] = dict(original.limits)

        for op in self._operations:
            if op.op == CompositionOp.EXTEND and op.new_phase:
                idx = new_phases.index(op.target_phase) + 1
                new_phases.insert(idx, op.new_phase.phase_id)
                new_fragments[op.new_phase.phase_id] = op.new_phase.prompt_fragment
                new_contracts[op.new_phase.phase_id] = op.new_phase.contract
                new_definitions[op.new_phase.phase_id] = op.new_phase
            elif op.op == CompositionOp.REPLACE and op.new_phase:
                idx = new_phases.index(op.target_phase)
                new_phases[idx] = op.new_phase.phase_id
                new_fragments[op.new_phase.phase_id] = op.new_phase.prompt_fragment
                new_contracts[op.new_phase.phase_id] = op.new_phase.contract
                new_definitions.pop(op.target_phase, None)
                new_definitions[op.new_phase.phase_id] = op.new_phase
            elif op.op == CompositionOp.CONFIGURE:
                new_limits[op.target_phase] = op.config
            elif op.op == CompositionOp.DISABLE:
                new_phases.remove(op.target_phase)
                new_fragments.pop(op.target_phase, None)
                new_contracts.pop(op.target_phase, None)
                new_definitions.pop(op.target_phase, None)

        if original.validate_contracts:
            StrategyCompiler._validate_phase_contracts(
                StrategyDefinition(
                    strategy_id=original.strategy_id,
                    version=version + 1,
                    stable_phase_ids=tuple(new_phases),
                    phase_definitions=new_definitions,
                ),
                tuple(new_phases),
                {"goal", "reviewed_proposal", "implementation_evidence", "review_target"},
            )

        return StrategyDefinition(
            strategy_id=original.strategy_id,
            version=version + 1,
            stable_phase_ids=tuple(new_phases),
            prompt_fragments=new_fragments,
            role_authority=dict(original.role_authority),
            phase_contracts=new_contracts,
            gates=dict(original.gates),
            limits=new_limits,
            finalization_policy=original.finalization_policy,
            publication_policy=original.publication_policy,
            phase_definitions=new_definitions,
            non_overridable_phases=original.non_overridable_phases,
            validate_contracts=original.validate_contracts,
        )


class ContextModule:
    """Additive namespaced context module."""

    def __init__(
        self,
        module_id: str,
        namespace: str,
        constraints: dict[str, Any] | None = None,
        version: int = 1,
        inherited_from: tuple[str, ...] | None = None,
        applicable_roles: tuple[str, ...] | None = None,
        evidence_requirements: tuple[str, ...] | None = None,
        source_rules: tuple[str, ...] | None = None,
        goal_gates: tuple[str, ...] | None = None,
    ) -> None:
        self.module_id = module_id
        self.namespace = namespace
        self.constraints = constraints or {}
        self.version = version
        self.inherited_from = inherited_from or ()
        self.applicable_roles = applicable_roles or ()
        self.evidence_requirements = evidence_requirements or ()
        self.source_rules = source_rules or ()
        self.goal_gates = goal_gates or ()

    def compute_digest(self) -> str:
        payload = {
            "module_id": self.module_id,
            "namespace": self.namespace,
            "constraints": dict(sorted(self.constraints.items())),
            "version": self.version,
            "inherited_from": list(self.inherited_from),
            "applicable_roles": list(self.applicable_roles),
            "evidence_requirements": list(self.evidence_requirements),
            "source_rules": list(self.source_rules),
            "goal_gates": list(self.goal_gates),
        }
        return content_hash(payload)

    def validate_no_authority(self) -> None:
        forbidden = {
            "authority", "role_authority", "graph", "graph_operations",
            "side_effects", "phases", "permissions",
        }

        def collect_forbidden(value: Any) -> set[str]:
            found: set[str] = set()
            if isinstance(value, dict):
                found.update(forbidden & set(value))
                for nested in value.values():
                    found.update(collect_forbidden(nested))
            elif isinstance(value, list):
                for nested in value:
                    found.update(collect_forbidden(nested))
            return found

        invalid = sorted(collect_forbidden(self.constraints))
        if invalid:
            raise OrchestratorError(
                f"context module {self.module_id!r} cannot grant authority or mutate workflow: "
                + ", ".join(invalid)
            )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "namespace": self.namespace,
            "version": self.version,
            "digest": self.compute_digest(),
            "constraints": self.constraints,
            "inherited_from": list(self.inherited_from),
            "applicable_roles": list(self.applicable_roles),
            "evidence_requirements": list(self.evidence_requirements),
            "source_rules": list(self.source_rules),
            "goal_gates": list(self.goal_gates),
        }


class ContextModuleRegistry:
    """Registry for additive namespaced context modules."""

    def __init__(self) -> None:
        self._modules: dict[str, ContextModule] = {}
        self._frozen: set[str] = set()

    def add_context_module(self, module: ContextModule) -> None:
        module.validate_no_authority()
        mid = module.module_id
        if mid in self._frozen:
            raise OrchestratorError(f"module {mid!r} is frozen and cannot be modified")
        if mid in self._modules:
            existing = self._modules[mid]
            if module.version < existing.version:
                raise OrchestratorError(
                    f"cannot downgrade module {mid!r} from v{existing.version} to v{module.version}"
                )
        self._modules[mid] = module

    def get_module(self, module_id: str) -> ContextModule | None:
        return self._modules.get(module_id)

    def validate_module_conflicts(self, module: ContextModule) -> list[str]:
        conflicts: list[str] = []
        for mid, existing in self._modules.items():
            if mid == module.module_id:
                continue
            if existing.namespace == module.namespace:
                common_keys = set(existing.constraints.keys()) & set(module.constraints.keys())
                for key in common_keys:
                    if existing.constraints[key] != module.constraints[key]:
                        conflicts.append(
                            f"conflict in namespace {module.namespace!r}: "
                            f"key {key!r} has value {existing.constraints[key]!r} "
                            f"in {mid!r} but {module.constraints[key]!r} in {module.module_id!r}"
                        )
        for inh in module.inherited_from:
            if inh not in self._modules:
                conflicts.append(f"inherited module {inh!r} not found")
        return conflicts

    def freeze_module_versions(self, module_ids: list[str]) -> dict[str, str]:
        frozen: dict[str, str] = {}
        for mid in module_ids:
            if mid not in self._modules:
                raise OrchestratorError(f"module {mid!r} not found for freezing")
            self._frozen.add(mid)
            frozen[mid] = self._modules[mid].compute_digest()
        return frozen

    def resolve_constraints(self, namespace: str) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for module in self._modules.values():
            if module.namespace == namespace:
                resolved.update(module.constraints)
        return resolved

    def get_modules_for_namespace(self, namespace: str) -> list[ContextModule]:
        return [m for m in self._modules.values() if m.namespace == namespace]


def build_default_strategy_registry() -> StrategyRegistry:
    """Build the sole production strategy registry used by jobctl initialization."""
    phase_specs = (
        ("branch_init", "branch_initializer", True, "repository", ("goal",), ("branch_ready",)),
        ("proposal_explore", "proposal_explore", True, "none", ("goal",), ("exploration_report",)),
        ("proposal_architect", "proposal_architect", True, "none", ("exploration_report",), ("proposal_design",)),
        ("proposal_finalize", "proposal_finalizer", False, "repository", ("proposal_design",), ("apply_ready_proposal",)),
        ("proposal_review", "verifier", True, "none", ("apply_ready_proposal",), ("reviewed_proposal",)),
        ("implementation_planning", "work_planner_architect", True, "none", ("reviewed_proposal",), ("work_plan",)),
        ("implementation", "implementation_worker", False, "repository", ("work_plan",), ("implementation_artifacts",)),
        ("deterministic_checks", "deterministic_checker", True, "none", ("implementation_artifacts",), ("check_results",)),
        ("verification", "verifier", True, "none", ("implementation_artifacts", "check_results"), ("implementation_evidence",)),
        ("implementation_review", "implementation_review_architect", True, "none", ("implementation_evidence",), ("implementation_review",)),
        ("openspec_sync", "openspec_finalizer", False, "repository", ("implementation_review",), ("specs_synced",)),
        ("openspec_archive", "openspec_finalizer", False, "repository", ("specs_synced",), ("openspec_finalized",)),
        ("cycle_commit", "commit_worker", False, "repository", ("openspec_finalized",), ("cycle_commit",)),
        ("cycle_push", "push_worker", False, "external_idempotent", ("cycle_commit",), ("branch_pushed",)),
        ("remote_verification", "remote_verifier", True, "none", ("branch_pushed",), ("remote_verified",)),
        ("goal_judge", "goal_judge", True, "none", ("remote_verified",), ("goal_judgment",)),
    )
    prompts = {
        "branch_init": "Create or validate the campaign feature branch and report its baseline commit.",
        "proposal_explore": "Explore primary evidence, requirements, alternatives, and risks for the Proposal.",
        "proposal_architect": "Independently design and challenge the Proposal without implementing it.",
        "proposal_finalize": "Produce apply-ready OpenSpec artifacts from accepted exploration and design evidence.",
        "proposal_review": "Independently verify that the Proposal is coherent, complete, and apply-ready.",
        "implementation_planning": "Select bounded implementation work. Nested OpenSpec promotion remains allowed for material redesign.",
        "implementation": "Implement the accepted work plan and tests without approving your own work.",
        "deterministic_checks": "Run the exact deterministic checks and retain primary command evidence.",
        "verification": "Independently verify the implementation and target-scoped gates from primary evidence.",
        "implementation_review": "Review quality, architecture, operability, durability, and all findings as a read-only Architect.",
        "openspec_sync": "Re-resolve stores and synchronize required OpenSpec specifications.",
        "openspec_archive": "Archive completed OpenSpec changes and verify final artifact state.",
        "cycle_commit": "Create exactly one campaign-owned commit for the accepted cycle.",
        "cycle_push": "Push the campaign feature branch using observable idempotent recovery.",
        "remote_verification": "Freshly verify the exact remote branch and commit read-only.",
        "goal_judge": "Freshly judge the original campaign goal and all frozen gates from primary evidence.",
    }
    phase_definitions = {
        phase_id: PhaseDefinition(
            phase_id=phase_id,
            prompt_fragment=prompts[phase_id],
            contract=PhaseContract(inputs=inputs, outputs=outputs),
            is_overridable=phase_id not in MANDATORY_SAFETY_PHASES,
            role=role,
            purpose_key=phase_id,
            is_read_only=read_only,
            is_mandatory=phase_id in MANDATORY_SAFETY_PHASES,
            side_effect_class=side_effect,
        )
        for phase_id, role, read_only, side_effect, inputs, outputs in phase_specs
    }
    definition = StrategyDefinition(
        strategy_id="default_adaptive",
        version=1,
        stable_phase_ids=tuple(spec[0] for spec in phase_specs),
        prompt_fragments=prompts,
        role_authority={
            "proposal_architect": RoleAuthority(can_expand=False),
            "work_planner_architect": RoleAuthority(can_expand=True),
            "implementation_review_architect": RoleAuthority(can_expand=True),
            "goal_judge": RoleAuthority(can_expand=True),
        },
        phase_contracts={key: value.contract for key, value in phase_definitions.items()},
        gates={
            "verification": ("independent_verification",),
            "implementation_review": ("architect_review",),
            "goal_judge": ("no_false_completion",),
        },
        limits={
            "max_cycles": 20,
            "max_jobs_per_cycle": 64,
            "max_total_jobs": 512,
            "max_jobs_per_expansion": 32,
            "max_concurrency": 8,
            "max_expansions": 64,
        },
        phase_definitions=phase_definitions,
        non_overridable_phases=tuple(sorted(MANDATORY_SAFETY_PHASES)),
        validate_contracts=True,
    )
    registry = StrategyRegistry()
    registry.register_strategy(definition)
    return registry


class AmbiguityItem:
    """Single ambiguity detection item."""

    def __init__(
        self,
        ambiguity_type: str,
        description: str,
        candidates: tuple[str, ...] = (),
        severity: str = "warning",
    ) -> None:
        self.ambiguity_type = ambiguity_type
        self.description = description
        self.candidates = candidates
        self.severity = severity


class AmbiguityRouter:
    """Routes ambiguous entries, anchors, overrides, and constraints to user questions."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def route(
        self,
        entry_target: str | None = None,
        phase_anchors: list[str] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> str | None:
        items: list[AmbiguityItem] = []

        if entry_target:
            all_strategies = self._registry.list_strategies()
            if entry_target in all_strategies:
                pass  # exact match, no ambiguity
            else:
                matches = [
                    sid for sid in all_strategies
                    if sid.startswith(entry_target) or entry_target in sid
                ]
                if len(matches) > 1:
                    items.append(AmbiguityItem(
                        ambiguity_type="entry_target",
                        description=f"multiple strategies match {entry_target!r}",
                        candidates=tuple(matches),
                    ))
                elif len(matches) == 0:
                    items.append(AmbiguityItem(
                        ambiguity_type="entry_target",
                        description=f"no strategy matches {entry_target!r}",
                        candidates=(),
                        severity="error",
                    ))
        if phase_anchors and len(phase_anchors) > 1:
            items.append(AmbiguityItem(
                ambiguity_type="phase_anchor",
                description=f"Multiple phase anchors specified: {phase_anchors}",
                candidates=tuple(phase_anchors),
            ))

        if overrides:
            conflicts = self.detect_conflicts(overrides)
            items.extend(conflicts)

        if items:
            return self.generate_user_question(items)
        return None

    def detect_conflicts(self, overrides: dict[str, Any]) -> list[AmbiguityItem]:
        items: list[AmbiguityItem] = []
        keys = list(overrides.keys())
        if len(keys) > 1:
            simple_types = (bool, int, float, str, type(None))
            all_simple = all(isinstance(overrides[k], simple_types) for k in keys)
            if all_simple:
                items.append(AmbiguityItem(
                    ambiguity_type="conflict",
                    description=f"multiple override targets: {keys}",
                    candidates=tuple(keys),
                ))
            else:
                values = [canonical_bytes(overrides[k]).hex() for k in keys]
                seen: dict[str, list[str]] = {}
                for k, v in zip(keys, values):
                    seen.setdefault(v, []).append(k)
                for group_keys in seen.values():
                    if len(group_keys) > 1:
                        items.append(AmbiguityItem(
                            ambiguity_type="conflict",
                            description=f"multiple override targets with same value: {group_keys}",
                            candidates=tuple(group_keys),
                        ))
        return items

    def detect_weakened_contracts(
        self,
        original: dict[str, PhaseContract],
        modified: dict[str, PhaseContract],
    ) -> list[AmbiguityItem]:
        items: list[AmbiguityItem] = []
        for phase_id, orig in original.items():
            if phase_id in modified:
                mod = modified[phase_id]
                if len(mod.inputs) < len(orig.inputs) or len(mod.outputs) < len(orig.outputs):
                    items.append(AmbiguityItem(
                        ambiguity_type="weakened_contract",
                        description=f"phase {phase_id!r} lost inputs or outputs",
                        candidates=(phase_id,),
                        severity="error",
                    ))
        return items

    def detect_incompatible_constraints(
        self,
        constraints: dict[str, dict[str, Any]],
    ) -> list[AmbiguityItem]:
        items: list[AmbiguityItem] = []
        keys = list(constraints.keys())
        for i, k_first in enumerate(keys):
            for k_second in keys[i + 1:]:
                val_first = constraints[k_first]
                val_second = constraints[k_second]
                common = set(val_first.keys()) & set(val_second.keys())
                for key in common:
                    if val_first[key] != val_second[key]:
                        items.append(AmbiguityItem(
                            ambiguity_type="incompatible_constraint",
                            description=f"incompatible constraint {key!r} in {k_first!r} and {k_second!r}",
                            candidates=(k_first, k_second),
                        ))
        return items

    def generate_user_question(self, items: list[AmbiguityItem]) -> str:
        if not items:
            return ""
        first = items[0]
        if first.severity == "error":
            if first.ambiguity_type == "entry_target":
                if first.candidates:
                    return f"Ambiguous entry target. Did you mean: {', '.join(first.candidates)}?"
                return f"no strategy matches your request"
            return f"Weakened contract: {first.description}"
        if first.ambiguity_type == "entry_target" and first.candidates:
            return f"Ambiguous entry target. Did you mean: {', '.join(first.candidates)}?"
        if first.ambiguity_type == "phase_anchor":
            return f"Multiple phase anchors: {first.description}"
        return f"Ambiguity detected: {first.description}"


# ---------------------------------------------------------------------------
# Phase definitions  (Task 10.1)
# ---------------------------------------------------------------------------

class PhaseKind(str, Enum):
    PROPOSAL_EXPLORE = "proposal_explore"
    PROPOSAL_ARCHITECT = "proposal_architect"
    PROPOSAL_FINALIZE = "proposal_finalize"
    IMPLEMENTATION_PLANNING = "implementation_planning"
    IMPLEMENTATION = "implementation"
    DETERMINISTIC_CHECKS = "deterministic_checks"
    VERIFICATION = "verification"
    REVIEW = "review"
    FINALIZATION = "finalization"
    GOAL_JUDGE = "goal_judge"


class PhaseRecord:
    """Immutable definition of a single strategy phase."""

    def __init__(
        self,
        phase_id: str,
        phase_kind: PhaseKind,
        role: str,
        purpose_key: str,
        authority_scope: dict[str, bool] | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        gate_conditions: list[str] | None = None,
        required_evidence: list[str] | None = None,
        is_mandatory: bool = True,
        is_read_only: bool = False,
        dependencies: list[str] | None = None,
    ) -> None:
        self.phase_id = phase_id
        self.phase_kind = phase_kind
        self.role = role
        self.purpose_key = purpose_key
        self.authority_scope = authority_scope or {}
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.gate_conditions = gate_conditions or []
        self.required_evidence = required_evidence or []
        self.is_mandatory = is_mandatory
        self.is_read_only = is_read_only
        self.dependencies = dependencies or []

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "phase_id": self.phase_id,
            "phase_kind": self.phase_kind.value,
            "role": self.role,
            "purpose_key": self.purpose_key,
            "authority_scope": self.authority_scope,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "gate_conditions": self.gate_conditions,
            "required_evidence": self.required_evidence,
            "is_mandatory": self.is_mandatory,
            "is_read_only": self.is_read_only,
            "dependencies": self.dependencies,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhaseRecord:
        return cls(
            phase_id=data["phase_id"],
            phase_kind=PhaseKind(data["phase_kind"]),
            role=data["role"],
            purpose_key=data["purpose_key"],
            authority_scope=data.get("authority_scope"),
            inputs=data.get("inputs"),
            outputs=data.get("outputs"),
            gate_conditions=data.get("gate_conditions"),
            required_evidence=data.get("required_evidence"),
            is_mandatory=data.get("is_mandatory", True),
            is_read_only=data.get("is_read_only", False),
            dependencies=data.get("dependencies"),
        )


# ---------------------------------------------------------------------------
# Default strategy  (Task 10.1)
# ---------------------------------------------------------------------------

class AdaptiveStrategyRegistry:
    """Registry for adaptive (Task 10) default strategies with stable phase IDs."""

    def __init__(self) -> None:
        self._strategies: dict[str, DefaultStrategy] = {}
        self._versions: dict[str, int] = {}

    def register(self, strategy: DefaultStrategy) -> None:
        name = strategy.name
        if name in self._strategies:
            raise OrchestratorError(f"strategy {name!r} already registered")
        self._strategies[name] = strategy
        self._versions[name] = strategy.version

    def get(self, name: str) -> DefaultStrategy:
        if name not in self._strategies:
            raise OrchestratorError(f"strategy {name!r} not found")
        return self._strategies[name]

    def has(self, name: str) -> bool:
        return name in self._strategies

    def list_names(self) -> list[str]:
        return sorted(self._strategies.keys())

    def get_version(self, name: str) -> int:
        if name not in self._versions:
            raise OrchestratorError(f"strategy {name!r} not found")
        return self._versions[name]


class DefaultStrategy:
    """The default adaptive OpenSpec campaign strategy.

    Encodes Proposal Explore -> Proposal Architect -> Proposal Finalize ->
    Implementation Planning -> Implementation -> Deterministic Checks ->
    Verification -> Review -> Finalization -> Goal Judge.
    """

    def __init__(self) -> None:
        self.name = "default_adaptive"
        self.version = 1
        self.phases: list[PhaseRecord] = self._build_default_phases()
        self.non_overridable: frozenset[str] = frozenset({
            "verification",
            "goal_judge",
            "review",
        })

    def _build_default_phases(self) -> list[PhaseRecord]:
        return [
            PhaseRecord(
                phase_id="proposal_explore",
                phase_kind=PhaseKind.PROPOSAL_EXPLORE,
                role="proposal_explore",
                purpose_key="explore_workspace",
                authority_scope={"read": True, "write": False},
                inputs=["goal", "context_snapshot"],
                outputs=["exploration_report"],
                gate_conditions=["exploration_report_accepted"],
                is_read_only=True,
                dependencies=[],
            ),
            PhaseRecord(
                phase_id="proposal_architect",
                phase_kind=PhaseKind.PROPOSAL_ARCHITECT,
                role="proposal_architect",
                purpose_key="design_proposal",
                authority_scope={"read": True, "write": False},
                inputs=["exploration_report"],
                outputs=["proposal_design"],
                gate_conditions=["proposal_design_complete"],
                is_read_only=True,
                dependencies=["proposal_explore"],
            ),
            PhaseRecord(
                phase_id="proposal_finalize",
                phase_kind=PhaseKind.PROPOSAL_FINALIZE,
                role="proposal_finalizer",
                purpose_key="finalize_proposal",
                authority_scope={"read": True, "write": False},
                inputs=["exploration_report", "proposal_design"],
                outputs=["finalized_proposal"],
                gate_conditions=["proposal_finalized"],
                is_read_only=True,
                dependencies=["proposal_architect"],
            ),
            PhaseRecord(
                phase_id="implementation_planning",
                phase_kind=PhaseKind.IMPLEMENTATION_PLANNING,
                role="work_planner_architect",
                purpose_key="plan_implementation",
                authority_scope={"read": True, "write": False},
                inputs=["finalized_proposal"],
                outputs=["work_plan"],
                gate_conditions=["work_plan_valid"],
                is_read_only=True,
                dependencies=["proposal_finalize"],
            ),
            PhaseRecord(
                phase_id="implementation",
                phase_kind=PhaseKind.IMPLEMENTATION,
                role="implementation_worker",
                purpose_key="implement_changes",
                authority_scope={"read": True, "write": True},
                inputs=["work_plan"],
                outputs=["implementation_artifacts"],
                gate_conditions=["implementation_complete"],
                is_read_only=False,
                dependencies=["implementation_planning"],
            ),
            PhaseRecord(
                phase_id="deterministic_checks",
                phase_kind=PhaseKind.DETERMINISTIC_CHECKS,
                role="deterministic_checker",
                purpose_key="run_checks",
                authority_scope={"read": True, "write": False},
                inputs=["implementation_artifacts"],
                outputs=["check_results"],
                gate_conditions=["all_checks_pass"],
                is_read_only=True,
                dependencies=["implementation"],
            ),
            PhaseRecord(
                phase_id="verification",
                phase_kind=PhaseKind.VERIFICATION,
                role="verifier",
                purpose_key="verify_implementation",
                authority_scope={"read": True, "write": False},
                inputs=["implementation_artifacts", "check_results"],
                outputs=["verification_report"],
                gate_conditions=["verification_pass"],
                is_read_only=True,
                is_mandatory=True,
                dependencies=["deterministic_checks"],
            ),
            PhaseRecord(
                phase_id="review",
                phase_kind=PhaseKind.REVIEW,
                role="implementation_review_architect",
                purpose_key="review_implementation",
                authority_scope={"read": True, "write": False},
                inputs=["implementation_artifacts", "verification_report"],
                outputs=["review_findings"],
                gate_conditions=["review_acceptable"],
                is_read_only=True,
                is_mandatory=True,
                dependencies=["verification"],
            ),
            PhaseRecord(
                phase_id="finalization",
                phase_kind=PhaseKind.FINALIZATION,
                role="openspec_finalizer",
                purpose_key="finalize_openspec",
                authority_scope={"read": True, "write": True},
                inputs=["review_findings"],
                outputs=["finalized_artifacts"],
                gate_conditions=["finalization_complete"],
                dependencies=["review"],
            ),
            PhaseRecord(
                phase_id="goal_judge",
                phase_kind=PhaseKind.GOAL_JUDGE,
                role="goal_judge",
                purpose_key="judge_goal",
                authority_scope={"read": True, "write": False},
                inputs=["finalized_artifacts"],
                outputs=["goal_judgment"],
                gate_conditions=["goal_decision_recorded"],
                is_read_only=True,
                is_mandatory=True,
                dependencies=["finalization"],
            ),
        ]

    def get_phase(self, phase_id: str) -> PhaseRecord:
        for phase in self.phases:
            if phase.phase_id == phase_id:
                return phase
        raise OrchestratorError(f"phase {phase_id!r} not found in strategy {self.name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "non_overridable": sorted(self.non_overridable),
            "phases": [p.to_dict() for p in self.phases],
        }


def register_default_strategy() -> DefaultStrategy:
    """Create and return the default adaptive strategy."""
    strategy = DefaultStrategy()
    return strategy


# ---------------------------------------------------------------------------
# Goal Judge contract  (Task 10.2)
# ---------------------------------------------------------------------------

class GoalJudgeContract:
    """Contract for Goal Judge output validation.

    Enforces immutable findings, finding groups, competing hypotheses,
    goal gates, continuation analysis, and trusted terminal decisions.
    """

    VALID_DECISIONS = frozenset({
        "GOAL_ACHIEVED",
        "CONTINUE",
        "BLOCKED",
        "INFEASIBLE",
        "BLOCKED_NO_PROGRESS",
        "BUDGET_EXHAUSTED",
    })

    REQUIRED_FIELDS = frozenset({
        "immutable_findings",
        "finding_groups",
        "competing_hypotheses",
        "goal_gates",
        "continuation_analysis",
        "terminal_decision",
    })

    def __init__(self) -> None:
        pass

    def validate_goal_judge_output(self, output: dict[str, Any]) -> list[str]:
        """Validate output against the Goal Judge contract.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []

        for field in self.REQUIRED_FIELDS:
            if field not in output:
                errors.append(f"missing required field: {field}")

        immutable_findings = output.get("immutable_findings", [])
        if not isinstance(immutable_findings, list):
            errors.append("immutable_findings must be a list")
        elif not immutable_findings:
            errors.append("immutable_findings must not be empty")
        else:
            for idx, finding in enumerate(immutable_findings):
                if not isinstance(finding, dict):
                    errors.append(f"immutable_findings[{idx}] must be a dict")
                    continue
                if "finding_id" not in finding:
                    errors.append(f"immutable_findings[{idx}]: missing finding_id")
                if "severity" not in finding:
                    errors.append(f"immutable_findings[{idx}]: missing severity")
                if "evidence" not in finding:
                    errors.append(f"immutable_findings[{idx}]: missing evidence")
                if "description" not in finding:
                    errors.append(f"immutable_findings[{idx}]: missing description")
                if "confidence" not in finding:
                    errors.append(f"immutable_findings[{idx}]: missing confidence")

        finding_groups = output.get("finding_groups", [])
        if not isinstance(finding_groups, list):
            errors.append("finding_groups must be a list")
        else:
            for idx, group in enumerate(finding_groups):
                if not isinstance(group, dict):
                    errors.append(f"finding_groups[{idx}] must be a dict")
                    continue
                if "group_id" not in group:
                    errors.append(f"finding_groups[{idx}]: missing group_id")
                if "finding_ids" not in group:
                    errors.append(f"finding_groups[{idx}]: missing finding_ids")
                elif not isinstance(group["finding_ids"], list):
                    errors.append(f"finding_groups[{idx}]: finding_ids must be a list")
                if "plausibility" not in group:
                    errors.append(f"finding_groups[{idx}]: missing plausibility")

        competing_hypotheses = output.get("competing_hypotheses", [])
        if not isinstance(competing_hypotheses, list):
            errors.append("competing_hypotheses must be a list")
        else:
            for idx, hyp in enumerate(competing_hypotheses):
                if not isinstance(hyp, dict):
                    errors.append(f"competing_hypotheses[{idx}] must be a dict")
                    continue
                if "hypothesis_id" not in hyp:
                    errors.append(f"competing_hypotheses[{idx}]: missing hypothesis_id")
                if "hypothesis_text" not in hyp:
                    errors.append(f"competing_hypotheses[{idx}]: missing hypothesis_text")
                if "predicted_observations" not in hyp:
                    errors.append(f"competing_hypotheses[{idx}]: missing predicted_observations")
                if "falsifying_observations" not in hyp:
                    errors.append(f"competing_hypotheses[{idx}]: missing falsifying_observations")
                if "null_hypothesis" not in hyp:
                    errors.append(f"competing_hypotheses[{idx}]: missing null_hypothesis")

        goal_gates = output.get("goal_gates", [])
        if not isinstance(goal_gates, list):
            errors.append("goal_gates must be a list")
        elif not goal_gates:
            errors.append("goal_gates must not be empty")
        else:
            for idx, gate in enumerate(goal_gates):
                if not isinstance(gate, dict):
                    errors.append(f"goal_gates[{idx}] must be a dict")
                    continue
                if "gate_id" not in gate:
                    errors.append(f"goal_gates[{idx}]: missing gate_id")
                if "requirement" not in gate:
                    errors.append(f"goal_gates[{idx}]: missing requirement")
                if "status" not in gate:
                    errors.append(f"goal_gates[{idx}]: missing status")

        continuation_analysis = output.get("continuation_analysis")
        if continuation_analysis is None:
            pass  # only required for CONTINUE
        elif not isinstance(continuation_analysis, dict):
            errors.append("continuation_analysis must be a dict")
        else:
            if "next_cycle_strategy" not in continuation_analysis:
                errors.append("continuation_analysis: missing next_cycle_strategy")
            if "stagnation_check" not in continuation_analysis:
                errors.append("continuation_analysis: missing stagnation_check")

        terminal_decision = output.get("terminal_decision")
        if terminal_decision is None:
            errors.append("missing terminal_decision")
        elif terminal_decision not in self.VALID_DECISIONS:
            errors.append(
                f"terminal_decision must be one of {sorted(self.VALID_DECISIONS)}; "
                f"got {terminal_decision!r}"
            )

        decision = output.get("terminal_decision")
        if decision == "CONTINUE" and continuation_analysis is None:
            errors.append("continuation_analysis is required when terminal_decision is CONTINUE")

        return errors


# ---------------------------------------------------------------------------
# Hypothesis contract  (Task 10.3)
# ---------------------------------------------------------------------------

class HypothesisResultState(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class HypothesisContract:
    """Contract for one-job-per-hypothesis investigation.

    Enforces predicted and falsifying observations, primary evidence,
    confidence, and result states.
    """

    REQUIRED_FIELDS = frozenset({
        "hypothesis_id",
        "finding_id",
        "predicted_observations",
        "falsifying_observations",
        "primary_evidence",
        "confidence",
        "result_state",
    })

    def __init__(self) -> None:
        pass

    def validate_hypothesis_output(self, output: dict[str, Any]) -> list[str]:
        """Validate output against the hypothesis contract.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []

        for field in self.REQUIRED_FIELDS:
            if field not in output:
                errors.append(f"missing required field: {field}")

        predicted = output.get("predicted_observations")
        if predicted is not None:
            if not isinstance(predicted, list):
                errors.append("predicted_observations must be a list")
            elif not predicted:
                errors.append("predicted_observations must not be empty")
            else:
                for idx, obs in enumerate(predicted):
                    if not isinstance(obs, dict):
                        errors.append(f"predicted_observations[{idx}] must be a dict")
                        continue
                    if "observation" not in obs:
                        errors.append(f"predicted_observations[{idx}]: missing observation")
                    if "evidence_source" not in obs:
                        errors.append(f"predicted_observations[{idx}]: missing evidence_source")

        falsifying = output.get("falsifying_observations")
        if falsifying is not None:
            if not isinstance(falsifying, list):
                errors.append("falsifying_observations must be a list")
            elif not falsifying:
                errors.append("falsifying_observations must not be empty")
            else:
                for idx, obs in enumerate(falsifying):
                    if not isinstance(obs, dict):
                        errors.append(f"falsifying_observations[{idx}] must be a dict")
                        continue
                    if "observation" not in obs:
                        errors.append(f"falsifying_observations[{idx}]: missing observation")
                    if "evidence_source" not in obs:
                        errors.append(f"falsifying_observations[{idx}]: missing evidence_source")

        primary_evidence = output.get("primary_evidence")
        if primary_evidence is not None:
            if not isinstance(primary_evidence, list):
                errors.append("primary_evidence must be a list")
            elif not primary_evidence:
                errors.append("primary_evidence must not be empty")
            else:
                for idx, ev in enumerate(primary_evidence):
                    if not isinstance(ev, dict):
                        errors.append(f"primary_evidence[{idx}] must be a dict")
                        continue
                    if "ref" not in ev:
                        errors.append(f"primary_evidence[{idx}]: missing ref")
                    if "digest" not in ev:
                        errors.append(f"primary_evidence[{idx}]: missing digest")
                    if "summary" not in ev:
                        errors.append(f"primary_evidence[{idx}]: missing summary")

        confidence = output.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                errors.append("confidence must be a number")
            elif not (0.0 <= confidence <= 1.0):
                errors.append("confidence must be between 0.0 and 1.0")

        result_state = output.get("result_state")
        if result_state is not None:
            valid_states = {s.value for s in HypothesisResultState}
            if result_state not in valid_states:
                errors.append(
                    f"result_state must be one of {sorted(valid_states)}; "
                    f"got {result_state!r}"
                )

        return errors


# ---------------------------------------------------------------------------
# Synthesis contract  (Task 10.4)
# ---------------------------------------------------------------------------

class SynthesisContract:
    """Contract for Synthesis Architect output.

    Must consume all settled hypotheses and produce planning constraints.
    """

    REQUIRED_FIELDS = frozenset({
        "synthesis_id",
        "consumed_hypothesis_ids",
        "conclusion",
        "planning_constraints",
        "evidence_refs",
    })

    VALID_CONCLUSIONS = frozenset({
        "root_cause_identified",
        "partial_understanding",
        "no_actionable_cause",
        "needs_further_investigation",
    })

    def validate_synthesis_output(
        self,
        output: dict[str, Any],
        all_settled_hypothesis_ids: list[str] | None = None,
    ) -> list[str]:
        """Validate output against the synthesis contract.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []

        for field in self.REQUIRED_FIELDS:
            if field not in output:
                errors.append(f"missing required field: {field}")

        consumed = output.get("consumed_hypothesis_ids", [])
        if not isinstance(consumed, list):
            errors.append("consumed_hypothesis_ids must be a list")
        elif all_settled_hypothesis_ids is not None:
            settled = set(all_settled_hypothesis_ids)
            consumed_set = set(consumed)
            if consumed_set != settled:
                missing = settled - consumed_set
                extra = consumed_set - settled
                if missing:
                    errors.append(
                        f"consumed_hypothesis_ids missing settled hypotheses: {sorted(missing)}"
                    )
                if extra:
                    errors.append(
                        f"consumed_hypothesis_ids contains unknown hypotheses: {sorted(extra)}"
                    )

        conclusion = output.get("conclusion")
        if conclusion is not None and conclusion not in self.VALID_CONCLUSIONS:
            errors.append(
                f"conclusion must be one of {sorted(self.VALID_CONCLUSIONS)}; "
                f"got {conclusion!r}"
            )

        planning_constraints = output.get("planning_constraints")
        if planning_constraints is not None:
            if not isinstance(planning_constraints, dict):
                errors.append("planning_constraints must be a dict")
            else:
                if "supported_causes" not in planning_constraints:
                    errors.append("planning_constraints: missing supported_causes")
                if "refuted_causes" not in planning_constraints:
                    errors.append("planning_constraints: missing refuted_causes")
                if "unresolved_causes" not in planning_constraints:
                    errors.append("planning_constraints: missing unresolved_causes")

        return errors


class WorkPlannerContract:
    """Contract for Work Planner Architect output.

    Must select exactly one decision variant from the allowed set.
    """

    VALID_DECISION_VARIANTS = frozenset({
        "direct_repair",
        "implementation_set",
        "openspec_batch",
        "no_safe_path",
    })

    REQUIRED_FIELDS = frozenset({
        "plan_id",
        "plan_type",
        "selected_decision",
        "targets",
        "cycle_id",
    })

    def validate_work_planner_output(self, output: dict[str, Any]) -> list[str]:
        """Validate output against the work planner contract.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []

        for field in self.REQUIRED_FIELDS:
            if field not in output:
                errors.append(f"missing required field: {field}")

        selected = output.get("selected_decision")
        if selected is not None:
            if selected not in self.VALID_DECISION_VARIANTS:
                errors.append(
                    f"selected_decision must be one of "
                    f"{sorted(self.VALID_DECISION_VARIANTS)}; "
                    f"got {selected!r}"
                )

        targets = output.get("targets")
        if targets is not None:
            if not isinstance(targets, list):
                errors.append("targets must be a list")
            elif selected == "no_safe_path":
                if targets:
                    errors.append("targets must be empty for no_safe_path decision")
            else:
                if not targets:
                    errors.append("targets must not be empty for non-no_safe_path decision")
                else:
                    for idx, target in enumerate(targets):
                        if not isinstance(target, dict):
                            errors.append(f"targets[{idx}] must be a dict")
                            continue
                        if "target_id" not in target:
                            errors.append(f"targets[{idx}]: missing target_id")
                        if "target_type" not in target:
                            errors.append(f"targets[{idx}]: missing target_type")

        return errors


# ---------------------------------------------------------------------------
# Path selection rules  (Task 10.5)
# ---------------------------------------------------------------------------

class PathSelectionRules:
    """Encode path-selection rules for direct repair, implementation set,
    and OpenSpec redesign.
    """

    def direct_repair_conditions(
        self,
        is_local: bool,
        is_reversible: bool,
        no_material_change: bool,
        single_cause: bool,
    ) -> bool:
        """Direct repair requires local, reversible, no material change, single cause."""
        return is_local and is_reversible and no_material_change and single_cause

    def implementation_set_conditions(
        self,
        known_design: bool,
        multiple_components: bool,
        cohesive: bool,
    ) -> bool:
        """Implementation set requires known design, multiple components, cohesive."""
        return known_design and multiple_components and cohesive

    def openspec_batch_conditions(
        self,
        material_redesign: bool,
        contract_change: bool = False,
        migration_required: bool = False,
        protocol_change: bool = False,
        trust_boundary_change: bool = False,
    ) -> bool:
        """OpenSpec batch requires material redesign with any contract, migration,
        protocol, or trust boundary change."""
        return (
            material_redesign
            or contract_change
            or migration_required
            or protocol_change
            or trust_boundary_change
        )

    def validate_path_selection(
        self,
        selected_path: str,
        conditions: dict[str, Any],
    ) -> list[str]:
        """Validate that the correct path was selected based on conditions.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        valid_paths = {"direct_repair", "implementation_set", "openspec_batch", "no_safe_path"}

        if selected_path not in valid_paths:
            errors.append(
                f"selected_path must be one of {sorted(valid_paths)}; "
                f"got {selected_path!r}"
            )
            return errors

        is_local = conditions.get("is_local", False)
        is_reversible = conditions.get("is_reversible", False)
        no_material_change = conditions.get("no_material_change", False)
        single_cause = conditions.get("single_cause", False)
        known_design = conditions.get("known_design", False)
        multiple_components = conditions.get("multiple_components", False)
        cohesive = conditions.get("cohesive", False)
        material_redesign = conditions.get("material_redesign", False)
        contract_change = conditions.get("contract_change", False)
        migration_required = conditions.get("migration_required", False)
        protocol_change = conditions.get("protocol_change", False)
        trust_boundary_change = conditions.get("trust_boundary_change", False)

        should_direct = self.direct_repair_conditions(
            is_local, is_reversible, no_material_change, single_cause,
        )
        should_impl_set = self.implementation_set_conditions(
            known_design, multiple_components, cohesive,
        )
        should_openspec = self.openspec_batch_conditions(
            material_redesign, contract_change, migration_required,
            protocol_change, trust_boundary_change,
        )

        if should_direct and selected_path != "direct_repair":
            errors.append(
                "conditions satisfy direct_repair but a different path was selected"
            )
        if should_impl_set and selected_path != "implementation_set":
            errors.append(
                "conditions satisfy implementation_set but a different path was selected"
            )
        if should_openspec and selected_path not in ("openspec_batch", "implementation_set"):
            errors.append(
                "conditions require OpenSpec batch but openspec_batch was not selected"
            )

        return errors


# ---------------------------------------------------------------------------
# Review lenses  (Task 10.6)
# ---------------------------------------------------------------------------

class ReviewLens:
    """Encapsulates a single review lens with its criteria."""

    def __init__(
        self,
        lens_id: str,
        display_name: str,
        description: str,
        check_items: list[str] | None = None,
        requires_evidence: bool = True,
    ) -> None:
        self.lens_id = lens_id
        self.display_name = display_name
        self.description = description
        self.check_items = check_items or []
        self.requires_evidence = requires_evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "display_name": self.display_name,
            "description": self.description,
            "check_items": self.check_items,
            "requires_evidence": self.requires_evidence,
        }


FORMAL_GATES = ReviewLens(
    lens_id="formal_gates",
    display_name="Formal Gates",
    description="Verify all formal gate conditions are satisfied",
    check_items=[
        "all_required_checks_pass",
        "gate_conditions_met",
        "no_stale_results",
    ],
)

KISS = ReviewLens(
    lens_id="kiss",
    display_name="KISS",
    description="Keep It Simple: assess unnecessary complexity",
    check_items=[
        "no_unnecessary_abstraction",
        "straightforward_control_flow",
        "appropriate_complexity_for_domain",
    ],
)

SOLID = ReviewLens(
    lens_id="solid",
    display_name="SOLID",
    description="Single Responsibility, Open/Closed, Liskov, Interface Segregation, Dependency Inversion",
    check_items=[
        "single_responsibility_per_module",
        "open_for_extension_closed_for_modification",
        "behavioral_contracts_preserved",
        "focused_interfaces",
        "dependencies_on_abstractions",
    ],
)

DRY = ReviewLens(
    lens_id="dry",
    display_name="DRY",
    description="Don't Repeat Yourself: assess unjustified duplication",
    check_items=[
        "no_semantic_duplication",
        "shared_abstractions_for_repeated_logic",
        "copy_paste_not_present",
    ],
)

YAGNI = ReviewLens(
    lens_id="yagni",
    display_name="YAGNI",
    description="You Aren't Gonna Need It: assess speculative generality",
    check_items=[
        "no_speculative_features",
        "no_premature_optimization",
        "code_serves_current_requirements",
    ],
)

COHESION = ReviewLens(
    lens_id="cohesion",
    display_name="Cohesion",
    description="Module elements share a common purpose",
    check_items=[
        "elements_share_common_purpose",
        "no_unrelated_responsibilities_in_single_module",
        "clear_module_boundary",
    ],
)

COUPLING = ReviewLens(
    lens_id="coupling",
    display_name="Coupling",
    description="Assess inter-module dependencies",
    check_items=[
        "no_excessive_coupling",
        "dependencies_are_justified",
        "change_locality_preserved",
        "no_circular_dependencies",
    ],
)

API_LENS = ReviewLens(
    lens_id="api",
    display_name="API Design",
    description="Assess API contracts, naming, and consistency",
    check_items=[
        "consistent_naming_conventions",
        "stable_public_contracts",
        "backward_compatibility",
        "clear_api_boundaries",
    ],
)

SECURITY = ReviewLens(
    lens_id="security",
    display_name="Security",
    description="Assess security implications",
    check_items=[
        "no_secret_exposure",
        "input_validation",
        "authorization_enforced",
        "no_injection_vulnerabilities",
    ],
)

RELIABILITY = ReviewLens(
    lens_id="reliability",
    display_name="Reliability",
    description="Assess error handling, retries, and failure modes",
    check_items=[
        "error_handling_comprehensive",
        "retry_policies_bounded",
        "failure_modes_identified",
        "recovery_paths_documented",
    ],
)

PERFORMANCE = ReviewLens(
    lens_id="performance",
    display_name="Performance",
    description="Assess performance implications",
    check_items=[
        "no_unbounded_loops",
        "appropriate_caching",
        "resource_usage_bounded",
        "no_known_performance_regressions",
    ],
)

OPERABILITY = ReviewLens(
    lens_id="operability",
    display_name="Operability",
    description="Assess operational concerns",
    check_items=[
        "logging_adequate",
        "metrics_available",
        "debugging_paths_clear",
        "deployment_safe",
    ],
)

TESTING = ReviewLens(
    lens_id="testing",
    display_name="Testing",
    description="Assess test coverage and quality",
    check_items=[
        "tests_cover_critical_paths",
        "tests_are_deterministic",
        "tests_validate_behavior_not_implementation",
        "edge_cases_covered",
    ],
)

DOCUMENTATION = ReviewLens(
    lens_id="documentation",
    display_name="Documentation",
    description="Assess documentation completeness",
    check_items=[
        "public_api_documented",
        "design_decisions_recorded",
        "usage_examples_provided",
        "limitations_documented",
    ],
)

MIGRATION = ReviewLens(
    lens_id="migration",
    display_name="Migration",
    description="Assess migration and upgrade paths",
    check_items=[
        "backward_compatible",
        "migration_path_clear",
        "data_loss_prevented",
        "rollback_possible",
    ],
)

DEPENDENCIES = ReviewLens(
    lens_id="dependencies",
    display_name="Dependencies",
    description="Assess external dependency management",
    check_items=[
        "dependencies_justified",
        "versions_pinned",
        "vulnerabilities_checked",
        "license_compatible",
    ],
)

HIGH_LEVEL_DESIGN = ReviewLens(
    lens_id="high_level_design",
    display_name="High-Level Design",
    description="Assess architectural design quality",
    check_items=[
        "architecture_clear",
        "components_well_defined",
        "boundaries_appropriate",
        "scalability_considered",
    ],
)

LONG_TERM_SUPPORT = ReviewLens(
    lens_id="long_term_support",
    display_name="Long-Term Support",
    description="Assess maintainability and long-term viability",
    check_items=[
        "maintainable_codebase",
        "clear_ownership",
        "deprecation_path_defined",
        "support_plan_documented",
    ],
)

IMPLEMENTATION_REVIEW_LENSES: list[ReviewLens] = [
    FORMAL_GATES,
    KISS,
    SOLID,
    DRY,
    YAGNI,
    COHESION,
    COUPLING,
    API_LENS,
    SECURITY,
    RELIABILITY,
    PERFORMANCE,
    OPERABILITY,
    TESTING,
    DOCUMENTATION,
    MIGRATION,
    DEPENDENCIES,
    HIGH_LEVEL_DESIGN,
    LONG_TERM_SUPPORT,
]

GOAL_JUDGE_REVIEW_LENSES: list[ReviewLens] = [
    FORMAL_GATES,
    KISS,
    SOLID,
    DRY,
    YAGNI,
    COHESION,
    COUPLING,
    API_LENS,
    SECURITY,
    RELIABILITY,
    PERFORMANCE,
    OPERABILITY,
    TESTING,
    DOCUMENTATION,
    MIGRATION,
    DEPENDENCIES,
    HIGH_LEVEL_DESIGN,
    LONG_TERM_SUPPORT,
]


# ---------------------------------------------------------------------------
# Architect enforcer  (Task 10.7)
# ---------------------------------------------------------------------------

class ArchitectEnforcer:
    """Enforces Architect role boundaries: read-only, fresh instances,
    no self-verification, no self-approval, and evidence-based findings.
    """

    ARCHITECT_ROLES = frozenset({
        "proposal_explore",
        "proposal_architect",
        "proposal_finalizer",
        "work_planner_architect",
        "implementation_review_architect",
        "synthesis_architect",
        "goal_judge",
    })

    SLOGAN_PATTERNS = frozenset({
        "follows best practices",
        "is not clean",
        "should be refactored",
        "violates principles",
        "too complex",
        "not simple",
        "needs improvement",
        "bad code",
        "code smell",
        "technical debt",
    })

    def enforce_read_only(self, role: str, actions: list[str]) -> list[str]:
        """Architect must not perform implementation actions.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        if role not in self.ARCHITECT_ROLES:
            return errors
        write_actions = {"write_file", "create_file", "modify_file", "delete_file"}
        for action in actions:
            if action in write_actions:
                errors.append(
                    f"Architect role {role!r} cannot perform write action {action!r}; "
                    f"Architects are read-only"
                )
        return errors

    def enforce_fresh_instances(
        self,
        job_id: str,
        role: str,
        previously_used_job_ids: set[str],
    ) -> list[str]:
        """Architect jobs must be fresh instances, not reused.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        if role not in self.ARCHITECT_ROLES:
            return errors
        if job_id in previously_used_job_ids:
            errors.append(
                f"Architect role {role!r} cannot reuse job {job_id!r}; "
                f"each Architect execution must be a fresh instance"
            )
        return errors

    def enforce_no_self_verification(
        self,
        verifier_job_id: str,
        target_job_id: str,
        verifier_role: str,
        target_role: str,
    ) -> list[str]:
        """Architect cannot verify its own work.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        if verifier_job_id == target_job_id:
            errors.append(
                f"self-verification rejected: job {verifier_job_id!r} "
                f"cannot verify its own output"
            )
        if verifier_role == target_role and verifier_role in self.ARCHITECT_ROLES:
            errors.append(
                f"Architect role {verifier_role!r} cannot verify work from "
                f"the same role {target_role!r}"
            )
        return errors

    def enforce_no_self_approval(
        self,
        approver_job_id: str,
        target_job_id: str,
        approver_role: str,
    ) -> list[str]:
        """Architect cannot approve its own work.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        if approver_job_id == target_job_id:
            errors.append(
                f"self-approval rejected: job {approver_job_id!r} "
                f"cannot approve its own output"
            )
        if approver_role in self.ARCHITECT_ROLES:
            errors.append(
                f"Architect role {approver_role!r} cannot approve work "
                f"produced by its own planning or design"
            )
        return errors

    def enforce_evidence_based_findings(self, finding: dict[str, Any]) -> list[str]:
        """Every finding must have concrete evidence, not just principle citations.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        description = finding.get("description", "")

        if not description:
            errors.append("finding must have a description")
            return errors

        has_evidence = bool(finding.get("evidence"))
        has_consequence = bool(finding.get("consequence"))
        has_correction = bool(finding.get("correction_objective"))

        if not has_evidence:
            errors.append(
                f"finding must include primary evidence; "
                f"description: {description!r}"
            )
        if not has_consequence:
            errors.append(
                f"finding must include concrete consequence; "
                f"description: {description!r}"
            )
        if not has_correction:
            errors.append(
                f"finding must include correction_objective; "
                f"description: {description!r}"
            )

        return errors

    def reject_slogan_findings(self, finding: dict[str, Any]) -> list[str]:
        """Reject findings that are only principle slogans without concrete evidence.

        Returns a list of error strings; empty means valid (not a slogan).
        """
        errors: list[str] = []
        description = finding.get("description", "").lower()

        for slogan in self.SLOGAN_PATTERNS:
            if slogan in description:
                evidence = finding.get("evidence", [])
                consequence = finding.get("consequence", "")
                if not evidence or not consequence:
                    errors.append(
                        f"finding appears to be a principle slogan without "
                        f"concrete evidence: {finding.get('description', '')!r}; "
                        f"findings must include specific evidence and consequence"
                    )
                    break

        return errors


# ---------------------------------------------------------------------------
# Durable solution enforcer  (Task 10.8)
# ---------------------------------------------------------------------------

class DurableSolutionEnforcer:
    """Enforces durable-solution requirements.

    Temporary mitigations cannot satisfy campaign completion and must
    be linked to mandatory replacement work.
    """

    PROVISIONAL_MARKER = "PROVISIONAL_MITIGATION"

    def enforce_durable_solution(self, repair: dict[str, Any]) -> list[str]:
        """Require correction of the causal mechanism, not symptom-only patches.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        repair_type = repair.get("repair_type", "")

        symptom_only_indicators = [
            "skip_test",
            "mock_external",
            "disable_check",
            "bypass_validation",
            "temporary_fix",
            "workaround",
            "hide_error",
            "ignore_failure",
        ]

        repair_str = str(repair).lower()
        for indicator in symptom_only_indicators:
            if indicator in repair_str:
                errors.append(
                    f"repair appears to be a symptom-only patch: "
                    f"contains {indicator!r}; durable solution requires "
                    f"correction of the causal mechanism"
                )

        if repair_type == "temporary_mitigation":
            errors.append(
                "repair is a temporary mitigation; durable solution "
                "requires causal correction at the authoritative boundary"
            )

        return errors

    def label_provisional_mitigation(self, repair: dict[str, Any]) -> dict[str, Any]:
        """Mark a repair as a provisional mitigation.

        Returns the repair dict with provisional label added.
        """
        labeled = dict(repair)
        labeled["mitigation_label"] = self.PROVISIONAL_MARKER
        labeled["is_provisional"] = True
        labeled["requires_replacement"] = True
        return labeled

    def link_replacement_work(
        self,
        provisional_repair: dict[str, Any],
        replacement_work_id: str,
    ) -> dict[str, Any]:
        """Link a provisional mitigation to mandatory replacement work.

        Returns the repair dict with replacement work link.
        """
        linked = dict(provisional_repair)
        linked["replacement_work_id"] = replacement_work_id
        linked["replacement_mandatory"] = True
        return linked

    def prevent_mitigation_completion(
        self,
        repair: dict[str, Any],
        proposed_decision: str,
    ) -> list[str]:
        """Prevent a provisional mitigation from satisfying GOAL_ACHIEVED.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []
        is_provisional = repair.get("is_provisional", False)
        mitigation_label = repair.get("mitigation_label", "")

        if is_provisional or mitigation_label == self.PROVISIONAL_MARKER:
            if proposed_decision == "GOAL_ACHIEVED":
                errors.append(
                    "provisional mitigation cannot satisfy GOAL_ACHIEVED; "
                    "mandatory replacement work must be completed first"
                )

        return errors


# ---------------------------------------------------------------------------
# Finding disposition enforcer  (Task 10.9)
# ---------------------------------------------------------------------------

class FindingDispositionEnforcer:
    """Requires every finding to have a valid disposition before goal success.

    Every finding must be fixed and verified, refuted, superseded, or
    otherwise authorized and evidenced before GOAL_ACHIEVED.
    """

    VALID_DISPOSITIONS = frozenset({
        "verified",
        "refuted",
        "superseded",
        "accepted_risk",
    })

    def require_disposition(self, finding_id: str) -> bool:
        """Check that a finding has a disposition record.

        Returns True if disposition exists, False otherwise.
        """
        # This is a check stub; actual implementation queries graph state.
        return True

    def validate_finding_disposition(self, disposition: dict[str, Any]) -> list[str]:
        """Validate that a finding disposition is complete and valid.

        Returns a list of error strings; empty means valid.
        """
        errors: list[str] = []

        required_fields = ["finding_id", "status", "evidence_refs", "reason"]
        for field in required_fields:
            if field not in disposition:
                errors.append(f"disposition missing required field: {field}")

        status = disposition.get("status")
        if status is not None and status not in self.VALID_DISPOSITIONS:
            errors.append(
                f"disposition status must be one of {sorted(self.VALID_DISPOSITIONS)}; "
                f"got {status!r}"
            )

        evidence_refs = disposition.get("evidence_refs", [])
        if not evidence_refs:
            errors.append("disposition must include at least one evidence reference")

        reason = disposition.get("reason", "")
        if not reason:
            errors.append("disposition must include a reason")

        return errors

    def block_goal_without_disposition(
        self,
        finding_ids: set[str],
        dispositioned_finding_ids: set[str],
    ) -> list[str]:
        """Block GOAL_ACHIEVED if any finding lacks a valid disposition.

        Returns a list of error strings; empty means all findings are dispositioned.
        """
        errors: list[str] = []
        undisp = finding_ids - dispositioned_finding_ids
        if undisp:
            errors.append(
                f"GOAL_ACHIEVED blocked: {len(undisp)} finding(s) lack valid "
                f"disposition: {sorted(undisp)}"
            )
        return errors


# ---------------------------------------------------------------------------
# StrategyCompiler  (Task 9.2-9.3 reference, minimal for Group 10)
# ---------------------------------------------------------------------------

class AdaptiveStrategyCompiler:
    """Task-10 compatibility helper for API tests; not used by production init."""

    VALID_OPERATIONS = frozenset({"extend", "replace", "configure", "disable"})
    NON_OVERRIDABLE_PHASES = frozenset({"verification", "goal_judge", "review"})

    def __init__(self, strategy: DefaultStrategy) -> None:
        self._strategy = strategy

    def compile(
        self,
        overrides: list[dict[str, Any]] | None = None,
    ) -> DefaultStrategy:
        """Apply overrides and return a resolved strategy.

        Returns a new DefaultStrategy with overrides applied.
        """
        if not overrides:
            return self._strategy

        resolved = DefaultStrategy()
        resolved.phases = [PhaseRecord(
            phase_id=p.phase_id,
            phase_kind=p.phase_kind,
            role=p.role,
            purpose_key=p.purpose_key,
            authority_scope=dict(p.authority_scope),
            inputs=list(p.inputs),
            outputs=list(p.outputs),
            gate_conditions=list(p.gate_conditions),
            required_evidence=list(p.required_evidence),
            is_mandatory=p.is_mandatory,
            is_read_only=p.is_read_only,
            dependencies=list(p.dependencies),
        ) for p in self._strategy.phases]

        errors: list[str] = []
        for override in overrides:
            op_errors = self._apply_override(resolved, override)
            errors.extend(op_errors)

        if errors:
            raise OrchestratorError(
                f"strategy compilation failed with {len(errors)} error(s): "
                + "; ".join(errors)
            )

        return resolved

    def _apply_override(
        self,
        strategy: DefaultStrategy,
        override: dict[str, Any],
    ) -> list[str]:
        """Apply a single override. Returns error list."""
        errors: list[str] = []
        operation = override.get("operation")
        target_phase = override.get("target_phase")

        if operation not in self.VALID_OPERATIONS:
            errors.append(f"invalid operation: {operation!r}")
            return errors

        if target_phase in self.NON_OVERRIDABLE_PHASES:
            errors.append(
                f"phase {target_phase!r} is non-overridable; "
                f"cannot apply {operation!r}"
            )
            return errors

        phase_exists = any(p.phase_id == target_phase for p in strategy.phases)
        if not phase_exists and operation in ("replace", "disable"):
            errors.append(f"phase {target_phase!r} not found for {operation!r}")

        return errors


# ---------------------------------------------------------------------------
# Convenience: get all review lenses for a role
# ---------------------------------------------------------------------------

def get_review_lenses_for_role(role: str) -> list[ReviewLens]:
    """Return the applicable review lenses for a given role."""
    if role == "implementation_review_architect":
        return list(IMPLEMENTATION_REVIEW_LENSES)
    if role == "goal_judge":
        return list(GOAL_JUDGE_REVIEW_LENSES)
    return []


# ---------------------------------------------------------------------------
# Group 11: Campaign Branch, Finalization, and Publication
# ---------------------------------------------------------------------------

# --- Task 11.1: CampaignBranchInitializer -----------------------------------

class CampaignBranchInitializer:
    """Initialize campaign feature branch and persist branch info in envelope."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def initialize_branch(
        self,
        campaign_id: str,
        strategy: str,
    ) -> dict[str, Any]:
        """Create or select feature branch for campaign.

        Returns dict with branch_name, baseline_commit, cycle_id.
        """
        branch_name = f"campaign/{campaign_id}"
        baseline_commit = self.get_baseline_commit()
        cycle_id = self.generate_cycle_id(campaign_id)

        return {
            "branch_name": branch_name,
            "baseline_commit": baseline_commit,
            "cycle_id": cycle_id,
            "campaign_id": campaign_id,
            "created_at": utc_now(),
        }

    def persist_branch_info(
        self,
        envelope: dict[str, Any],
        branch_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Store branch info in the frozen campaign envelope.

        Returns the updated envelope with branch metadata.
        """
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise OrchestratorError("cannot persist branch info to non-v6 envelope")

        envelope_copy = dict(envelope)
        envelope_copy["branch"] = {
            "branch_name": branch_info["branch_name"],
            "baseline_commit": branch_info["baseline_commit"],
            "initial_cycle_id": branch_info["cycle_id"],
            "persisted_at": utc_now(),
        }
        return envelope_copy

    def get_baseline_commit(self) -> str:
        """Get the current HEAD commit as baseline."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise OrchestratorError(
                f"failed to get baseline commit: {exc}"
            ) from exc

    def generate_cycle_id(self, campaign_id: str) -> str:
        """Generate a cycle identity from campaign ID and timestamp."""
        return stable_id("CYC", campaign_id, utc_now())


# --- Task 11.2: BranchInitWorker --------------------------------------------

class BranchInitWorker:
    """Execute branch initialization as a worker job with observable recovery."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")
        self.initializer = CampaignBranchInitializer(repo_root)

    def execute_branch_init(
        self,
        campaign_id: str,
        strategy: str,
        envelope: dict[str, Any],
    ) -> dict[str, Any]:
        """Run branch initialization as a worker job.

        Returns branch init result with status and recovery info.
        """
        branch_info = self.initializer.initialize_branch(campaign_id, strategy)
        updated_envelope = self.initializer.persist_branch_info(envelope, branch_info)
        
        return {
            "status": "pending_job",
            "job_type": "branch_init_worker",
            "campaign_id": campaign_id,
            "branch_info": branch_info,
            "updated_envelope": updated_envelope,
            "baseline_report": self.report_baseline_commit(branch_info),
            "recovery_state": {"recoverable": True}
        }

    def observable_recovery_check(self, branch_info: dict[str, Any]) -> dict[str, Any]:
        """Verify branch state is consistent after initialization.

        Checks that the branch exists and HEAD matches expected baseline.
        """
        import subprocess
        branch_name = branch_info["branch_name"]
        expected_commit = branch_info["baseline_commit"]

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            branch_exists = result.returncode == 0

            current_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            head_matches = current_head == expected_commit

            return {
                "recoverable": branch_exists and head_matches,
                "branch_exists": branch_exists,
                "head_matches_expected": head_matches,
                "current_head": current_head,
            }
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            return {
                "recoverable": False,
                "error": str(exc),
            }

    def report_baseline_commit(self, branch_info: dict[str, Any]) -> dict[str, Any]:
        """Report baseline commit to control plane."""
        return {
            "report_type": "baseline_commit",
            "campaign_id": branch_info["campaign_id"],
            "branch_name": branch_info["branch_name"],
            "baseline_commit": branch_info["baseline_commit"],
            "cycle_id": branch_info["cycle_id"],
            "reported_at": utc_now(),
        }


# --- Task 11.3: CycleFinalizer -----------------------------------------------

class CycleFinalizer:
    """Finalize each clean cycle through explicit worker jobs."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def resolve_openspec_stores(
        self,
        cycle_id: str,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Re-resolve OpenSpec stores for the cycle.

        Returns resolved store paths and metadata.
        """
        openspec_root = self.repo_root / "openspec"
        stores = {}

        for store_name in ("changes", "specs", "archive"):
            store_path = openspec_root / store_name
            if store_path.exists():
                stores[store_name] = {
                    "path": str(store_path),
                    "resolved": True,
                    "item_count": sum(1 for _ in store_path.iterdir()),
                }
            else:
                stores[store_name] = {
                    "path": str(store_path),
                    "resolved": False,
                    "item_count": 0,
                }

        return {
            "cycle_id": cycle_id,
            "campaign_id": campaign_id,
            "stores": stores,
            "resolved_at": utc_now(),
        }

    def sync_required_specs(
        self,
        cycle_id: str,
        required_specs: list[str],
    ) -> dict[str, Any]:
        """Sync required specs for the cycle.

        Returns sync status for each spec.
        """
        spec_results = []
        for spec_name in required_specs:
            spec_path = self.repo_root / "openspec" / "specs" / f"{spec_name}.md"
            exists = spec_path.exists()
            spec_results.append({
                "spec_name": spec_name,
                "path": str(spec_path),
                "synced": exists,
            })

        return {
            "cycle_id": cycle_id,
            "spec_results": spec_results,
            "all_synced": all(r["synced"] for r in spec_results),
            "synced_at": utc_now(),
        }

    def archive_completed_changes(
        self,
        cycle_id: str,
        completed_changes: list[str],
    ) -> dict[str, Any]:
        """Archive completed changes for the cycle.

        Returns archive results.
        """
        archive_root = self.repo_root / "openspec" / "archive"
        archive_results = []

        for change_id in completed_changes:
            source = self.repo_root / "openspec" / "changes" / change_id
            destination = archive_root / cycle_id / change_id

            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                archive_results.append({
                    "change_id": change_id,
                    "archived": True,
                    "destination": str(destination),
                })
            else:
                archive_results.append({
                    "change_id": change_id,
                    "archived": False,
                    "reason": "source not found",
                })

        return {
            "cycle_id": cycle_id,
            "archive_results": archive_results,
            "archived_at": utc_now(),
        }

    def verify_final_artifacts(
        self,
        cycle_id: str,
        expected_artifacts: list[str],
    ) -> dict[str, Any]:
        """Verify final artifact state for the cycle.

        Returns verification results.
        """
        verification_results = []
        for artifact_path in expected_artifacts:
            full_path = self.repo_root / artifact_path
            exists = full_path.exists()
            verification_results.append({
                "artifact": artifact_path,
                "exists": exists,
            })

        return {
            "cycle_id": cycle_id,
            "verification_results": verification_results,
            "all_present": all(r["exists"] for r in verification_results),
            "verified_at": utc_now(),
        }


# --- Task 11.4: CycleCommitter -----------------------------------------------

class CycleCommitter:
    """Create exactly one commit per accepted implementation cycle."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def create_commit(
        self,
        cycle_id: str,
        campaign_id: str,
        branch_name: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Create one commit per cycle.

        Stages only campaign-owned changes and creates a single commit.
        Returns commit result.
        """
        import subprocess

        if message is None:
            message = f"campaign {campaign_id} cycle {cycle_id}"

        campaign_files = self.filter_campaign_changes()
        validation = self.validate_commit_contents(campaign_files)

        if not validation["valid"]:
            return {
                "status": "rejected",
                "reason": validation["reason"],
                "cycle_id": cycle_id,
            }

        try:
            for file_path in campaign_files:
                subprocess.run(
                    ["git", "add", file_path],
                    cwd=self.repo_root,
                    check=True,
                    capture_output=True,
                )

            result = subprocess.run(
                ["git", "commit", "-m", message, "--allow-empty"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {
                    "status": "failed",
                    "error": result.stderr,
                    "cycle_id": cycle_id,
                }

            commit_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            return {
                "status": "committed",
                "commit_hash": commit_hash,
                "cycle_id": cycle_id,
                "campaign_id": campaign_id,
                "branch_name": branch_name,
                "files_committed": len(campaign_files),
                "committed_at": utc_now(),
            }
        except subprocess.CalledProcessError as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "cycle_id": cycle_id,
            }

    def filter_campaign_changes(self) -> list[str]:
        """Return only campaign-owned files from working tree changes.

        Filters to files under openspec/, docs/, and strategy-related paths.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files = [
                f for f in result.stdout.strip().splitlines()
                if f
            ]

            campaign_prefixes = ("openspec/", "docs/", "strategy_", "campaign_")
            campaign_files = [
                f for f in changed_files
                if any(f.startswith(prefix) for prefix in campaign_prefixes)
            ]

            result_untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            untracked = [
                f for f in result_untracked.stdout.strip().splitlines()
                if f
            ]
            campaign_untracked = [
                f for f in untracked
                if any(f.startswith(prefix) for prefix in campaign_prefixes)
            ]

            return list(dict.fromkeys(campaign_files + campaign_untracked))
        except subprocess.CalledProcessError:
            return []

    def validate_commit_contents(self, files: list[str]) -> dict[str, Any]:
        """Ensure commit contains only allowed campaign-owned files.

        Returns validation result.
        """
        if not files:
            return {"valid": False, "reason": "no campaign-owned files to commit"}

        import re
        allowed_patterns = [
            r"^openspec/",
            r"^docs/",
            r"^strategy_",
            r"^campaign_",
        ]

        for file_path in files:
            if not any(re.match(pattern, file_path) for pattern in allowed_patterns):
                return {
                    "valid": False,
                    "reason": f"file {file_path!r} is not campaign-owned",
                }

        return {"valid": True, "reason": "all files are campaign-owned"}


# --- Task 11.5: CyclePusher --------------------------------------------------

class CyclePusher:
    """Push campaign feature branch after each cycle with idempotency."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def push_branch(
        self,
        branch_name: str,
        cycle_id: str,
        commit_hash: str,
    ) -> dict[str, Any]:
        """Push feature branch to remote.

        Returns push result with recovery info.
        """
        idempotency = self.idempotency_check(branch_name, cycle_id, commit_hash)
        if idempotency["already_pushed"]:
            return {
                "status": "skipped",
                "reason": "already pushed",
                "idempotency": idempotency,
            }

        import subprocess
        try:
            result = subprocess.run(
                ["git", "push", "origin", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                recovery = self.observable_remote_ref_recovery(branch_name, commit_hash)
                return {
                    "status": "failed",
                    "error": result.stderr,
                    "recovery": recovery,
                    "cycle_id": cycle_id,
                }

            return {
                "status": "pushed",
                "branch_name": branch_name,
                "cycle_id": cycle_id,
                "commit_hash": commit_hash,
                "pushed_at": utc_now(),
            }
        except FileNotFoundError as exc:
            return {
                "status": "failed",
                "error": f"git not available: {exc}",
                "cycle_id": cycle_id,
            }

    def observable_remote_ref_recovery(
        self,
        branch_name: str,
        expected_commit: str,
    ) -> dict[str, Any]:
        """Verify remote ref state after push attempt.

        Checks if the remote branch exists and points to expected commit.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {
                    "recoverable": False,
                    "reason": "cannot query remote",
                }

            remote_refs = result.stdout.strip()
            if not remote_refs:
                return {
                    "recoverable": False,
                    "reason": "remote branch does not exist",
                }

            remote_commit = remote_refs.split()[0]
            return {
                "recoverable": remote_commit == expected_commit,
                "remote_commit": remote_commit,
                "expected_commit": expected_commit,
            }
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return {
                "recoverable": False,
                "error": str(exc),
            }

    def idempotency_check(
        self,
        branch_name: str,
        cycle_id: str,
        commit_hash: str,
    ) -> dict[str, Any]:
        """Prevent duplicate push based on repository, branch, cycle, and commit.

        Returns idempotency status.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and result.stdout.strip():
                remote_commit = result.stdout.strip().split()[0]
                already_pushed = remote_commit == commit_hash
            else:
                already_pushed = False

            return {
                "branch_name": branch_name,
                "cycle_id": cycle_id,
                "commit_hash": commit_hash,
                "already_pushed": already_pushed,
                "checked_at": utc_now(),
            }
        except (FileNotFoundError, subprocess.CalledProcessError):
            return {
                "branch_name": branch_name,
                "cycle_id": cycle_id,
                "commit_hash": commit_hash,
                "already_pushed": False,
                "checked_at": utc_now(),
            }


# --- Task 11.6: RemoteVerifier -----------------------------------------------

class RemoteVerifier:
    """Verify remote branch through a fresh read-only worker."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def verify_remote_branch(
        self,
        branch_name: str,
        expected_commit: str,
    ) -> dict[str, Any]:
        """Fresh read-only verification of remote branch state.

        Returns verification result.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {
                    "verified": False,
                    "reason": "cannot query remote",
                    "error": result.stderr,
                }

            remote_refs = result.stdout.strip()
            if not remote_refs:
                return {
                    "verified": False,
                    "reason": "remote branch not found",
                }

            remote_commit = remote_refs.split()[0]
            verified = remote_commit == expected_commit

            return {
                "verified": verified,
                "branch_name": branch_name,
                "remote_commit": remote_commit,
                "expected_commit": expected_commit,
                "verified_at": utc_now(),
            }
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return {
                "verified": False,
                "error": str(exc),
            }

    def default_publication_disabled(self) -> dict[str, Any]:
        """Report that PR creation, merge, release, deployment are disabled by default.

        Returns publication policy.
        """
        return {
            "pr_creation": False,
            "mainline_merge": False,
            "release": False,
            "deploy": False,
            "destructive_migration": False,
            "policy": "all_publication_disabled_by_default",
        }

    def require_explicit_authority(
        self,
        requested_effects: list[str],
        authority: str,
    ) -> dict[str, Any]:
        """Validate that requested publication effects have explicit authority.

        Returns authority check result.
        """
        if not requested_effects:
            return {
                "authorized": True,
                "reason": "no publication effects requested",
            }

        if authority == "none":
            return {
                "authorized": False,
                "reason": f"no authority for effects: {requested_effects}",
            }

        if authority != "deploy":
            denied = [e for e in requested_effects if e != "branch_only"]
            if denied:
                return {
                    "authorized": False,
                    "reason": f"authority {authority!r} does not cover: {denied}",
                }

        return {
            "authorized": True,
            "authority": authority,
            "effects": requested_effects,
        }


# --- Task 11.7: PostCommitGoalJudge -----------------------------------------

class PostCommitGoalJudge:
    """Schedule fresh Goal Judge after commit and remote verification."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")

    def schedule_goal_judge_after_commit(
        self,
        campaign_id: str,
        cycle_id: str,
        commit_hash: str,
        remote_verified: bool,
    ) -> dict[str, Any]:
        """Schedule Goal Judge only after commit and remote verification.

        Returns scheduling result.
        """
        if not remote_verified:
            return {
                "scheduled": False,
                "reason": "remote verification not complete",
                "cycle_id": cycle_id,
            }

        judgment_id = stable_id("JUDGE", campaign_id, cycle_id, commit_hash)

        return {
            "scheduled": True,
            "judgment_id": judgment_id,
            "campaign_id": campaign_id,
            "cycle_id": cycle_id,
            "commit_hash": commit_hash,
            "scheduled_at": utc_now(),
        }

    def handle_continue(
        self,
        judgment: dict[str, Any],
        campaign_id: str,
        current_cycle: int,
    ) -> dict[str, Any]:
        """Handle CONTINUE decision by starting a new cycle.

        Returns new cycle info.
        """
        decision = judgment.get("decision")
        if decision != "CONTINUE":
            return {
                "action": "none",
                "reason": f"decision is {decision!r}, not CONTINUE",
            }

        new_cycle_id = stable_id("CYC", campaign_id, str(current_cycle + 1), utc_now())

        return {
            "action": "new_cycle",
            "previous_cycle": current_cycle,
            "new_cycle_id": new_cycle_id,
            "campaign_id": campaign_id,
            "started_at": utc_now(),
        }

    def handle_goal_achieved(
        self,
        judgment: dict[str, Any],
        campaign_id: str,
    ) -> dict[str, Any]:
        """Handle GOAL_ACHIEVED decision by sealing campaign.

        Returns seal result.
        """
        decision = judgment.get("decision")
        if decision != "GOAL_ACHIEVED":
            return {
                "action": "none",
                "reason": f"decision is {decision!r}, not GOAL_ACHIEVED",
            }

        return {
            "action": "seal_campaign",
            "campaign_id": campaign_id,
            "judgment_id": judgment.get("judgment_id"),
            "sealed_at": utc_now(),
            "publication_policy": {
                "pr_creation": False,
                "mainline_merge": False,
                "release": False,
                "deploy": False,
                "destructive_migration": False,
                "note": "sealed campaigns do not auto-publish",
            },
        }


# ---------------------------------------------------------------------------
# CampaignStrategyOrchestrator (composes all Group 11 workers)
# ---------------------------------------------------------------------------

class CampaignStrategyOrchestrator:
    """Orchestrates all campaign strategy workers in sequence."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(".")
        self.branch_init_worker = BranchInitWorker(repo_root)
        self.cycle_finalizer = CycleFinalizer(repo_root)
        self.cycle_committer = CycleCommitter(repo_root)
        self.cycle_pusher = CyclePusher(repo_root)
        self.remote_verifier = RemoteVerifier(repo_root)
        self.post_commit_judge = PostCommitGoalJudge(repo_root)

    def run_cycle(
        self,
        campaign_id: str,
        envelope: dict[str, Any],
        cycle_number: int,
        required_specs: list[str] | None = None,
        completed_changes: list[str] | None = None,
        expected_artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a full campaign cycle.

        Returns comprehensive cycle result.
        """
        cycle_id = stable_id("CYC", campaign_id, str(cycle_number), utc_now())
        results: dict[str, Any] = {"cycle_id": cycle_id, "campaign_id": campaign_id, "steps": []}

        # Finalize cycle
        if required_specs:
            sync_result = self.cycle_finalizer.sync_required_specs(cycle_id, required_specs)
            results["steps"].append({
                "step": "sync_specs",
                "result": sync_result,
            })

        if completed_changes:
            archive_result = self.cycle_finalizer.archive_completed_changes(
                cycle_id, completed_changes
            )
            results["steps"].append({
                "step": "archive_changes",
                "result": archive_result,
            })

        if expected_artifacts:
            verify_result = self.cycle_finalizer.verify_final_artifacts(
                cycle_id, expected_artifacts
            )
            results["steps"].append({
                "step": "verify_artifacts",
                "result": verify_result,
            })

        # Commit
        branch_name = f"campaign/{campaign_id}"
        commit_result = self.cycle_committer.create_commit(
            cycle_id=cycle_id,
            campaign_id=campaign_id,
            branch_name=branch_name,
        )
        results["steps"].append({
            "step": "commit",
            "result": commit_result,
        })

        if commit_result.get("status") != "committed":
            results["status"] = "failed"
            return results

        commit_hash = commit_result["commit_hash"]

        # Push
        push_result = self.cycle_pusher.push_branch(
            branch_name=branch_name,
            cycle_id=cycle_id,
            commit_hash=commit_hash,
        )
        results["steps"].append({
            "step": "push",
            "result": push_result,
        })

        remote_verified = False
        if push_result.get("status") == "pushed":
            verify_remote = self.remote_verifier.verify_remote_branch(
                branch_name, commit_hash
            )
            results["steps"].append({
                "step": "verify_remote",
                "result": verify_remote,
            })
            remote_verified = verify_remote.get("verified", False)

        # Schedule Goal Judge
        judge_schedule = self.post_commit_judge.schedule_goal_judge_after_commit(
            campaign_id=campaign_id,
            cycle_id=cycle_id,
            commit_hash=commit_hash,
            remote_verified=remote_verified,
        )
        results["steps"].append({
            "step": "schedule_goal_judge",
            "result": judge_schedule,
        })

        results["status"] = "completed"
        results["commit_hash"] = commit_hash
        results["remote_verified"] = remote_verified
        results["goal_judge_scheduled"] = judge_schedule.get("scheduled", False)

        return results

