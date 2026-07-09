# Recovery Protocol

## Resume A Run

1. Locate the run by explicit run ID. Do not guess when multiple active runs
   match the same workspace.
2. Run `jobctl audit`; replay the authoritative event journal and compare all
   derived snapshots.
3. Hash `protocol/job-protocol.md` and compare it with the manifest.
4. Replay `improvements.jsonl` and identify unresolved observations and active
   maintenance jobs.
5. Let `jobctl recover` acquire or safely take over the renewable lease.
6. Validate every indexed job directory, contract, and report path.
7. Rebuild disposable indexes if they disagree with authoritative job files.
8. Reconstruct parent/child waits from `workflow.json`, child request events,
   and child report paths.
9. Use `jobctl recover --dry-run --evidence <file>` to classify any active
   dispatch before scheduling new work.
10. Persist `recovering`, perform reconciliation, then return the run to
   `active`, `waiting_for_user`, or `blocked`.

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
