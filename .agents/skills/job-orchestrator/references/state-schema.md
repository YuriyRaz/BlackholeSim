# Durable State Schema

> [!CAUTION]
> **INFORMATIONAL ONLY: DO NOT PARSE OR EDIT THESE FILES.**
> This schema describes the internal data model managed exclusively by `scripts/jobctl.py`.
> **NEVER** use tools like `read_file`, `cat`, or `grep` to manually inspect JSON files (e.g. `run.json`, `queue.json`, `events.jsonl`) as they can be hundreds of kilobytes and will cause context truncation or tool errors. Always use `jobctl` commands to query state.

## Directory Layout

```text
<state-root>/
`-- <run-id>/
    |-- run.json
    |-- request.md
    |-- setup.json
    |-- queue.json
    |-- actions/
    |-- improvements.jsonl
    |-- protocol/
    |   |-- job-protocol.md
    |   `-- manifest.json
    |-- events.jsonl
    |-- decisions.jsonl
    |-- orchestrator.lock
    `-- jobs/
        |-- index.json
        `-- J001/
            |-- job.json
            |-- contract.json
            |-- inputs.json
            |-- workflow.json
            |-- steps.json
            |-- dispatches/
            |   `-- D001.json
            |-- child-requests.jsonl
            |-- messages.jsonl
            |-- report.md
            |-- checkpoint.md
            |-- progress.json
            |-- results/
            `-- artifacts/
```

Use absolute paths in cross-job references. Use paths relative to the run root
inside indexes when portability matters.

## Authority And Duplication

- `events.jsonl` is authoritative for lifecycle state.
- `setup.json` is authoritative for normalized initial configuration.
- `run.json`, `queue.json`, job/workflow/step/session/action/dispatch documents,
  and indexes are deterministic replay snapshots.
- `improvements.jsonl` is the append-only observation and maintenance ledger.
- `protocol/job-protocol.md` is the immutable worker protocol for this run.
- `protocol/manifest.json` records its version, source, and SHA-256 hash.
- `jobs/<id>/job.json` is a derived job-lifecycle snapshot.
- `contract.json` is authoritative for what one job may do and access.
- `workflow.json` and `steps.json` are derived workflow snapshots.
- `child-requests.jsonl` records proposed, accepted, rejected, and materialized
  child jobs.
- `events.jsonl` is the append-only audit and recovery journal.
- `jobs/index.json` is a rebuildable discovery index.
- `report.md` is the stable human-readable job product.

Summary fields in indexes are caches. Rebuild them from authoritative files
when they disagree.

## Run

```json
{
  "schema_version": 3,
  "run_id": "20260708-120000-example",
  "status": "initializing",
  "goal": "Deliver the requested change",
  "created_at": "2026-07-08T12:00:00Z",
  "updated_at": "2026-07-08T12:00:00Z",
  "workspace": "C:\\Projects\\example",
  "state_root": "C:\\...\\job-orchestrator\\runs",
  "protocol": {
    "manifest_path": "protocol/manifest.json",
    "version": 3,
    "sha256": "..."
  },
  "skill_source": {
    "path": "C:\\Projects\\ai-skills\\skills\\job-orchestrator",
    "update_scope": "future_runs"
  },
  "revision": 1,
  "active_job_id": null,
  "active_dispatch_id": null
}
```

Run statuses:

```text
initializing | active | waiting_for_user | recovering |
completed | completed_with_concerns | blocked | canceled
```

## Setup

```json
{
  "goal": "",
  "requirements": [],
  "acceptance_criteria": [],
  "roles": {},
  "job_types": {},
  "policies": {
    "execution_mode": "sequential",
    "max_same_approach_attempts": 2,
    "max_total_attempts_per_step": 4,
    "max_job_depth": 4,
    "max_children_per_job": 20,
    "max_verification_repair_attempts": 3,
    "nested_delegation": "tracked_only",
    "continuous_improvement": {
      "enabled": true,
      "capture_all_observations": true,
      "auto_create_maintenance_jobs": true,
      "max_maintenance_jobs_per_run": 3,
      "require_generalizable_evidence": true,
      "apply_to_active_run": false
    },
    "investigate_alternatives_before_user": true,
    "final_synthesis": "when_requested_or_needed"
  }
}
```

