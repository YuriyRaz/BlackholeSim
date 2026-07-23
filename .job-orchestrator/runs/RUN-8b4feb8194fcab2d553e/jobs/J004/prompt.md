# Iteration 1 — Implementation: Rendering Contract + Verification + Performance

Job ID: `J004`

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
Implement task groups 6-7 of rebuild-tde-physics-core: update physics state and rendering contract (getState(), remove TDE-specific hacks), add integration tests, benchmarks, and documentation. Applied via openspec-apply-change, verified, fixed, synced, archived, committed.

## Workflow
openspec-apply-change for task group 6 -> openspec-apply-change for task group 7 -> openspec-verify-change -> fix findings -> openspec-sync-specs -> openspec-archive-change -> git commit and push

## Requirements
- Implement tasks 6.1-6.5 (Physics State and Rendering Contract)
- Implement tasks 7.1-7.6 (Verification and Performance)
- Ensure visual-effects-03 and audio-polish-04 features still work with new TDE state

## Constraints
- Must run after J002 and J003 complete
- Check compatibility with existing features
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- Tasks 6.1-6.5 checked off
- Tasks 7.1-7.6 checked off
- Existing visual and audio features compatible
- Change archived and committed

## Context
- Workspace: `C:\Projects\BlackholeSim`
- openspec/changes/rebuild-tde-physics-core/tasks.md — task definitions
- openspec/changes/archive/2026-07-09-visual-effects-03/ — archived visual effects specs for compatibility check

## Escalation
Architect

## Report Expectation
Write the final report to `jobs/J004/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

Begin the domain work immediately.
