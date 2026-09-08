# Recovery Procedure

Load this reference before mutating an interrupted run, resolving contradictory
transport evidence, or handling a possibly repeated external effect.

## State safety

Never manually read, edit, parse, replay, or reconstruct authoritative state
JSON. First run `jobctl audit --run <run-root>`. Then use supported `recover`
or `repair` commands and report an unsupported control-plane condition when
they cannot safely diagnose or repair state.

Input files supplied to `register`, `outcome`, `answer`, `advisory-decision`,
or recovery evidence may be corrected before successful ingestion. They are not
authoritative state.

## Procedure

1. Run `jobctl audit --run <run-root>`.
2. Gather direct transport status, transcript, workspace, report/checkpoint,
   and required external-effect evidence.
3. Supply the evidence to `jobctl recover --run <run-root> --job <job-id>`;
   use `--apply` only after its proposed action is safe.
4. Use `jobctl repair` only for its explicit failed/canceled disposition.
5. Run a final audit before returning to `jobctl next`.

Missing, silent, or ambiguous transport evidence is unknown—not a completed,
canceled, or lost session. For an uncertain non-idempotent external effect,
perform the configured check or escalate; automatic retry is blocked.

Transport evidence has priority for conversation liveness and responses, then
explicit external-system facts, repository/workspace facts, reports or
checkpoints, and persisted status. Report contradictions instead of selecting a
convenient source.

## Trusted v5 Interruption Rules

Cancellation is not permission to retry. Any canceled, lost, unavailable,
empty-with-uncertain-liveness, or contradictory transport result exits the
normal scheduling loop. The root must run `audit`, gather direct adapter status
and transcript evidence, and invoke `recover` before resuming, retrying,
failing, canceling, or creating a replacement attempt.

The v5 state keeps append-only attempts. Recovery may classify the active
attempt as `canceled`, `lost`, `unknown`, or `replaced`; only an explicit
recovery result may authorize a new dispatch. A crash after worker creation but
before receipt persistence is reconciled against the pending dispatch before a
second worker can be launched.

For a non-idempotent side effect, perform the configured external check and
record its result as recovery evidence. Unknown is not negative and is not
permission to repeat the effect. Raw worker responses and attested artifacts
are immutable evidence and cannot be reconstructed from workspace observations.
