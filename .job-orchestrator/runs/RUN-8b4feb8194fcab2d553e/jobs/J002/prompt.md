# Iteration 1 — Implementation: Physics Foundation + SPH + Gravity

Job ID: `J002`

## Worker Contract
You execute one assigned job in one persistent conversation. Follow the job
prompt's workspace boundaries, requirements, constraints, and completion
conditions. Do not schedule work or mutate orchestration-owned state.

## Work and durable artifacts

1. Read the complete job prompt.
2. Perform only the assigned work using the requested method.
3. Keep the contracted `report.md` current; write `checkpoint.md` when its
   minimal replacement context would help recovery.
4. Place artifacts only in the paths authorized by the prompt.

`checkpoint.md` is recovery evidence, not an orchestration-state contract.

## Return a normalized outcome

Return exactly one outcome:

```json
{"status":"completed","summary":"what was accomplished","report_path":"path/to/report.md"}
```

```json
{"status":"needs_input","summary":"where work stopped","question":"precise question","context":"optional context"}
```

```json
{"status":"failed","summary":"what failed and why"}
```

Only claim `completed` after satisfying the job's completion conditions. Ask
blocking questions early. Do not blindly repeat a possible side effect; follow
the prompt's recovery check first. A replacement worker inspects the supplied
report, checkpoint, transcript reference, and workspace observations before
continuing.

Workers may recommend follow-up work in their report, but only the root
operator creates explicit jobs.

## Goal
Implement task groups 1-3 of rebuild-tde-physics-core: physics state foundation (units, persistent particles, polytropic star), neighbor search and SPH (hash, density, pressure, forces, internal energy), unified gravity (symplectic integration, BH+self-gravity, pseudo-Newtonian potential). Each task group applied via openspec-apply-change, verified, fixed, synced, archived, committed.

## Workflow
openspec-apply-change for task group 1 -> openspec-apply-change for task group 2 -> openspec-apply-change for task group 3 -> openspec-verify-change -> fix findings -> openspec-sync-specs -> openspec-archive-change -> git commit and push

## Requirements
- Implement tasks 1.1-1.5 (Physics State Foundation)
- Implement tasks 2.1-2.6 (Neighbor Search and SPH)
- Implement tasks 3.1-3.5 (Unified Gravity Integration)

## Constraints
- Do not implement later task groups
- Major issues must be escalated to Architect
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- Tasks 1.1-1.5 checked off
- Tasks 2.1-2.6 checked off
- Tasks 3.1-3.5 checked off
- All verification findings fixed
- Change archived and committed

## Context
- Workspace: `C:\Projects\BlackholeSim`
- openspec/changes/rebuild-tde-physics-core/tasks.md — task definitions
- openspec/changes/rebuild-tde-physics-core/design.md — design decisions
- openspec/changes/rebuild-tde-physics-core/specs/ — specification files

## Escalation
Architect

## Report Expectation
Write the final report to `jobs/J002/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

Begin the domain work immediately.
