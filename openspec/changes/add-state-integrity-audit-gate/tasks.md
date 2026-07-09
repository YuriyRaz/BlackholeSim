## 1. Protocol And Documentation

- [x] 1.1 Add a State Integrity Audit Gate section to `references/recovery.md` with the required root-orchestrator command sequence: `jobctl audit`, `jobctl audit --rebuild` when needed, `jobctl recover --dry-run`, reviewed `jobctl recover`, then final audit.
- [x] 1.2 Update `references/job-protocol.md` to clarify that interrupted-run recovery is control-plane work handled by `jobctl.py`, while workers continue to use only `workerctl.py`.
- [x] 1.3 Update `.agents/skills/job-orchestrator/SKILL.md` with concrete agent-facing instructions and prompt text for suspected interruption handling, including when not to dispatch new work.
- [x] 1.4 Document that recovery investigation jobs are conditional diagnostics and not ordinary product architecture review jobs.

## 2. Audit Classification

- [x] 2.1 Extend `jobctl audit` output to report replay health, protocol hash status, derived snapshot drift, unresolved action/dispatch contradictions, active-idle contradictions, and side-effect blockers.
- [x] 2.2 Add finding classifications for `clean`, `derived_snapshot_drift`, `stale_index_or_queue`, `interrupted_dispatch_recorded_not_sent`, `interrupted_dispatch_sent_no_result`, `completed_result_not_applied`, `external_effect_unknown`, and `journal_corrupt_or_insufficient`.
- [x] 2.3 Ensure `jobctl audit` blocks normal resume when an active run has no active job, no active dispatch, an empty queue, and unresolved actions or worker evidence.
- [x] 2.4 Ensure protocol hash mismatch is reported as unsafe for automatic recovery.

## 3. Recovery Behavior

- [x] 3.1 Extend `jobctl recover --dry-run` to classify interrupted dispatches without mutating state and to identify the proposed safe next action.
- [x] 3.2 Implement deterministic rebuild behavior for derived snapshot drift and stale index/queue findings using authoritative journal and job evidence.
- [x] 3.3 Implement completed-result reconciliation when dispatch ID, nonce, session ID, protocol hash, contract revision, and artifact hashes validate.
- [x] 3.4 Ensure `progress.json` without a matching validated worker result remains evidence only and does not complete a workflow node.
- [x] 3.5 Ensure dispatches with repository or external side effects require their configured recovery check before retry, acceptance, or replacement dispatch.

## 4. Recovery Investigation Jobs

- [x] 4.1 Define the recovery investigation recommendation path for cases where no single safe automatic next action can be established.
- [x] 4.2 Constrain recovery investigation job contracts to run-state evidence, contradiction analysis, side-effect safety, and recommended next action.
- [x] 4.3 Ensure recovery investigation jobs do not receive state mutation authority unless explicitly authorized.

## 5. Tests And Fixtures

- [x] 5.1 Add tests for clean interrupted resume returning to the normal `jobctl next` loop without an investigation job.
- [x] 5.2 Add tests for derived snapshot drift and stale `jobs/index.json` or queue rebuild.
- [x] 5.3 Add tests for active-idle contradiction blocking normal dispatch.
- [x] 5.4 Add tests for completed worker result present while action/workflow state remains unresolved.
- [x] 5.5 Add tests for `progress.json` completion evidence without a validated worker result.
- [x] 5.6 Add tests for side-effect recovery checks blocking unsafe retry.
- [x] 5.7 Add tests for protocol hash mismatch blocking automatic recovery.

## 6. Validation

- [x] 6.1 Run the job-orchestrator test suite for v3 recovery and protocol behavior.
- [x] 6.2 Run OpenSpec validation for `add-state-integrity-audit-gate`.
- [x] 6.3 Manually verify the new recovery instructions describe what agents must check, how findings are classified, and which fixes are allowed through `jobctl.py`.
