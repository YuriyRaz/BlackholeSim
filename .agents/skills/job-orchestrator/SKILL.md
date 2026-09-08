---
name: job-orchestrator
description: Operate a durable, persistent-session queue of explicit subagent jobs.
---

# Job Orchestrator

The root session is the control plane. It MUST NOT perform domain work itself:
route investigation, implementation, verification, decisions, and synthesis to
explicit jobs. This boundary is enforced by the v5 receipt and artifact
contracts, not by root-agent prose alone.

## Root Allowlist

The root MAY only initialize runs, register jobs, call `next`, launch or resume
workers through a configured transport adapter, record exact verified transport
facts, answer user questions, run `audit`, `recover`, or `repair`, and relay
final run status. Repository investigation, editing, domain testing,
verification, report authorship, checkpoint authorship, outcome synthesis, and
domain acceptance MUST be delegated.

The root MUST record the exact native session reference returned by the
transport. Invented labels, aliases, reconstructed IDs, and descriptive
references are forbidden. The root MUST send the generated prompt verbatim and
MUST NOT prepend, append, summarize, correct, or replace it.

## Boundaries

- State lives at `cwd()/.job-orchestrator/runs/` unless `--state-root` is set.
- Never manually read, edit, parse, or reconstruct authoritative run-state JSON
  (`run.json`, `jobs/*/job.json`, or `jobs/index.json`). Use `jobctl audit`,
  `recover`, and `repair`; if they cannot safely handle the condition, report
  that control-plane limitation.
- Files supplied to a command—job definitions, outcomes, answers, decisions,
  or recovery evidence—remain editable until successful ingestion. Correct a
  rejected input using its validation error; do not patch persisted state.
- A canceled, lost, unavailable, empty-with-uncertain-liveness, or contradictory
  transport result exits the normal loop. Run `audit`, gather direct evidence,
  and invoke `recover` before any retry or replacement.

## Start and register

```text
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py init --request-file <path> --goal "<goal>"
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py register --run <run-root> --definition <jobs.json>
```

New trusted runs use `--protocol-version 5`; v4 is retained only for explicit
legacy operation. Use `jobctl --help` and command help for CLI syntax. Use the
v5 schemas for trusted field validity.

```text
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py init --protocol-version 5 --request-file <path> --goal "<goal>"
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py launch-receipt --run <run-root> --receipt <receipt.json>
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py response-receipt --run <run-root> --receipt <receipt.json>
```

## Normal control loop

Repeatedly run:

```text
python C:\Projects\ai-skills\skills\job-orchestrator\scripts\jobctl.py next --run <run-root>
```

| Operation | Root action |
| --- | --- |
| `start_job` | Create a worker session and send the returned prompt verbatim. |
| `resume_job` | Send the returned continuation prompt to the existing session. |
| `ask_user` | Obtain the requested authority or answer, then record it with `answer`. |
| `wait` | Wait for a transport event; do not invent state. |
| `run_complete` | Relay `run_status` and `successful`; do not equate terminal with success. |

Record v4 transport facts with `session` and `outcome` only for legacy runs.
For v5, record adapter-authenticated launch and response receipts; standalone
session references and outcome files are rejected. `answer` returns an
immediate `resume_job` operation, which MUST be sent to the existing worker
before calling `next` again. A `wait` with
`reason: advisory_decision_required` requires `advisory-decision`; an ordinary
`wait` requires a transport event. `run_complete` is terminal, but only
`run_status: completed` with `successful: true` means the goal succeeded.

## Load a reference only when needed

| Situation | Reference |
| --- | --- |
| Protocol semantics, outcomes, completion, or scheduling | [protocol.md](references/protocol.md) |
| Interruption, contradictory evidence, uncertain external effect, audit, or repair | [recovery.md](references/recovery.md) |
| Creating or replacing a worker prompt | [job-protocol.md](references/job-protocol.md) |
| Selecting or implementing a transport adapter | [transport-capabilities.md](references/transport-capabilities.md) |
| Maintaining the skill or composing workflows | [maintainer-guidance.md](references/maintainer-guidance.md) |
| Field-level v4 validity | `schemas/v4/*.schema.json` |
| Field-level trusted validity | `schemas/v5/*.schema.json` |
