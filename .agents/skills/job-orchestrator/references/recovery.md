# Recovery Protocol

> [!CAUTION]
> **DO NOT PERFORM THESE STEPS MANUALLY.**
> The steps below describe the mechanical actions performed by the `jobctl.py` script. The LLM agent MUST NOT attempt to read JSON files, manually replay events, or manually reconstruct state. Just run the corresponding `jobctl.py` commands.

## Resume A Run

To resume a run, the agent must ONLY use `jobctl.py`. Internally, the script will:

1. Locate the run by explicit run ID.
2. When you run `jobctl audit`, it will replay the authoritative event journal and compare all derived snapshots.
3. It will hash `protocol/job-protocol.md` and compare it with the manifest.
4. It will replay `improvements.jsonl` and identify unresolved observations and active maintenance jobs.
5. When you run `jobctl recover`, it will acquire or safely take over the renewable lease.
6. It will validate every indexed job directory, contract, and report path.
7. It will rebuild disposable indexes if they disagree with authoritative job files.
8. It will reconstruct parent/child waits from `workflow.json`, child request events, and child report paths.

Your only tasks are to:
1. Run `jobctl audit` to ensure state consistency.
2. If audit reports `derived_snapshot_drift` or `stale_index_or_queue`, run `jobctl audit --rebuild` and then run `jobctl audit` again.
3. Use `jobctl recover --dry-run --evidence <file>` to classify any active dispatch or unapplied worker evidence before scheduling new work.
4. Review the script's `finding`, `safe_next_action`, blockers, and proposed repair.
5. Run `jobctl recover` only after the dry run proves one safe action.
6. Run a final `jobctl audit` before returning to the normal `jobctl next` loop.

## State Integrity Audit Gate

After any suspected interruption, session replacement, dispatch recovery, or
post-interruption scheduling decision, the root orchestrator MUST complete this
gate before dispatching new domain work:

```text
python scripts/jobctl.py audit --run <run-root>
python scripts/jobctl.py audit --run <run-root> --rebuild   # only when audit says rebuild is eligible
python scripts/jobctl.py audit --run <run-root>
python scripts/jobctl.py recover --run <run-root> --dry-run --evidence <evidence.json>
python scripts/jobctl.py recover --run <run-root> --evidence <evidence.json>
python scripts/jobctl.py audit --run <run-root>
```

Do not skip the dry run. Do not dispatch new work while audit reports protocol
hash mismatch, active-idle contradiction, unresolved dispatch evidence,
`external_effect_unknown`, or `journal_corrupt_or_insufficient`.

Audit and recovery findings use these classifications:

- `clean`: replay, snapshots, protocol identity, and recovery evidence agree.
- `derived_snapshot_drift`: replay is healthy but a derived snapshot disagrees.
- `stale_index_or_queue`: `queue.json` or `jobs/index.json` is stale or empty
  compared with authoritative journal or job evidence.
- `interrupted_dispatch_recorded_not_sent`: a dispatch was recorded but no
  transport send is proven.
- `interrupted_dispatch_sent_no_result`: transport or progress evidence exists
  but no validated worker result has been applied.
- `completed_result_not_applied`: a validated result exists while the action or
  workflow state remains unresolved.
- `external_effect_unknown`: local state cannot prove whether repository or
  external side effects completed.
- `journal_corrupt_or_insufficient`: the journal, protocol identity, or
  evidence cannot prove one safe next action.

`progress.json` is evidence only. It can justify a status request or
investigation, but it never completes a workflow node without a matching
validated worker result.

## Classify Interrupted Dispatches

An interrupted dispatch may be:

- recorded but never sent
- sent but not started
- running in a resumable subagent session
- completed by the subagent but not persisted
- externally effective but locally unacknowledged
- safe to retry
- unsafe to retry without reconciliation

Never convert `running` to `pending` blindly. A stale threshold first creates
one idempotent `request_status` action. Apply recovery only from persisted
transport, checkpoint, and external-effect evidence.

