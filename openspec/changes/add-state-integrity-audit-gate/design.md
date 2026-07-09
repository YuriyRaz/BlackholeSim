## Context

The job orchestrator already separates root control-plane authority from worker execution authority. Workers operate through `workerctl.py` and return evidence; the root orchestrator operates through `jobctl.py` and decides workflow advancement. Recovery guidance exists, but the current protocol does not make a state integrity audit a mandatory gate before resuming interrupted runs or dispatching more work after suspected interruption.

Recent run evidence showed a dangerous contradiction: a worker verification result and `progress.json` indicated completion, while the action remained unresolved, workflow state still marked the node ready, the queue and job index were empty, and the run stayed active with no active job or dispatch. This is a control-plane reconciliation failure, not a normal worker task.

## Goals / Non-Goals

**Goals:**

- Make state integrity audit mandatory before interrupted-run resume, session replacement, dispatch recovery, or post-interruption scheduling.
- Centralize audit, classification, rebuild, and repair behavior in `jobctl.py`.
- Classify recovery findings into deterministic categories with explicit safe handling.
- Rebuild derived snapshots only from authoritative events and validated worker evidence.
- Prevent duplicate side effects by requiring side-effect recovery checks before retry.
- Create recovery investigation jobs only when automatic recovery cannot prove a single safe next action.

**Non-Goals:**

- Do not allow root agents or workers to manually edit durable JSON state.
- Do not turn every interruption into an Architect/product review job.
- Do not change worker authority: workers still never invoke `jobctl.py` or mutate run state.
- Do not update active run protocol snapshots implicitly; frozen run protocols remain frozen unless migration is explicitly authorized.
- Do not change simulation renderer, physics, audio, or UI behavior.

## Decisions

### Decision 1: Add a State Integrity Audit Gate before recovery or resume

The root orchestrator will run the audit gate before dispatching new work after any suspected interruption. The gate checks whether the event journal is replayable, derived snapshots match, unresolved actions/dispatches are classified, and exactly one safe next action exists.

Why: a normal `next` loop assumes state is coherent. After interruption, that assumption is the thing being tested.

Alternatives considered:

- Always resume from `progress.json`: rejected because worker progress is evidence, not control-plane authority.
- Always create an Architect job: rejected because clean interruptions can recover mechanically and product architecture review is the wrong lens for state corruption.
- Require manual JSON inspection: rejected because it violates the job-orchestrator safety model and makes recovery non-repeatable.

### Decision 2: Keep recovery authority in `jobctl.py`

The agent-facing protocol will instruct the root orchestrator to use `jobctl audit`, `jobctl audit --rebuild`, `jobctl recover --dry-run`, and `jobctl recover`. Durable state reads, classification, and mutations stay script-owned.

Why: recovery must be deterministic, idempotent, and safe across repeated attempts.

Alternatives considered:

- Document a manual checklist for agents to inspect files: rejected because it encourages ad hoc parsing and inconsistent fixes.
- Let workers repair their own job state: rejected because workers are intentionally bounded to a dispatch and cannot decide workflow advancement.

### Decision 3: Classify findings before repair

Audit/recovery will classify findings such as:

- `clean`
- `derived_snapshot_drift`
- `stale_index_or_queue`
- `interrupted_dispatch_recorded_not_sent`
- `interrupted_dispatch_sent_no_result`
- `completed_result_not_applied`
- `external_effect_unknown`
- `journal_corrupt_or_insufficient`

Why: repair behavior differs sharply between a disposable index mismatch, a validated but unapplied worker result, and an unknown external side effect. A classification layer prevents blind retry.

Alternatives considered:

- Single generic "corrupt" result: rejected because it does not tell the root orchestrator whether to rebuild, recover, investigate, or ask the user.
- Failure-only handling: rejected because many interruptions are recoverable and should not fail the whole run.

### Decision 4: Use validated evidence precedence

The authoritative event journal remains the primary source for lifecycle state. Derived snapshots can be rebuilt. Worker artifacts (`report.md`, `checkpoint.md`, `progress.json`, and result files) are evidence that may justify a recovery event only after identity and hash validation.

Why: the recovery path must avoid both data loss and accepting spoofed/stale worker output.

Alternatives considered:

