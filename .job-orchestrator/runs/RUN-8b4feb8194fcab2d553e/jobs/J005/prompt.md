# Iteration 1 — Architect: Cross-cutting Review and Iteration 2 Plan

Job ID: `J005`

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
Perform a cross-cutting architecture review of the entire rebuild-tde-physics-core change. Check GREAT_GOAL.md compliance: are all faked TDE mechanics replaced with physical simulation? Verify compatibility with visual-effects-03 and audio-polish-04. Identify any remaining non-physical behavior in the entire simulation. Plan Iteration 2.

## Workflow
openspec explore the complete rebuilt TDE -> check every faked mechanic removal -> verify compatibility with existing features -> plan next iteration -> update GREAT_GOAL.md if needed

## Requirements
- Verify no faked TDE mechanics remain (pre-shaped stream, index gas, random jet, fallback timer)
- Check compatibility with visual-effects-03 features (phase indicator, particle trails, GW ripples)
- Check compatibility with audio-polish-04 features (event sounds, spatial audio)
- Identify any other non-physical behaviors in the simulation
- Produce Iteration 2 plan

## Constraints
- This review is cross-cutting — must examine the entire system, not just TDE
- Must verify great goal compliance
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- All TDE physics confirmed as emergent from physical equations
- No fake mechanics remain anywhere
- Compatibility confirmed with existing features
- Iteration 2 plan documented

## Context
- Workspace: `C:\Projects\BlackholeSim`
- GREAT_GOAL.md — ultimate goal reference
- openspec/changes/rebuild-tde-physics-core/ — the implemented change
- openspec/specs/ — all main specs to check for remaining non-physical behavior

## Escalation
If blocked by missing information, authority, a decision, or separately managed work, return `needs_input` with a precise question and relevant context.

## Report Expectation
Write the final report to `jobs/J005/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

Begin the domain work immediately.
