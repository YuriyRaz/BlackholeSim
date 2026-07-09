## Why

Interrupted job-orchestrator runs can currently resume from contradictory state when derived snapshots, worker artifacts, unresolved actions, and queue/index files disagree. This creates a risk of skipping completed work, retrying side effects, or leaving a run active but unable to dispatch the next safe action.

## What Changes

- Add a mandatory State Integrity Audit Gate before resuming interrupted runs, replacing sessions, recovering dispatches, or scheduling new work after suspected interruption.
- Require the root orchestrator to classify interruption and corruption findings through `jobctl.py` instead of reading or editing durable JSON state manually.
- Define recovery classifications for common failure modes such as stale indexes, snapshot drift, unresolved dispatches with completed worker results, unknown external side effects, and insufficient journal evidence.
- Define safe repair behavior: rebuild derived snapshots from the journal, reconcile completed results through recovery events, quarantine malformed state, and create a recovery investigation job only when automatic recovery cannot prove one safe next action.
- Clarify that recovery investigation jobs are conditional read-only diagnostics, not ordinary product architecture reviews.

## Example Cases

- A worker result exists and validates, but the corresponding `send_dispatch` action is still unresolved and the workflow node did not advance.
- A run is still `active`, but has no active job, no active dispatch, an empty queue, and unresolved recovery evidence.
- `jobs/index.json` or `queue.json` is stale or empty even though authoritative job evidence exists.
- A dispatch may have committed, pushed, deployed, or touched another external system, but local state cannot prove whether the side effect completed.
- `progress.json` says work completed, but there is no matching validated worker result yet.

## Capabilities

### New Capabilities
- `job-orchestrator-recovery`: Requirements for auditing, classifying, and safely recovering interrupted job-orchestrator runs before normal execution resumes.

### Modified Capabilities

## Impact

- Affects `.agents/skills/job-orchestrator/references/recovery.md`, `.agents/skills/job-orchestrator/references/job-protocol.md`, and the job-orchestrator skill guidance that controls interrupted run handling.
- Affects `scripts/jobctl.py` recovery/audit behavior and tests around v3 recovery, stale snapshot rebuilds, unresolved actions, and completed-result reconciliation.
- No runtime simulation, renderer, physics, audio, or UI behavior changes.
