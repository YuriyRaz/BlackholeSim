---
name: job-orchestrator
description: Operate a durable, persistent-session queue of explicit subagent jobs.
---

# Job Orchestrator

The root session is the control plane. It MUST NOT perform domain work itself:
route investigation, implementation, verification, decisions, and synthesis to
explicit jobs.

## Boundaries

- State lives at `cwd()/.job-orchestrator/runs/` unless `--state-root` is set.
- Never manually read, edit, parse, or reconstruct authoritative run-state JSON
  (`run.json`, `jobs/*/job.json`, or `jobs/index.json`). Use `jobctl audit`,
  `recover`, and `repair`; if they cannot safely handle the condition, report
  that control-plane limitation.
- Files supplied to a command—job definitions, outcomes, answers, decisions,
  or recovery evidence—remain editable until successful ingestion. Correct a
  rejected input using its validation error; do not patch persisted state.

## Start and register

```text
python scripts/jobctl.py init --request-file <path> --goal "<goal>"
python scripts/jobctl.py register --run <run-root> --definition <jobs.json>
```

Use `jobctl --help` and command help for CLI syntax. Use the v4 schemas for
field validity.

## Normal control loop

Repeatedly run:

```text
python scripts/jobctl.py next --run <run-root>
```

| Operation | Root action |
| --- | --- |
| `start_job` | Create a worker session and send the returned prompt verbatim. |
| `resume_job` | Send the returned continuation prompt to the existing session. |
| `ask_user` | Obtain the requested authority or answer, then record it with `answer`. |
| `wait` | Wait for a transport event; do not invent state. |
| `run_complete` | Report completion under run policy. |

Record transport facts with `session`, `outcome`, `answer`, and
`advisory-decision` as applicable. The normal loop is read-only until one of
those supported commands records a fact.

## Load a reference only when needed

| Situation | Reference |
| --- | --- |
| Protocol semantics, outcomes, completion, or scheduling | [protocol.md](references/protocol.md) |
| Interruption, contradictory evidence, uncertain external effect, audit, or repair | [recovery.md](references/recovery.md) |
| Creating or replacing a worker prompt | [job-protocol.md](references/job-protocol.md) |
| Selecting or implementing a transport adapter | [transport-capabilities.md](references/transport-capabilities.md) |
| Maintaining the skill or composing workflows | [maintainer-guidance.md](references/maintainer-guidance.md) |
| Field-level state validity | `schemas/v4/*.schema.json` |