- Prefer latest file timestamp: rejected because timestamps do not prove authority.
- Prefer `progress.json` over events: rejected because progress can exist without the control plane accepting the result.

### Decision 5: Make recovery investigation conditional and read-only by default

When audit/recover cannot establish one safe next action, the system may create a recovery investigation job. That job produces a report identifying contradictions, evidence, side effects that must not repeat, and whether user authority is needed. It does not mutate run state unless explicitly authorized.

Why: some failures require human-readable forensic analysis, but making that the default path adds overhead and can obscure mechanical recoveries.

Alternatives considered:

- Always create a recovery Architect job: rejected as unnecessary overhead for clean recoveries.
- Never create investigation jobs: rejected because ambiguous journal/external-effect conflicts need careful analysis before repair.

## Examples

| Situation | Classification | Expected handling |
|-----------|----------------|-------------------|
| Worker result exists, dispatch ID/nonce/session validate, but the action remains unresolved and workflow still marks the node ready | `completed_result_not_applied` | Apply recovery through `jobctl recover`, persist recovery events, resolve the action, advance workflow, and recompute derived state |
| Run is `active` with `active_job_id=null`, `active_dispatch_id=null`, empty queue, and unresolved actions | control-plane idle contradiction, usually paired with another finding | Block `jobctl next` from scheduling new domain work until recovery classifies the unresolved evidence |
| `jobs/index.json` is empty but job records or journal events prove jobs exist | `stale_index_or_queue` | Rebuild disposable indexes from authoritative evidence; preserve job directories |
| `progress.json` says `verification_complete`, but no matching worker result validates | evidence only | Request session status or create a recovery investigation; do not complete the node from progress alone |
| A publish/deploy dispatch may have reached an external system, but local action state is unresolved | `external_effect_unknown` | Run the configured recovery check, such as inspecting git history or deployment status, before retrying or accepting completion |
| Protocol hash in the run manifest does not match the frozen protocol snapshot | `journal_corrupt_or_insufficient` or protocol identity mismatch | Block automatic recovery and require investigation or explicit migration authority |

Concrete current-run style example:

```text
J008 verify dispatch returned a completed result
        |
        v
progress.json says verification_complete and next_permitted_action=finalize
        |
        v
but ACT-297 remains unresolved and workflow still marks verify ready
        |
        v
classification: completed_result_not_applied
repair: validate result identity and apply it through jobctl recovery
```

## Risks / Trade-offs

- Audit gate adds resume latency -> Keep the fast path mechanical: clean audits immediately return to normal `jobctl next`.
- Classification mistakes could approve unsafe retry -> Require external side-effect recovery checks and dry-run review before mutating recovery.
- Rebuild may hide evidence of a malformed snapshot -> Quarantine malformed files and persist recovery events rather than overwriting without trace.
- Recovery investigation jobs could drift into product architecture review -> Constrain their purpose to run-state evidence and safe next action.
- Existing tests may assume older recovery behavior -> Add regression fixtures for completed-result-not-applied, empty index with job directories, and active-idle contradictions.

## Migration Plan

1. Update recovery and protocol references to define the State Integrity Audit Gate and root-agent instructions.
2. Extend `jobctl audit` output to expose required finding classes and machine-readable recovery blockers.
3. Extend `jobctl recover --dry-run` to classify interrupted dispatches and completed-result-not-applied cases without mutation.
4. Extend `jobctl recover` to apply validated recovery events and rebuild derived snapshots safely.
5. Add tests covering clean resume, derived snapshot rebuild, stale index/queue rebuild, completed result reconciliation, unknown side-effect blocking, and investigation-job recommendation.
6. Keep active run protocol snapshots unchanged unless explicit migration is requested; this change applies to future protocol snapshots and local skill guidance.

Rollback is documentation and script-level: revert the protocol/reference changes and the associated `jobctl` behavior while leaving existing run journals intact.

## Open Questions

- Should `jobctl recover` introduce a distinct `waiting_for_recovery` status, or reuse existing `recovering` and `blocked` states?
- Should recovery investigation jobs be a new job type, or ordinary advisory jobs with a stricter recovery-only contract?
- What exact evidence schema should be accepted by `--evidence` for transport session status and external side-effect checks?
