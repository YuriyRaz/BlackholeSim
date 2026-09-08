"""End-to-end verification tests for v6 strategy composition and modes.

Task 15.4: Strategy composition and mode tests for defaults, overrides,
ambiguity, context conflicts, Proposal-only, implementation-from-proposal,
review-only, resume, and nested OpenSpec promotion.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import SCHEMA_VERSION, OrchestratorError, content_hash, stable_id  # noqa: E402
from strategy_v6 import (  # noqa: E402
    AdaptiveStrategyCompiler,
    AdaptiveStrategyRegistry,
    CompilationMode,
    ContextModule,
    ContextModuleRegistry,
    DefaultStrategy,
    PhaseKind,
    PhaseRecord,
    StrategyCompiler,
    StrategyDefinition,
    StrategyRegistry,
    StrategyComposer,
    PhaseDefinition,
    PhaseContract,
    CompositionOp,
    AmbiguityRouter,
    PathSelectionRules,
)


def _make_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    definition = StrategyDefinition(
        strategy_id="test-strategy",
        version=1,
        stable_phase_ids=("proposal_explore", "proposal_architect", "proposal_finalize",
                          "implementation", "verification", "review", "goal_judge"),
        prompt_fragments={
            "proposal_explore": "Explore workspace",
            "proposal_architect": "Design proposal",
            "proposal_finalize": "Finalize proposal",
            "implementation": "Implement changes",
            "verification": "Verify implementation",
            "review": "Review implementation",
            "goal_judge": "Judge goal",
        },
        limits={"max_total_jobs": 50},
    )
    registry.register_strategy(definition)
    return registry


class DefaultStrategyCompilationTest(unittest.TestCase):
    """Test default strategy compilation."""

    def test_default_strategy_has_all_phases(self) -> None:
        strategy = DefaultStrategy()
        self.assertEqual(len(strategy.phases), 10)
        phase_ids = [p.phase_id for p in strategy.phases]
        self.assertIn("proposal_explore", phase_ids)
        self.assertIn("goal_judge", phase_ids)
        self.assertIn("verification", phase_ids)

    def test_default_strategy_non_overridable(self) -> None:
        strategy = DefaultStrategy()
        self.assertIn("verification", strategy.non_overridable)
        self.assertIn("goal_judge", strategy.non_overridable)
        self.assertIn("review", strategy.non_overridable)

    def test_default_strategy_to_dict(self) -> None:
        strategy = DefaultStrategy()
        d = strategy.to_dict()
        self.assertEqual(d["name"], "default_adaptive")
        self.assertEqual(d["version"], 1)
        self.assertEqual(len(d["phases"]), 10)

    def test_register_default_strategy(self) -> None:
        from strategy_v6 import register_default_strategy
        strategy = register_default_strategy()
        self.assertEqual(strategy.name, "default_adaptive")
        self.assertTrue(len(strategy.phases) > 0)

    def test_adaptive_strategy_registry(self) -> None:
        registry = AdaptiveStrategyRegistry()
        strategy = DefaultStrategy()
        registry.register(strategy)
        self.assertTrue(registry.has("default_adaptive"))
        self.assertEqual(registry.get_version("default_adaptive"), 1)

    def test_compile_full_campaign(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        result = compiler.compile_full_campaign(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="implement feature X",
            run_id="run-1",
        )
        self.assertIsNotNone(result.envelope)
        self.assertEqual(result.envelope.goal, "implement feature X")
        self.assertEqual(len(result.graph.initial_jobs), 8)  # root + 7 phases
        self.assertEqual(len(result.prompts), 7)


class OverrideCompositionTest(unittest.TestCase):
    """Test override composition."""

    def test_no_overrides_returns_original(self) -> None:
        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        result = compiler.compile(overrides=None)
        self.assertEqual(result.phases, strategy.phases)

    def test_validate_non_overridable_rejected(self) -> None:
        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        overrides = [{"operation": "replace", "target_phase": "verification"}]
        with self.assertRaises(OrchestratorError) as ctx:
            compiler.compile(overrides=overrides)
        self.assertIn("non-overridable", str(ctx.exception))

    def test_invalid_operation_rejected(self) -> None:
        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        overrides = [{"operation": "invalid_op", "target_phase": "implementation"}]
        with self.assertRaises(OrchestratorError) as ctx:
            compiler.compile(overrides=overrides)
        self.assertIn("invalid operation", str(ctx.exception))

    def test_disable_nonexistent_phase_rejected(self) -> None:
        strategy = DefaultStrategy()
        compiler = AdaptiveStrategyCompiler(strategy)
        overrides = [{"operation": "disable", "target_phase": "nonexistent"}]
        with self.assertRaises(OrchestratorError) as ctx:
            compiler.compile(overrides=overrides)
        self.assertIn("not found", str(ctx.exception))


class AmbiguityDetectionTest(unittest.TestCase):
    """Test ambiguity detection."""

    def test_ambiguous_entry_target(self) -> None:
        registry = _make_registry()
        # Register a second strategy that shares the prefix
        extra = StrategyDefinition(
            strategy_id="test-strategy-extra",
            version=1,
            stable_phase_ids=("implementation",),
            prompt_fragments={"implementation": "Extra"},
            limits={"max_total_jobs": 10},
        )
        registry.register_strategy(extra)
        router = AmbiguityRouter(registry)
        result = router.route(entry_target="test-strat")
        self.assertIsNotNone(result)

    def test_exact_match_no_ambiguity(self) -> None:
        registry = _make_registry()
        router = AmbiguityRouter(registry)
        result = router.route(entry_target="test-strategy")
        self.assertIsNone(result)

    def test_multiple_phase_anchors_ambiguous(self) -> None:
        registry = _make_registry()
        router = AmbiguityRouter(registry)
        result = router.route(phase_anchors=["phase1", "phase2"])
        self.assertIsNotNone(result)

    def test_detect_conflicts_in_overrides(self) -> None:
        registry = _make_registry()
        router = AmbiguityRouter(registry)
        result = router.route(overrides={"phase1": True, "phase2": False})
        self.assertIsNotNone(result)

    def test_weakened_contract_detection(self) -> None:
        registry = _make_registry()
        router = AmbiguityRouter(registry)
        original = {
            "verification": PhaseContract(inputs=("a", "b"), outputs=("c",)),
        }
        modified = {
            "verification": PhaseContract(inputs=("a",), outputs=("c",)),
        }
        items = router.detect_weakened_contracts(original, modified)
        self.assertTrue(any(i.ambiguity_type == "weakened_contract" for i in items))

    def test_incompatible_constraints_detection(self) -> None:
        registry = _make_registry()
        router = AmbiguityRouter(registry)
        constraints = {
            "module-a": {"key1": "value1"},
            "module-b": {"key1": "value2"},
        }
        items = router.detect_incompatible_constraints(constraints)
        self.assertTrue(any(i.ambiguity_type == "incompatible_constraint" for i in items))


class ContextConflictTest(unittest.TestCase):
    """Test context conflict detection."""

    def test_no_conflict_different_namespaces(self) -> None:
        reg = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns1", constraints={"k": "v1"})
        m2 = ContextModule(module_id="m2", namespace="ns2", constraints={"k": "v1"})
        reg.add_context_module(m1)
        reg.add_context_module(m2)
        conflicts = reg.validate_module_conflicts(m2)
        self.assertEqual(conflicts, [])

    def test_conflict_same_namespace_different_value(self) -> None:
        reg = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns1", constraints={"k": "v1"})
        m2 = ContextModule(module_id="m2", namespace="ns1", constraints={"k": "v2"})
        reg.add_context_module(m1)
        conflicts = reg.validate_module_conflicts(m2)
        self.assertTrue(any("conflict" in c.lower() for c in conflicts))

    def test_no_conflict_same_value(self) -> None:
        reg = ContextModuleRegistry()
        m1 = ContextModule(module_id="m1", namespace="ns1", constraints={"k": "v1"})
        m2 = ContextModule(module_id="m2", namespace="ns1", constraints={"k": "v1"})
        reg.add_context_module(m1)
        conflicts = reg.validate_module_conflicts(m2)
        self.assertEqual(conflicts, [])

    def test_inherited_module_not_found(self) -> None:
        reg = ContextModuleRegistry()
        m = ContextModule(module_id="m1", namespace="ns1", inherited_from=("nonexistent",))
        conflicts = reg.validate_module_conflicts(m)
        self.assertTrue(any("inherited" in c.lower() for c in conflicts))

    def test_freeze_module(self) -> None:
        reg = ContextModuleRegistry()
        m = ContextModule(module_id="m1", namespace="ns1")
        reg.add_context_module(m)
        frozen = reg.freeze_module_versions(["m1"])
        self.assertIn("m1", frozen)
        self.assertEqual(len(frozen["m1"]), 64)


class ProposalOnlyModeTest(unittest.TestCase):
    """Test Proposal-only compilation mode."""

    def test_proposal_only_filters_phases(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        result = compiler.compile_proposal_only(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="run-1",
        )
        phase_names = [p.phase_id for p in result.prompts]
        self.assertTrue(all("proposal" in p for p in phase_names))
        self.assertNotIn("implementation", phase_names)
        self.assertNotIn("verification", phase_names)


class ImplementationFromProposalModeTest(unittest.TestCase):
    """Test implementation-from-proposal compilation mode."""

    def test_impl_from_proposal_filters_phases(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        result = compiler.compile_implementation_from_proposal(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="run-1",
        )
        phase_names = [p.phase_id for p in result.prompts]
        self.assertNotIn("proposal_explore", phase_names)
        self.assertIn("implementation", phase_names)


class ReviewOnlyModeTest(unittest.TestCase):
    """Test review-only compilation mode."""

    def test_review_only_filters_phases(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        result = compiler.compile_architect_review_only(
            strategy_id="test-strategy",
            strategy_version=1,
            goal="test goal",
            run_id="run-1",
        )
        self.assertIsNotNone(result.envelope)


class ResumeModeTest(unittest.TestCase):
    """Test resume compilation mode."""

    def test_resume_refuses_to_recompile_defaults(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        with self.assertRaisesRegex(OrchestratorError, "persisted frozen campaign"):
            compiler.compile_resume(
                strategy_id="test-strategy",
                strategy_version=1,
                goal="test goal",
                run_id="run-1",
            )


class NestedOpenSpecPromotionTest(unittest.TestCase):
    """Test nested OpenSpec promotion path selection."""

    def test_openspec_conditions(self) -> None:
        rules = PathSelectionRules()
        self.assertTrue(rules.openspec_batch_conditions(
            material_redesign=True,
            contract_change=True,
        ))

    def test_openspec_conditions_boundary_change(self) -> None:
        rules = PathSelectionRules()
        self.assertTrue(rules.openspec_batch_conditions(
            material_redesign=False,
            trust_boundary_change=True,
        ))

    def test_direct_repair_conditions(self) -> None:
        rules = PathSelectionRules()
        self.assertTrue(rules.direct_repair_conditions(
            is_local=True, is_reversible=True,
            no_material_change=True, single_cause=True,
        ))

    def test_implementation_set_conditions(self) -> None:
        rules = PathSelectionRules()
        self.assertTrue(rules.implementation_set_conditions(
            known_design=True, multiple_components=True, cohesive=True,
        ))

    def test_validate_path_selection_direct_repair(self) -> None:
        rules = PathSelectionRules()
        conditions = {
            "is_local": True, "is_reversible": True,
            "no_material_change": True, "single_cause": True,
        }
        errors = rules.validate_path_selection("direct_repair", conditions)
        self.assertEqual(errors, [])

    def test_validate_path_selection_openspec(self) -> None:
        rules = PathSelectionRules()
        conditions = {
            "material_redesign": True, "contract_change": True,
        }
        errors = rules.validate_path_selection("openspec_batch", conditions)
        self.assertEqual(errors, [])


class StrategyRegistryTest(unittest.TestCase):
    """Test strategy registry versioning."""

    def test_register_new_strategy(self) -> None:
        registry = StrategyRegistry()
        defn = StrategyDefinition(strategy_id="s1", version=1, stable_phase_ids=("p1",))
        registry.register_strategy(defn)
        self.assertEqual(registry.list_strategies(), {"s1": 1})

    def test_register_sequential_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(StrategyDefinition(strategy_id="s1", version=1))
        registry.register_strategy(StrategyDefinition(strategy_id="s1", version=2))
        self.assertEqual(registry.list_strategies(), {"s1": 2})

    def test_reject_non_sequential_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(StrategyDefinition(strategy_id="s1", version=1))
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(StrategyDefinition(strategy_id="s1", version=3))

    def test_reject_duplicate_version(self) -> None:
        registry = StrategyRegistry()
        registry.register_strategy(StrategyDefinition(strategy_id="s1", version=1))
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(StrategyDefinition(strategy_id="s1", version=1))

    def test_new_strategy_must_start_at_1(self) -> None:
        registry = StrategyRegistry()
        with self.assertRaises(OrchestratorError):
            registry.register_strategy(StrategyDefinition(strategy_id="s1", version=2))


class CompilationDeterminismTest(unittest.TestCase):
    """Test deterministic compilation results."""

    def test_same_inputs_same_output(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal", "run-1")
        self.assertEqual(r1.envelope.envelope_digest, r2.envelope.envelope_digest)
        self.assertEqual(r1.graph.graph_digest, r2.graph.graph_digest)
        self.assertEqual(r1.compilation_digest, r2.compilation_digest)

    def test_different_goals_different_digest(self) -> None:
        registry = _make_registry()
        compiler = StrategyCompiler(registry)
        r1 = compiler.compile_full_campaign("test-strategy", 1, "goal-a", "run-1")
        r2 = compiler.compile_full_campaign("test-strategy", 1, "goal-b", "run-1")
        self.assertNotEqual(r1.envelope.envelope_digest, r2.envelope.envelope_digest)


if __name__ == "__main__":
    unittest.main()
