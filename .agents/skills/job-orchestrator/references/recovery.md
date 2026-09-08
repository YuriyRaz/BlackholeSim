# Recovery Procedure

Load this reference before mutating an interrupted run, resolving contradictory
transport evidence, or handling a possibly repeated external effect.

## State Safety

Never manually read, edit, parse, replay, or reconstruct authoritative state
JSON. First run `jobctl audit --run <run-root>`. Then use supported `recover`
or `repair` commands and report an unsupported control-plane condition when
they cannot safely diagnose or repair state.

Job definitions and recovery evidence remain editable until successful
ingestion. They are not authoritative state.

## State Integrity Audit Gate

Before resuming an interrupted run, replacing a job session, recovering a
dispatch, or scheduling new work after suspected interruption, the root
orchestrator MUST execute the State Integrity Audit Gate. This gate is
mandatory; skipping it may cause duplicate side effects, data loss, or
silent state corruption.

### Command Sequence

1. **Initial audit** — `jobctl audit --run <run-root>`
   Reports replay health, protocol hash status, derived snapshot drift,
   unresolved action/dispatch contradictions, active-idle contradictions,
   and side-effect blockers. Examine the `audit_report.findings` and
   `audit_report.facts.blocking_codes` before proceeding.

2. **Rebuild when needed** — `jobctl audit --run <run-root> --rebuild`
   When the initial audit reports `derived_snapshot_drift` or
   `stale_index_or_queue`, run the rebuild audit to regenerate derived
   snapshots from the authoritative event journal and validated worker
   evidence. Do NOT run `--rebuild` when the audit reports
   `journal_corrupt_or_insufficient` or `external_effect_unknown`.

3. **Dry-run recovery** — `jobctl recover --run <run-root> --dry-run`
   Classifies interrupted dispatches, identifies the proposed safe next
   action, and reports completed-result-not-applied cases WITHOUT mutating
   state. Review the dry-run output to confirm the proposed action matches
   expectations before executing.

4. **Execute recovery** — `jobctl recover --run <run-root>`
   After reviewing the dry-run output, execute the actual recovery. Supply
   `--job <job-id> --evidence <evidence.json>` when recovery requires
   worker evidence validation. Use without `--job` only to recover an
   interrupted control-plane commit.

5. **Final audit** — `jobctl audit --run <run-root>`
   After recovery completes, run a final audit to verify the state is
   clean and the normal `jobctl next` loop may resume. If the final audit
   still reports blocking findings, do NOT return to the normal loop.

### Gate Outcomes

| Audit Result | Required Action |
|---|---|
| `clean` (no blocking findings) | Proceed to `jobctl next` |
| `derived_snapshot_drift` or `stale_index_or_queue` | Run `--rebuild`, then dry-run recovery, then execute recovery, then final audit |
| `completed_result_not_applied` | Dry-run recovery to classify, then execute recovery with validated evidence |
| `interrupted_dispatch_recorded_not_sent` or `interrupted_dispatch_sent_no_result` | Dry-run recovery to classify, then execute recovery |
| `external_effect_unknown` | Run configured recovery check (e.g., inspect git history or deployment status) before retrying or accepting completion |
| `journal_corrupt_or_insufficient` | Block automatic recovery; create a recovery investigation job or ask the user |
| `active_idle_contradiction` | Block `jobctl next` from scheduling new domain work until recovery classifies the unresolved evidence |

### Blocking Rules

The audit gate blocks normal resume when ALL of the following are true:
- The run is `active`
- No active job exists (`active_job_id` is null)
- No active dispatch exists (`active_dispatch_id` is null)
- The queue is empty
- Unresolved actions or worker evidence remain

When the gate blocks, the root orchestrator MUST NOT dispatch new domain
work. It MUST classify the evidence and either apply a deterministic repair
through `jobctl recover` or create a recovery investigation job.

## Procedure

1. Run `jobctl audit --run <run-root>`.
2. If the audit reports blocking findings, follow the State Integrity Audit
   Gate command sequence above.
3. Gather direct adapter status, transcript evidence, workspace observations,
   attested artifacts, and required external-effect evidence.
4. Supply the evidence to `jobctl recover --run <run-root> --job <job-id>
   --evidence <evidence.json>`.
5. Use `jobctl recover --run <run-root>` without a job only to recover an
   interrupted control-plane commit.
6. Use `jobctl repair` only for an explicit failed or canceled disposition.
7. Run a final audit before returning to `jobctl next`.

Missing, silent, or ambiguous transport evidence is unknown, not a completed,
canceled, or lost session. Cancellation is not permission to retry. Any
canceled, lost, unavailable, empty-with-uncertain-liveness, or contradictory
transport result exits the normal scheduling loop.

The state keeps append-only attempts. Recovery may classify the active attempt
as `canceled`, `lost`, `unknown`, or `replaced`; only an explicit recovery
result may authorize a new dispatch. A crash after worker creation but before
receipt persistence is reconciled against the pending dispatch before a second
worker can be launched.

For every side-effecting job, recovery evidence must identify the exact
configured check and include direct observation, a reference, and
`retry_safe`, `effect_confirmed`, or `unknown`. External idempotent work also
requires the registered idempotency key. Unknown and confirmed effects do not
authorize replacement. Raw worker responses and attested artifacts are
immutable evidence and cannot be reconstructed from workspace observations.

## Dynamic Recovery

The v6 protocol adds expansion transaction recovery:

### Expansion Transaction Boundaries

1. **Before writes** — no staged bytes, no manifest → nothing to recover
2. **During partial writes** — staged bytes exist but no manifest → replay staging
3. **After manifest, before commit** — manifest staged, not committed → roll-forward commit
4. **After commit** — visibility committed → cleanup
5. **Contradictory bytes** — manifest and staged bytes disagree → block

### Recovery Commands

```text
python jobctl.py recover --run <run-root> --transaction <transaction-id>
```

The transaction ID is returned by `next` when recovery is required.

### Idempotent Recovery

Recovery is idempotent. Replaying a committed expansion returns the existing
result with `idempotent_replay: true`.

### Contradiction Detection

Recovery blocks on:
- Staged bytes digest mismatch with manifest
- Expansion ID mismatch between manifest and staged bytes
- Graph revision mismatch after commit
