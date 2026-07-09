---
name: job-orchestrator
description: Run complex work through a durable, resumable, script-enforced queue of bounded subagent jobs with generated prompts, atomic checkpoints, audit, and side-effect-aware recovery.
---

# Job Orchestrator

Use the root session only as a transport-neutral control plane. Domain
investigation, implementation, verification, decisions, and synthesis belong
in explicit jobs. Read [protocol.md](references/protocol.md) for the model and
[recovery.md](references/recovery.md) before recovering interrupted work.

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
`run_complete`). Use its generated prompt verbatim. Persist the transport or
worker response to JSON, then:

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