The role and job-type registries are maps keyed by arbitrary strings. Do not
validate them against a closed enum. Initial-prompt values may override these
policy defaults.

## Queue

```json
{
  "mode": "sequential",
  "next_sequence": 2,
  "entries": [
    {
      "job_id": "J001",
      "priority": 50,
      "sequence": 1,
      "depends_on": [],
      "waiting_on": ["J002"]
    }
  ]
}
```

Read job status from `job.json`. Do not maintain a second authoritative status
in the queue. Keep parent and child jobs in this same queue.

## Job

```json
{
  "id": "J001",
  "parent_job_id": null,
  "parent_workflow_node_id": null,
  "depth": 0,
  "title": "Deliver the OpenSpec change",
  "goal": "Apply, verify, sync, archive, and publish the change",
  "job_type": "proposal",
  "role": "Proposal",
  "priority": 50,
  "status": "waiting",
  "current_workflow_node_id": "apply",
  "attempt": 0,
  "approach_id": "initial",
  "session": {
    "id": "agent-session-42",
    "resumable": true,
    "protocol_ack": {
      "schema_version": 3,
      "protocol_version": 3,
      "protocol_sha256": "...",
      "contract_revision": 1,
      "acknowledged_at": "2026-07-08T12:01:00Z"
    }
  },
  "report_path": "jobs/J001/report.md",
  "checkpoint_path": "jobs/J001/checkpoint.md",
  "created_at": "2026-07-08T12:00:00Z",
  "updated_at": "2026-07-08T12:05:00Z",
  "revision": 4
}
```

Job statuses:

```text
queued | running | waiting | completed | completed_with_concerns |
blocked | failed | canceled
```

A composite parent uses `waiting` while required children run. Waiting parents
remain discoverable in the queue but are not ready and do not occupy the
global dispatch slot.

## Protocol Manifest

```json
{
  "protocol_version": 3,
  "file": "job-protocol.md",
  "sha256": "...",
  "source": "references/job-protocol.md",
  "snapshotted_at": "2026-07-08T12:00:00Z"
}
```

Never replace this snapshot during an active run. A protocol upgrade requires
an explicit migration decision and re-bootstrap of every affected session.

## Job Contract

```json
{
  "contract_version": 3,
  "revision": 1,
  "job_id": "J001",
  "role": "Verifier",
  "goal": "Verify and repair the change",
  "protocol": {
    "path": "../../protocol/job-protocol.md",
    "version": 2,
    "sha256": "..."
  },
  "report_path": "report.md",
  "checkpoint_path": "checkpoint.md",
  "may_propose_jobs": true,
  "may_spawn_untracked_agents": false,
  "may_contact_user": false,
  "may_update_skill": false,
  "skill_source_path": null,
  "related_reports": []
}
```

Increment `revision` whenever capabilities, restrictions, paths, role, goal,
or related report authority changes. Re-bootstrap the active session after a
revision change.

## Workflow Nodes

```json
{
  "session_policy": "persistent",
  "nodes": [
    {
      "id": "apply",
      "position": 1,
      "run_in": "child_job",
      "status": "waiting_for_child",
      "command": null,
      "child_template": {
        "role": "Implementation",
        "command": "/openspec-apply-change"
      },
      "child_request_ids": ["CR001"],
      "child_job_ids": ["J002"],
      "required_report_paths": ["jobs/J002/report.md"],
      "attempt": 1
    },
    {
      "id": "sync",
      "position": 2,
      "run_in": "job_session",
      "status": "pending",
      "command": "/openspec-sync-specs",
      "child_request_ids": [],
      "child_job_ids": [],
      "required_report_paths": [],
      "attempt": 0
    }
  ]
}
```

Workflow-node statuses:

```text
pending | ready | dispatching | running | waiting_for_child |
waiting_for_resolution | evaluating | completed |
completed_with_concerns | blocked | failed | skipped
```

Execution targets are open for future extension, but `job_session` and
`child_job` are the defined sequential-mode targets. A workflow node may own
multiple bounded dispatches. A partial result persists completed work units,
keeps the node active, and schedules only the remainder. Advancement is a
control-plane decision after required reports and acknowledgements persist.

