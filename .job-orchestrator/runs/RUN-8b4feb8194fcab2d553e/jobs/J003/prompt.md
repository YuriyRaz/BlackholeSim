# Iteration 1 — Implementation: TDE Init + Disruption + Fallback + Accretion

Job ID: `J003`

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
Implement task groups 4-5 of rebuild-tde-physics-core: TDE initial conditions and disruption (persistent star, real tidal gradient), fallback/circularization/accretion (bound/unbound classification, particle capture, remove fake timers and synthetic jet). Each task group applied via openspec-apply-change, verified, fixed, synced, archived, committed.

## Workflow
openspec-apply-change for task group 4 -> openspec-apply-change for task group 5 -> openspec-verify-change -> fix findings -> openspec-sync-specs -> openspec-archive-change -> git commit and push

## Requirements
- Implement tasks 4.1-4.5 (TDE Initial Conditions and Disruption)
- Implement tasks 5.1-5.6 (Fallback, Circularization, Accretion)
- Remove pre-shaped stream, index-based gas, random jet redirect rule

## Constraints
- Do not implement later task groups before J002 is done
- Major issues must be escalated to Architect
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- Tasks 4.1-4.5 checked off
- Tasks 5.1-5.6 checked off
- No faked TDE mechanics remain from groups 4-5
- Change archived and committed

## Context
- Workspace: `C:\Projects\BlackholeSim`
- openspec/changes/rebuild-tde-physics-core/tasks.md — task definitions
- openspec/changes/rebuild-tde-physics-core/design.md — design decisions
- openspec/specs/tidal-disruption/spec.md — current (faked) spec being replaced

## Escalation
Architect

## Report Expectation
Write the final report to `jobs/J003/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

Begin the domain work immediately.
