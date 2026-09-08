# Strategy Reference

The canonical strategy definition and compiler are in
`scripts/strategy_v6.py`. This reference documents the default adaptive
strategy, compilation modes, and composition operations.

## Default Adaptive Strategy

The default strategy `default_adaptive` (version 1) defines ten phases:

| Phase | Kind | Role | Read-Only | Mandatory |
|-------|------|------|-----------|-----------|
| `proposal_explore` | proposal_explore | proposal_explore | yes | yes |
| `proposal_architect` | proposal_architect | proposal_architect | yes | yes |
| `proposal_finalize` | proposal_finalize | proposal_finalizer | yes | yes |
| `implementation_planning` | implementation_planning | work_planner_architect | yes | yes |
| `implementation` | implementation | implementation_worker | no | yes |
| `deterministic_checks` | deterministic_checks | deterministic_checker | yes | yes |
| `verification` | verification | verifier | yes | yes |
| `review` | review | implementation_review_architect | yes | yes |
| `finalization` | finalization | openspec_finalizer | no | yes |
| `goal_judge` | goal_judge | goal_judge | yes | yes |

Non-overridable phases: `verification`, `review`, `goal_judge`.

## Compilation Modes

| Mode | Phases Selected | Use Case |
|------|----------------|----------|
| `full_campaign` | All stable phases | Complete campaign execution |
| `proposal_only` | Phases with "proposal" in ID | Design-only campaigns |
| `implementation_from_proposal` | Phases without "proposal" | Implementation from existing proposal |
| `architect_review_only` | Review/architect phases | Read-only review |
| `resume` | All phases | Resume interrupted campaign |
| `custom` | User-specified subset | Specialized workflows |

## Composition Operations

| Operation | Effect | Constraint |
|-----------|--------|------------|
| `extend` | Insert phase after anchor | Anchor must exist |
| `replace` | Swap phase with new definition | Phase must not be non-overridable |
| `configure` | Update phase limits | Any phase |
| `disable` | Remove phase from strategy | Cannot disable first phase |

## Goal Judge Contract

The Goal Judge produces typed decisions:

- `GOAL_ACHIEVED` — requires accepted primary evidence
- `CONTINUE` — requires continuation_analysis with next_cycle_strategy
- `BLOCKED` — sealed terminal
- `INFEASIBLE` — sealed terminal
- `BLOCKED_NO_PROGRESS` — sealed terminal
- `BUDGET_EXHAUSTED` — sealed terminal

## Path Selection Rules

| Path | Conditions |
|------|-----------|
| `direct_repair` | local, reversible, no material change, single cause |
| `implementation_set` | known design, multiple components, cohesive |
| `openspec_batch` | material redesign or contract/migration/protocol/trust change |
| `no_safe_path` | no valid path satisfies conditions |