Each child request is journaled through `proposed` (`child_job_requested`),
`validated` (`child_job_validated`), `materialized`
(`child_job_materialized`), and `acknowledged`
(`child_job_acknowledged`) states. The parent remains blocked while any
materialized child is non-terminal or its routed report is unacknowledged.
Validation rejects a child dependency whose transitive chain reaches the
waiting parent.

## Session Steps And Dispatches

`steps.json` records only commands sent to this job's persistent session:

```json
{
  "steps": [
    {
      "id": "sync",
      "workflow_node_id": "sync",
      "command": "/openspec-sync-specs",
      "status": "pending",
      "attempts": [],
      "result_path": null
    }
  ]
}
```

Step statuses:

```text
pending | dispatching | running | evaluating | waiting_for_resolution |
ready | completed | completed_with_concerns | blocked | failed | skipped
```

Each attempt records a unique dispatch ID, approach ID, prompt path or digest,
timestamps, session ID, response path, side-effect class, and recovery check.
The child owns its own steps; never duplicate child dispatches in the parent.

Persist each dispatch before sending it:

```json
{
  "dispatch_id": "D001",
  "job_id": "J001",
  "workflow_node_id": "verify",
  "contract_revision": 1,
  "protocol_version": 3,
  "protocol_sha256": "...",
  "command": "/openspec-verify-change",
  "status": "recorded",
  "created_at": "..."
}
```

## Child Requests

Store immutable events, one JSON object per line:

```json
{"request_id":"CR001","parent_job_id":"J001","workflow_node_id":"apply","status":"proposed","signature":"...","proposed_job":{"role":"Implementation","command":"/openspec-apply-change"},"materialized_job_id":null,"created_at":"..."}
{"request_id":"CR001","status":"materialized","materialized_job_id":"J002","created_at":"..."}
```

Persist the proposal before validation and append later events when it is
accepted, rejected, or materialized. Never let the requesting job choose the
authoritative child job ID. Reject requests that exceed limits, duplicate
active work, or introduce an ancestor dependency cycle.

## Messages

Store one JSON object per line:

```json
{"id":"M001","from":"J002","to":"J001","kind":"child_result","body":"Apply completed","artifact_refs":[{"job_id":"J002","path":"jobs/J002/report.md"}],"created_at":"...","acknowledged_at":null}
```

Kinds are extensible strings such as `question`, `resolution`,
`child_result`, `artifact_available`, `job_request`, `user_answer`, and
`acknowledgement`.

## Improvement Ledger

Store append-only observation and lifecycle events:

```json
{"observation_id":"IO001","source_job_id":"J004","source_dispatch_id":"D009","category":"protocol_gap","summary":"Recovery repeated an acknowledged external action","evidence":["jobs/J004/report.md"],"impact":"Duplicate side effect","suggested_change":"Require reconciliation","generalizable":true,"confidence":"high","signature":"protocol-gap:external-action-acknowledgement","status":"observed","created_at":"..."}
{"observation_id":"IO001","status":"accepted","maintenance_job_id":"J010","created_at":"..."}
{"observation_id":"IO001","status":"resolved","maintenance_job_id":"J010","validation":["quick_validate"],"created_at":"..."}
```

Do not rewrite earlier events. Deduplicate by signature while preserving each
source occurrence. A skill-maintenance job is an ordinary job whose contract
explicitly sets `may_update_skill: true` and supplies `skill_source_path`.
Ordinary job contracts keep both fields disabled.

## Reports And Checkpoints

Update `report.md` after each completed workflow node. Include:

- job identity and current status
- completed work and evidence
- produced artifacts
- child jobs and report paths
- unresolved concerns and questions
- decisions received from other jobs
- proposed follow-up jobs
- improvement observations with evidence and generalizability

Update `checkpoint.md` with the minimum context required to replace a lost
subagent session: current objective, completed workflow nodes and steps, active
concern, accepted decisions, child job IDs, related report paths, unresolved
child requests, and the exact next permitted action.

## Persistence Rules

Write snapshots atomically through a temporary file followed by replacement.
Increment `revision` on every authoritative update. Append journal events
before exposing dependent work. Include event IDs, request IDs, observation
IDs, and dispatch IDs so replay is idempotent.

Use `orchestrator.lock` as a renewable lease containing controller ID,
acquired time, expiry, and heartbeat. A replacement controller may take over
only after the lease expires or explicit handoff is recorded.
