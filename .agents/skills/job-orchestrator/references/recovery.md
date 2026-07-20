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