If the original session exists, ask it only for the status and missing result.
If the session is lost, create a replacement job session using `job.json`,
`checkpoint.md`, relevant step results, and related reports.

## Composite Parent Recovery

For each parent node marked `waiting_for_child`:

1. Resolve every child request to an accepted child job, rejection, or
   incomplete materialization event.
2. Verify accepted child directories and authoritative job states.
3. Do not recreate a child when a materialized job ID already exists.
4. If all required children completed, verify their reports and route those
   paths to the parent.
5. If the parent session is unavailable, replace it using its checkpoint,
   workflow state, and child reports.
6. Require acknowledgement of recovered child results before dispatching the
   next parent-session node.

Detect orphan children whose parent or workflow node is missing. Preserve them
for investigation rather than silently deleting or attaching them elsewhere.
Reject any recovered dependency cycle involving an ancestor and descendant.

## Side Effects

Exactly-once execution cannot be guaranteed for external systems. Every
side-effecting step must define a recovery check and, where possible, an
idempotency key.

Examples:

- Before repeating a commit, inspect repository history and working state.
- Before repeating a push, verify the expected commit on the remote branch.
- Before repeating deployment, inspect provider deployment status.
- Before repeating issue creation, search by durable correlation ID.

Record observed external state before deciding to retry, accept completion, or
create a repair job.

## Recovery Investigation Jobs

Create a recovery investigation job only when audit and dry-run recovery cannot
prove one safe automatic next action. The job is a conditional diagnostic, not
an ordinary product architecture review. Its contract must be limited to:

- run-state evidence and contradiction analysis
- side-effect safety and recovery-check status
- the recommended next control-plane action
- any user authority required before mutation

Do not grant state mutation authority to an investigation job unless the user
explicitly authorizes that authority in the job contract. By default, all
repairs remain `jobctl.py` control-plane operations.

## Session Loss

Resume a persistent subagent only when its session ID remains valid. Otherwise:

1. Mark the old session unavailable without marking the job failed.
2. Persist a `session_replaced` event.
3. Obtain the generated replacement bootstrap action from `jobctl next`.
4. Send the frozen protocol path and job contract path.
5. Require a matching protocol acknowledgement without domain work.
6. Supply the checkpoint, completed work units, and exactly one next permitted
   action; do not create a replacement dispatch until acknowledgement.

For a composite job, also provide completed and waiting workflow nodes, child
job IDs, child report paths, and unresolved child requests.

Do not resume work when the protocol hash, contract revision, or bootstrap
acknowledgement is inconsistent. Persist the mismatch and investigate or
migrate explicitly.

## Improvement Recovery

Rebuild each improvement candidate from its append-only events. Do not create
a duplicate maintenance job when an accepted or materialized candidate already
references one.

If a maintenance job was interrupted, reconcile its file changes and
validation evidence before retrying. Preserve unrelated working-tree changes.
If canonical skill files changed while the job was unavailable, require the
maintenance job to reread them and reconsider its patch.

Canonical updates do not change the active run's frozen protocol. Version-2
runs stay on version 2 unless `jobctl migrate-v2` is explicitly authorized.
Migration updates the manifest and every contract revision, journals the
decision, and requires replacement acknowledgements before domain work.
For eventless version-2 layouts, migration first imports the existing job,
queue, workflow, and step snapshots into lifecycle events. The migration
event carries authoritative version-3 protocol and contract content so audit
or a repeated migration command can finish static installation after a crash
without dropping legacy jobs. Default recovery reports
`legacy_v2_unchanged` and does not mutate such a run.

Before restoring a terminal run state, ensure every observation is resolved,
rejected, or deferred with a reason.

## Corrupt Or Partial State

Prefer the append-only event journal when a snapshot is truncated or has an
unexpected revision. Quarantine malformed files rather than overwriting them.
If journal and external side effects cannot establish a safe next action,
create an investigation job or ask the user when authority is required.

## Completion Audit

After recovery, do not trust a terminal status alone. Confirm required job
reports exist, referenced artifacts are readable, acceptance criteria are
addressed, and no active dispatch remains.
