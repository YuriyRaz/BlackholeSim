# Iteration 1 — Proposal: Review rebuild-tde-physics-core

Job ID: `J001`

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
Review the existing rebuild-tde-physics-core proposal using openspec explore, check current TDE codebase state (PhysicsEngine.js, Star.js, Constants.js, presets.js), consult Architect if issues found, and confirm the proposal is ready for implementation.

## Workflow
openspec explore current TDE state -> if issues, ask Architect via sub-job -> openspec proposal

## Requirements
- Understand current faked TDE mechanics
- Review existing rebuild-tde-physics-core proposal

## Constraints
- Do not implement code
- Only review and propose
- Do not mutate orchestrator-owned run, queue, dependency, parent, or job-status state.

## Completion Conditions
- Proposal reviewed and confirmed ready for implementation
- Any architectural issues documented

## Context
- Workspace: `C:\Projects\BlackholeSim`
- GREAT_GOAL.md — ultimate goal: all phenomena emerge from shared physical equations
- openspec/changes/rebuild-tde-physics-core/proposal.md — existing proposal to review

## Escalation
If blocked by missing information, authority, a decision, or separately managed work, return `needs_input` with a precise question and relevant context.

## Report Expectation
Write the final report to `jobs/J001/report.md` before returning `completed`. The completed outcome must include that report path and a non-empty summary.

Begin the domain work immediately.
