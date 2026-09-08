# Architect Role Reference

The canonical enforcer is in `scripts/strategy_v6.py` (`ArchitectEnforcer`).
This reference documents Architect role boundaries, evidence requirements,
and prohibited patterns.

## Architect Roles

| Role | Purpose |
|------|---------|
| `proposal_explore` | Read-only workspace exploration |
| `proposal_architect` | Read-only architecture design |
| `proposal_finalizer` | Read-only proposal validation |
| `work_planner_architect` | Read-only work plan generation |
| `implementation_review_architect` | Read-only implementation review |
| `synthesis_architect` | Read-only hypothesis synthesis |
| `goal_judge` | Read-only goal assessment |

## Boundaries

### Read-Only Enforcement

Architect roles MUST NOT perform write actions:
- `write_file`, `create_file`, `modify_file`, `delete_file`

Architects produce analysis, findings, and plans. Implementation workers
execute the actual changes.

### Fresh Instances

Each Architect execution MUST be a fresh job instance. Reusing a previous
Architect job ID is forbidden. This prevents stale analysis from being
mistaken for current assessment.

### No Self-Verification

An Architect job MUST NOT verify its own output. Verification must be
performed by an independent Verifier job with a different job ID.

### No Self-Approval

An Architect job MUST NOT approve its own output. Approval must come
from a separate authority.

### Evidence-Based Findings

Every finding MUST include:
- `evidence` — concrete primary evidence references
- `consequence` — specific impact description
- `correction_objective` — actionable correction path

### Slogan Rejection

Findings containing only principle slogans without evidence are rejected:
- "follows best practices"
- "is not clean"
- "should be refactored"
- "violates principles"
- "too complex"
- "not simple"
- "needs improvement"
- "bad code"
- "code smell"
- "technical debt"

## Review Lenses

Architect reviews apply structured lenses:

| Lens | Focus |
|------|-------|
| Formal Gates | Gate condition satisfaction |
| KISS | Unnecessary complexity |
| SOLID | Design principle compliance |
| DRY | Unjustified duplication |
| YAGNI | Speculative generality |
| Cohesion | Module purpose alignment |
| Coupling | Inter-module dependencies |
| API Design | Contract consistency |
| Security | Security implications |
| Reliability | Error handling and failure modes |
| Performance | Performance implications |
| Operability | Operational concerns |
| Testing | Test coverage and quality |
| Documentation | Documentation completeness |
| Migration | Migration and upgrade paths |
| Dependencies | External dependency management |
| High-Level Design | Architectural quality |
| Long-Term Support | Maintainability |
