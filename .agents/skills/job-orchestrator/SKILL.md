---
name: job-orchestrator
description: Run complex work through a durable, resumable, script-enforced queue of bounded subagent jobs with generated prompts, atomic checkpoints, audit, and side-effect-aware recovery.
---

# Job Orchestrator

## Overview

Use the root session only as a transport-neutral control plane. Domain
investigation, implementation, verification, decisions, and synthesis belong
in explicit jobs. Read [protocol.md](references/protocol.md) for the model and
[recovery.md](references/recovery.md) before recovering interrupted work.

The root session MUST NEVER execute a job dispatch itself. For
`spawn_and_bootstrap` and `send_dispatch`, the generated prompt is worker
payload: create or resume the appropriate subagent session, send that prompt to
the subagent verbatim, and record only the subagent response. If the root
session starts reading application files, applying changes, running job checks,
answering a job question, or invoking a job-specific skill directly, stop and
route that work into the active job session instead.

> [!CAUTION]
> **NEVER MANUALLY READ, WRITE, OR PARSE THE JSON STATE FILES** in the `<run-root>` (e.g. `run.json`, `queue.json`, `events.jsonl`, etc.) using tools like `read_file`, `cat`, or `grep`. These files can be hundreds of kilobytes and will cause context truncation or tool errors. All interaction with the durable state **MUST** be performed exclusively via the `scripts/jobctl.py` CLI commands described below.

## Parameters/Arguments

- `--request-file <path>`: Path to the initialization request payload.
- `--goal "<goal>"`: The top-level goal for the run.
- `--run <run-root>`: Directory containing the job orchestrator run state.
- `--definition <jobs.json>`: Path to the normalized job definition JSON.
- `--action-id <action-id>`: The ID of the action being recorded.
- `--response <response.json>`: The worker or transport response payload.
- `--rebuild`: Rebuild snapshots from the journal during an audit.
- `--dry-run`: Evaluate recovery actions without mutating state.
- `--evidence <file>`: External evidence of transport state for recovery.
- `--authorized-by <identity>`: The identity authorizing a v2-to-v3 migration.
- `--reason "<reason>"`: The justification for migrating a run.
- `--abort-dispatch <dispatch-id>`: The ID of a dangling dispatch to abort during a repair.

## Create And Compile

Initialize a version-3 run:

```text
python scripts/jobctl.py init --request-file <path> --goal "<goal>"
```

Normalize jobs and bounded workflow nodes into a JSON definition, then:

```text
python scripts/jobctl.py compile --run <run-root> --definition <jobs.json>
```

Each node needs explicit work units, acceptance criteria, checks, prohibited
later actions, checkpoint policy, side-effect class, and recovery check.
Oversized work requires a persisted, authorized unbounded-scope override.

## Execute The Control Loop

Repeat:

```text
python scripts/jobctl.py next --run <run-root>
```

Perform exactly the returned external action (`spawn_and_bootstrap`,
`send_dispatch`, `wait`, `request_status`, `route_resolution`, `ask_user`, or
`run_complete`). For `spawn_and_bootstrap` and `send_dispatch`, perform means
transport the generated prompt to the job's subagent session; it never means
executing the prompt in the root session. Use the generated prompt verbatim.
Persist the transport or worker response to JSON, then:

```text
python scripts/jobctl.py record --run <run-root> \
  --action-id <action-id> --response <response.json>
```

Repeated `next` returns the same unresolved action. Repeated `record` with the
same response is harmless. Never hand-edit lifecycle snapshots, the journal,
dispatches, actions, or prompts. Do not combine bootstrap, resolution, status,
or execution messages.

Workers use only [job-protocol.md](references/job-protocol.md) and
`scripts/workerctl.py`. They checkpoint worker-owned artifacts and return
validated results; the control plane decides advancement and schedules another
bounded dispatch when a workflow node has remaining work.

## Returns/Output

