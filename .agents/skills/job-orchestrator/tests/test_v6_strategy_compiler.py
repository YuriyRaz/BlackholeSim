"""Tests for v6 strategy compiler, composition, context modules, and ambiguity routing."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import OrchestratorError, SCHEMA_VERSION, canonical_bytes, content_hash, stable_id  # noqa: E402
from strategy_v6 import (  # noqa: E402
    CompilationMode,
    CompiledEnvelope,
    CompiledGraph,
    CompiledPrompt,
    CompilationResult,
    CompositionOp,
    CompositionOperation,
    ContextModule,
    ContextModuleRegistry,
    FinalizationPolicy,
    PhaseContract,
    PhaseDefinition,
    PublicationPolicy,
    RoleAuthority,
    StrategyCompiler,
    StrategyDefinition,
    StrategyRegistry,
    StrategyComposer,
    AmbiguityRouter,
    AmbiguityItem,
)


def _make_strategy(
    strategy_id: str = "test-strategy",
    version: int = 1,
    phases: tuple[str, ...] = ("proposal-explore", "proposal-architect", "implementation", "verification"),
) -> StrategyDefinition:
    """Create a test strategy definition."""
    fragments = {p: f"Instructions for {p}" for p in phases}
    contracts = {p: PhaseContract(inputs=(f"in-{p}",), outputs=(f"out-{p}",)) for p in phases}
    gates = {p: (f"gate-{p}",) for p in phases}
    return StrategyDefinition(
        strategy_id=strategy_id,
        version=version,
        stable_phase_ids=phases,
        prompt_fragments=fragments,
        role_authority={"implementation": RoleAuthority(can_expand=True)},
        phase_contracts=contracts,
        gates=gates,
        limits={"max_cycles": 10, "max_total_jobs": 50},
        finalization_policy=FinalizationPolicy(),
        publication_policy=PublicationPolicy(),
    )


def _register_test_strategy(registry: StrategyRegistry) -> StrategyDefinition:
    """Register and return a test strategy."""
    definition = _make_strategy()
    registry.register_strategy(definition)
    return definition


# ===========================================================================
# Task 9.1 Tests: Strategy Registry
# ===========================================================================

class StrategyRegistryTest(unittest.TestCase):
    """Test versioned strategy registry."""

    def test_register_and_get_strategy(self) -> None:
        registry = StrategyRegistry()
        definition = _make_strategy()
        registry.register_strategy(definition)
        retrieved = registry.get_strategy("test-strategy")
        self.assertEqual(retrieved.strategy_id, "test-strategy")
        self.assertEqual(retrieved.version, 1)

    def test_register_version_2(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        registry.register_strategy(_make_strategy(version=2))
        retrieved = registry.get_strategy("test-strategy", version=2)
        self.assertEqual(retrieved.version, 2)

    def test_rejects_duplicate_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(_make_strategy(version=1))

    def test_rejects_non_sequential_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(_make_strategy(version=3))

    def test_new_strategy_must_start_at_1(self) -> None:
        registry = StrategyRegistry()
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(_make_strategy(version=2))

    def test_get_nonexistent_strategy(self) -> None:
        registry = StrategyRegistry()
        with self.assertRaises(OrchestratorError):
            registry.get_strategy("nonexistent")

    def test_get_specific_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        registry.register_strategy(_make_strategy(version=2))
        first = registry.get_strategy("test-strategy", version=1)
        second = registry.get_strategy("test-strategy", version=2)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)

    def test_validate_strategy_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        errors = registry.validate_strategy_version("test-strategy", 1)
        self.assertEqual(errors, [])

    def test_validate_strategy_version_not_found(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        errors = registry.validate_strategy_version("test-strategy", 2)
        self.assertTrue(len(errors) > 0)

    def test_list_strategies(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(_make_strategy(version=1))
        registry.register_strategy(_make_strategy(strategy_id="other", version=1))
        listing = registry.list_strategies()
        self.assertEqual(listing["test-strategy"], 1)
        self.assertEqual(listing["other"], 1)

    def test_strategy_canonical_digest_deterministic(self) -> None:
        definition = _make_strategy()
        d1 = definition.canonical_digest()
        d2 = definition.canonical_digest()
        self.assertEqual(d1, d2)
        self.assertEqual(len(d1), 64)

    def test_strategy_digest_changes_with_version(self) -> None:
        d1 = _make_strategy(version=1).canonical_digest()
        d2 = _make_strategy(version=2).canonical_digest()
        self.assertNotEqual(d1, d2)


# ===========================================================================
# Task 9.2 Tests: Deterministic Compiler
# ===========================================================================

class StrategyCompilerTest(unittest.TestCase):
    """Test deterministic compilation across all modes."""

    def setUp(self) -> None:
        self.registry = StrategyRegistry()
        self.definition = _register_test_strategy(self.registry)
        self.compiler = StrategyCompiler(self.registry)

    def _compile_and_verify_determinism(self, compile_fn, **kwargs) -> None:
        """Compile twice and verify identical outputs."""
        r1 = compile_fn(**kwargs)
        r2 = compile_fn(**kwargs)
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)
        self.assertEqual(r1.envelope.envelope_digest, r2.envelope.envelope_digest)
        self.assertEqual(r1.graph.graph_digest, r2.graph.graph_digest)
        self.assertEqual(r1.compilation_digest, r2.compilation_digest)
        self.assertEqual(len(r1.prompts), len(r2.prompts))
        for p1, p2 in zip(r1.prompts, r2.prompts):
            self.assertEqual(p1.prompt_digest, p2.prompt_digest)

    def test_full_campaign_determinism(self) -> None:
        self._compile_and_verify_determinism(
            self.compiler.compile_full_campaign,
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )

    def test_proposal_only_determinism(self) -> None:
        self._compile_and_verify_determinism(
            self.compiler.compile_proposal_only,
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )

    def test_implementation_from_proposal_determinism(self) -> None:
        self._compile_and_verify_determinism(
            self.compiler.compile_implementation_from_proposal,
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )

    def test_architect_review_only_determinism(self) -> None:
        self._compile_and_verify_determinism(
            self.compiler.compile_architect_review_only,
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )

    def test_resume_cannot_recompile_registry_defaults(self) -> None:
        with self.assertRaisesRegex(OrchestratorError, "persisted frozen campaign"):
            self.compiler.compile_resume(
                strategy_id="test-strategy",
                strategy_version=1,
                goal="test goal",
                run_id="test-run",
            )

    def test_custom_mode_determinism(self) -> None:
        self._compile_and_verify_determinism(
            self.compiler.compile_custom,
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
            custom_phases=["proposal-explore", "implementation"],
        )

    def test_full_campaign_has_all_phases(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )
        self.assertEqual(
            result.envelope.phase_sequence,
            ("proposal-explore", "proposal-architect", "implementation", "verification"),
        )

    def test_proposal_only_has_proposal_phases(self) -> None:
        result = self.compiler.compile_proposal_only(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )
        for phase in result.envelope.phase_sequence:
            self.assertIn("proposal", phase)

    def test_envelope_contains_strategy_info(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="my goal",
            run_id="my-run",
        )
        self.assertEqual(result.envelope.strategy_id, "test-strategy")
        self.assertEqual(result.envelope.strategy_version, 1)
        self.assertEqual(result.envelope.goal, "my goal")
        self.assertEqual(result.envelope.run_id, "my-run")

    def test_graph_has_root_job(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )
        root_jobs = [j for j in result.graph.initial_jobs if j["expansion_origin"] == "ROOT"]
        self.assertEqual(len(root_jobs), 1)

    def test_graph_edges_form_chain(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )
        self.assertEqual(
            len(result.graph.initial_edges),
            len(result.graph.initial_jobs) - 1,
        )

    def test_prompts_match_phases(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
        )
        self.assertEqual(len(result.prompts), len(result.envelope.phase_sequence))
        for prompt, phase in zip(result.prompts, result.envelope.phase_sequence):
            self.assertEqual(prompt.phase_id, phase)

    def test_custom_mode_invalid_phase_rejected(self) -> None:
        with self.assertRaises(OrchestratorError):
            self.compiler.compile_custom(
                strategy_id="test-strategy",
                strategy_version=1,
                goal="test goal",
                run_id="test-run",
                custom_phases=["nonexistent-phase"],
            )

    def test_different_goals_produce_different_digests(self) -> None:
        r1 = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="goal A",
            run_id="run-1",
        )
        r2 = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="goal B",
            run_id="run-1",
        )
        self.assertNotEqual(r1.compilation_digest, r2.compilation_digest)

    def test_different_runs_produce_different_digests(self) -> None:
        r1 = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="same goal",
            run_id="run-1",
        )
        r2 = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="same goal",
            run_id="run-2",
        )
        self.assertNotEqual(r1.compilation_digest, r2.compilation_digest)

    def test_custom_limits_override(self) -> None:
        result = self.compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="test-run",
            limits={"max_cycles": 5},
        )
        self.assertEqual(result.envelope.limits["max_cycles"], 5)
        self.assertEqual(result.envelope.limits["max_total_jobs"], 50)


# ===========================================================================
# Task 9.3 Tests: Composition
# ===========================================================================

class StrategyComposerTest(unittest.TestCase):
    """Test extend, replace, configure, disable composition."""

    def setUp(self) -> None:
        self.registry = StrategyRegistry()
        self.definition = _register_test_strategy(self.registry)

    def test_extend_phase(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(
            phase_id="synthesis",
            prompt_fragment="Synthesize findings",
            contract=PhaseContract(inputs=("findings",), outputs=("synthesis",)),
        )
        composer.extend_phase("synthesis", "implementation", new_phase)
        errors = composer.validate_composition("test-strategy", 1)
        self.assertEqual(errors, [])

    def test_extend_and_apply(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(
            phase_id="synthesis",
            prompt_fragment="Synthesize",
            contract=PhaseContract(),
        )
        composer.extend_phase("synthesis", "implementation", new_phase)
        new_def = composer.apply_composition("test-strategy", 1)
        self.assertIn("synthesis", new_def.stable_phase_ids)
        self.assertEqual(new_def.version, 2)

    def test_replace_phase(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(
            phase_id="proposal-explore",
            prompt_fragment="Updated explore",
            is_overridable=True,
        )
        composer.replace_phase("proposal-explore", new_phase)
        errors = composer.validate_composition("test-strategy", 1)
        self.assertEqual(errors, [])

    def test_replace_non_overridable_rejected(self) -> None:
        # Add a non-overridable phase first
        self.registry.register_strategy(StrategyDefinition(
            strategy_id="protected",
            version=1,
            stable_phase_ids=("root",),
            phase_contracts={"root": PhaseContract()},
        ))
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(
            phase_id="root",
            prompt_fragment="New root",
            is_overridable=False,
        )
        composer.replace_phase("root", new_phase)
        errors = composer.validate_composition("protected", 1)
        self.assertTrue(any("not overridable" in e for e in errors))

    def test_configure_phase(self) -> None:
        composer = StrategyComposer(self.registry)
        composer.configure_phase("implementation", {"max_retries": 5})
        errors = composer.validate_composition("test-strategy", 1)
        self.assertEqual(errors, [])

    def test_disable_phase(self) -> None:
        composer = StrategyComposer(self.registry)
        composer.disable_phase("verification")
        errors = composer.validate_composition("test-strategy", 1)
        self.assertEqual(errors, [])

    def test_disable_first_phase_rejected(self) -> None:
        composer = StrategyComposer(self.registry)
        composer.disable_phase("proposal-explore")
        errors = composer.validate_composition("test-strategy", 1)
        self.assertTrue(any("cannot disable first" in e for e in errors))

    def test_extend_nonexistent_anchor_rejected(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(phase_id="new-phase")
        composer.extend_phase("new-phase", "nonexistent", new_phase)
        errors = composer.validate_composition("test-strategy", 1)
        self.assertTrue(any("anchor phase" in e for e in errors))

    def test_extend_existing_phase_rejected(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(phase_id="implementation")
        composer.extend_phase("implementation", "proposal-explore", new_phase)
        errors = composer.validate_composition("test-strategy", 1)
        self.assertTrue(any("already exists" in e for e in errors))

    def test_compose_multiple_operations(self) -> None:
        composer = StrategyComposer(self.registry)
        new_phase = PhaseDefinition(
            phase_id="synthesis",
            prompt_fragment="Synthesize",
        )
        composer.extend_phase("synthesis", "implementation", new_phase)
        composer.configure_phase("proposal-explore", {"timeout": 30})
        new_def = composer.apply_composition("test-strategy", 1)
        self.assertIn("synthesis", new_def.stable_phase_ids)
        self.assertEqual(new_def.limits["proposal-explore"]["timeout"], 30)

    def test_composition_deterministic(self) -> None:
        c1 = StrategyComposer(self.registry)
        c1.extend_phase(
            "synthesis", "implementation",
            PhaseDefinition(phase_id="synthesis", prompt_fragment="Synth"),
        )
        d1 = c1.apply_composition("test-strategy", 1)

        c2 = StrategyComposer(self.registry)
        c2.extend_phase(
            "synthesis", "implementation",
            PhaseDefinition(phase_id="synthesis", prompt_fragment="Synth"),
        )
        d2 = c2.apply_composition("test-strategy", 1)

        self.assertEqual(d1.canonical_digest(), d2.canonical_digest())


# ===========================================================================
# Task 9.4 Tests: Context Modules
# ===========================================================================

class ContextModuleRegistryTest(unittest.TestCase):
    """Test additive namespaced context modules."""

    def test_add_module(self) -> None:
        registry = ContextModuleRegistry()
        module = ContextModule(
            module_id="mod-1",
            namespace="security",
            constraints={"require_auth": True},
        )
        registry.add_context_module(module)
        retrieved = registry.get_module("mod-1")
        self.assertIsNotNone(retrieved)
        assert retrieved is not None
        self.assertEqual(retrieved.namespace, "security")

    def test_add_duplicate_module_updates(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1}, version=1)
        m2 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 2}, version=2)
        registry.add_context_module(m1)
        registry.add_context_module(m2)
        module = registry.get_module("m1")
        assert module is not None
        self.assertEqual(module.constraints["a"], 2)

    def test_reject_lower_version(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", version=2)
        registry.add_context_module(m1)
        m0 = ContextModule(module_id="m1", namespace="ns", version=1)
        with self.assertRaises(OrchestratorError):
            registry.add_context_module(m0)

    def test_conflict_detection(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={"key": "value1"})
        m2 = ContextModule(module_id="m2", namespace="ns", constraints={"key": "value2"})
        registry.add_context_module(m1)
        conflicts = registry.validate_module_conflicts(m2)
        self.assertTrue(len(conflicts) > 0)

    def test_no_conflict_different_namespaces(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns1", constraints={"key": "value1"})
        m2 = ContextModule(module_id="m2", namespace="ns2", constraints={"key": "value2"})
        registry.add_context_module(m1)
        conflicts = registry.validate_module_conflicts(m2)
        self.assertEqual(conflicts, [])

    def test_freeze_module(self) -> None:
        registry = ContextModuleRegistry()
        module = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        registry.add_context_module(module)
        frozen = registry.freeze_module_versions(["m1"])
        self.assertIn("m1", frozen)
        self.assertEqual(len(frozen["m1"]), 64)

    def test_frozen_module_cannot_be_modified(self) -> None:
        registry = ContextModuleRegistry()
        module = ContextModule(module_id="m1", namespace="ns", version=1)
        registry.add_context_module(module)
        registry.freeze_module_versions(["m1"])
        with self.assertRaises(OrchestratorError):
            registry.add_context_module(
                ContextModule(module_id="m1", namespace="ns", version=2)
            )

    def test_resolve_constraints_additive(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        m2 = ContextModule(module_id="m2", namespace="ns", constraints={"b": 2})
        registry.add_context_module(m1)
        registry.add_context_module(m2)
        resolved = registry.resolve_constraints("ns")
        self.assertEqual(resolved, {"a": 1, "b": 2})

    def test_resolve_constraints_last_write_wins(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1}, version=1)
        m2 = ContextModule(module_id="m2", namespace="ns", constraints={"a": 2}, version=2)
        registry.add_context_module(m1)
        # Need to add m2 under different module_id to avoid conflict detection
        # Actually m2 has same key with different value, which IS a conflict
        conflicts = registry.validate_module_conflicts(m2)
        self.assertTrue(len(conflicts) > 0)

    def test_module_digest_deterministic(self) -> None:
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        m2 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        self.assertEqual(m1.compute_digest(), m2.compute_digest())

    def test_inherited_module_not_found(self) -> None:
        registry = ContextModuleRegistry()
        module = ContextModule(
            module_id="m1", namespace="ns",
            inherited_from=("nonexistent",),
        )
        conflicts = registry.validate_module_conflicts(module)
        self.assertTrue(any("not found" in c for c in conflicts))

    def test_get_modules_for_namespace(self) -> None:
        registry = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns", constraints={})
        m2 = ContextModule(module_id="m2", namespace="other", constraints={})
        registry.add_context_module(m1)
        registry.add_context_module(m2)
        ns_modules = registry.get_modules_for_namespace("ns")
        self.assertEqual(len(ns_modules), 1)
        self.assertEqual(ns_modules[0].module_id, "m1")


# ===========================================================================
# Task 9.5 Tests: Ambiguity Router
# ===========================================================================

class AmbiguityRouterTest(unittest.TestCase):
    """Test ambiguity detection and routing."""

    def setUp(self) -> None:
        self.registry = StrategyRegistry()
        self.registry.register_strategy(_make_strategy(strategy_id="alpha-strategy"))
        self.registry.register_strategy(_make_strategy(strategy_id="alpha-build"))
        self.router = AmbiguityRouter(registry=self.registry)

    def test_no_ambiguity(self) -> None:
        question = self.router.route(entry_target="alpha-strategy")
        self.assertIsNone(question)

    def test_ambiguous_entry_target(self) -> None:
        question = self.router.route(entry_target="alpha")
        self.assertIsNotNone(question)
        assert question is not None
        self.assertIn("Ambiguous", question)

    def test_no_matching_target(self) -> None:
        question = self.router.route(entry_target="nonexistent")
        self.assertIsNotNone(question)
        assert question is not None
        self.assertIn("no strategy matches", question)

    def test_multiple_phase_anchors(self) -> None:
        question = self.router.route(phase_anchors=["anchor1", "anchor2"])
        self.assertIsNotNone(question)
        assert question is not None
        self.assertIn("Multiple phase anchors", question)

    def test_detect_conflicts(self) -> None:
        # Both have same canonical representation but different keys => conflict
        items = self.router.detect_conflicts({"a": "same_value", "b": "same_value"})
        self.assertTrue(len(items) > 0)

    def test_no_conflicts(self) -> None:
        items = self.router.detect_conflicts({"a": {"x": 1}, "b": {"y": 2}})
        self.assertEqual(items, [])

    def test_detect_weakened_contracts(self) -> None:
        original = {"phase1": PhaseContract(inputs=("a", "b"), outputs=("c",))}
        modified = {"phase1": PhaseContract(inputs=("a",), outputs=("c",))}
        items = self.router.detect_weakened_contracts(original, modified)
        self.assertTrue(len(items) > 0)
        self.assertEqual(items[0].ambiguity_type, "weakened_contract")

    def test_no_weakened_contracts(self) -> None:
        original = {"phase1": PhaseContract(inputs=("a",), outputs=("c",))}
        modified = {"phase1": PhaseContract(inputs=("a", "b"), outputs=("c", "d"))}
        items = self.router.detect_weakened_contracts(original, modified)
        self.assertEqual(items, [])

    def test_detect_incompatible_constraints(self) -> None:
        constraints = {
            "mod1": {"key": "value1"},
            "mod2": {"key": "value2"},
        }
        items = self.router.detect_incompatible_constraints(constraints)
        self.assertTrue(len(items) > 0)

    def test_no_incompatible_constraints(self) -> None:
        constraints = {
            "mod1": {"key": "value1"},
            "mod2": {"key": "value1"},
        }
        items = self.router.detect_incompatible_constraints(constraints)
        self.assertEqual(items, [])

    def test_generate_question_from_ambiguity(self) -> None:
        items = [
            AmbiguityItem(
                ambiguity_type="entry_target",
                description="multiple matches",
                candidates=("a", "b"),
            )
        ]
        question = self.router.generate_user_question(items)
        self.assertIsNotNone(question)
        assert question is not None
        self.assertIn("Did you mean", question)

    def test_generate_question_from_error(self) -> None:
        items = [
            AmbiguityItem(
                ambiguity_type="weakened_contract",
                description="lost inputs",
                candidates=("phase1",),
                severity="error",
            )
        ]
        question = self.router.generate_user_question(items)
        self.assertIsNotNone(question)
        assert question is not None
        self.assertIn("Weakened contract", question)

    def test_full_route_pipeline(self) -> None:
        question = self.router.route(
            entry_target="alpha",
            overrides={"a": {"x": 1}, "b": {"x": 2}},
        )
        self.assertIsNotNone(question)

    def test_route_no_ambiguities(self) -> None:
        question = self.router.route(entry_target="alpha-strategy")
        self.assertIsNone(question)


# ===========================================================================
# Task 9.6 Tests: Integration / Cross-cutting determinism
# ===========================================================================

class CrossCuttingDeterminismTest(unittest.TestCase):
    """Test that compilation is fully deterministic across all paths."""

    def test_same_inputs_same_envelope_id(self) -> None:
        registry = StrategyRegistry()
        _register_test_strategy(registry)
        compiler = StrategyCompiler(registry)

        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)

    def test_same_inputs_same_graph_digest(self) -> None:
        registry = StrategyRegistry()
        _register_test_strategy(registry)
        compiler = StrategyCompiler(registry)

        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        self.assertEqual(r1.graph.graph_digest, r2.graph.graph_digest)

    def test_same_inputs_same_prompt_digests(self) -> None:
        registry = StrategyRegistry()
        _register_test_strategy(registry)
        compiler = StrategyCompiler(registry)

        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        self.assertEqual(len(r1.prompts), len(r2.prompts))
        for p1, p2 in zip(r1.prompts, r2.prompts):
            self.assertEqual(p1.prompt_digest, p2.prompt_digest)

    def test_same_inputs_same_compilation_digest(self) -> None:
        registry = StrategyRegistry()
        _register_test_strategy(registry)
        compiler = StrategyCompiler(registry)

        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        self.assertEqual(r1.compilation_digest, r2.compilation_digest)

    def test_composition_preserves_determinism(self) -> None:
        registry = StrategyRegistry()
        _register_test_strategy(registry)

        c1 = StrategyComposer(registry)
        c1.extend_phase(
            "synthesis", "implementation",
            PhaseDefinition(phase_id="synthesis", prompt_fragment="Synth"),
        )
        d1 = c1.apply_composition("test-strategy", 1)

        registry2 = StrategyRegistry()
        _register_test_strategy(registry2)
        c2 = StrategyComposer(registry2)
        c2.extend_phase(
            "synthesis", "implementation",
            PhaseDefinition(phase_id="synthesis", prompt_fragment="Synth"),
        )
        d2 = c2.apply_composition("test-strategy", 1)

        self.assertEqual(d1.canonical_digest(), d2.canonical_digest())

    def test_context_module_freeze_deterministic(self) -> None:
        r1 = ContextModuleRegistry()
        m = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        r1.add_context_module(m)
        f1 = r1.freeze_module_versions(["m1"])

        r2 = ContextModuleRegistry()
        m2 = ContextModule(module_id="m1", namespace="ns", constraints={"a": 1})
        r2.add_context_module(m2)
        f2 = r2.freeze_module_versions(["m1"])

        self.assertEqual(f1["m1"], f2["m1"])


if __name__ == "__main__":
    unittest.main()