- **`jobctl next`**: Outputs exactly one unresolved action containing a generated prompt or system instruction.
- **`jobctl record`**: Outputs the updated run state or workflow advancement.
- **Worker Checkpoints**: Write atomically to `checkpoint.md` and `progress.json` within the worker's restricted root.

## Error Handling

If a command fails, it emits a non-zero exit code and error details. 
- **Validation Errors**: If `compile` or `record` rejects inputs, fix the invalid JSON or response and retry. The journal remains unmutated on rejection.
- **Schema Validation Errors**: If schema validation fails, read the error message to identify the missing or invalid field. Cross-reference the relevant schema in `schemas/v3/` and apply targeted edits to correct the drift instead of rewriting the entire file.
- **Truncated JSON**: If JSON parsing fails due to truncation, the orchestrator will output the line of failure and a partial read count. Inspect the end of the file and use file append or targeted edits to add the missing data (e.g. closing brackets or missing objects). Do NOT rewrite the entire file.
- **Interrupted Work**: Do not manually retry. Use `jobctl recover --dry-run` to classify the interruption safely.
- **State Corruption**: If snapshots drift, use `jobctl audit --rebuild` to deterministically reconstruct state from the append-only journal.

## Suspected Interruption Handling

When a run may have been interrupted, do not dispatch new domain work and do
not ask a worker to continue until the State Integrity Audit Gate passes:

```text
python scripts/jobctl.py audit --run <run-root>
python scripts/jobctl.py audit --run <run-root> --rebuild
python scripts/jobctl.py recover --run <run-root> --dry-run --evidence <evidence.json>
python scripts/jobctl.py recover --run <run-root> --evidence <evidence.json>
python scripts/jobctl.py audit --run <run-root>
```

Run `audit --rebuild` only when audit reports eligible
`derived_snapshot_drift` or `stale_index_or_queue`. Review dry-run recovery
before applying it. Do not dispatch new work while audit or recovery reports
protocol hash mismatch, active-idle contradiction, unresolved worker evidence,
`external_effect_unknown`, or `journal_corrupt_or_insufficient`.

Use this prompt text when asking an existing or replacement job session for
recovery status:

```text
Status check only. Do not perform domain work, do not retry side effects, and
do not edit run state. Inspect the current dispatch with workerctl, report
whether the session is available, whether the prior dispatch started, the latest
checkpoint/progress identity, whether a finalized result exists, and any
repository or external side-effect evidence required by the dispatch recovery
check. Return evidence for jobctl recover; do not decide workflow advancement.
```

Recovery investigation jobs are conditional diagnostics for run-state evidence,
contradictions, side-effect safety, and the recommended next control-plane
action. They are not ordinary product architecture review jobs and receive no
state mutation authority unless the user explicitly authorizes it.

## Repair State

If the orchestrator is stuck due to a dangling dispatch (e.g. failing validation with `run active dispatch pointer disagrees with dispatch state`), repair the state by aborting it:

```text
python scripts/jobctl.py repair --run <run-root> --abort-dispatch <dispatch-id>
```

This safely constructs synthetic failure events to abort the hanging dispatch and resolve the inconsistency without manual editing.

## Audit And Recover

Audit at completion and after suspected interruption:

```text
python scripts/jobctl.py audit --run <run-root>
python scripts/jobctl.py audit --run <run-root> --rebuild
```

Inspect recovery without mutating state:

```text
python scripts/jobctl.py recover --run <run-root> --dry-run \
  --evidence <transport-and-external-evidence.json>
```

Apply recovery only after its classification is supported. Status is requested
from an existing session before replacement. Repository or external side
effects require their explicit recovery check; unsafe work is never blindly
retried.

Existing version-2 runs remain frozen. Migrate only with explicit authority:

```text
python scripts/jobctl.py migrate-v2 --run <run-root> \
  --authorized-by <identity> --reason "<reason>"
```

Migration updates the manifest and contracts and requires every active session
to bootstrap again. Canonical skill updates affect future runs by default.
