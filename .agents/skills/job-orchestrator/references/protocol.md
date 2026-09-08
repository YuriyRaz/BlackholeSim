# Protocol Semantics

This is the canonical protocol reference. The root procedure is in
[SKILL.md](../SKILL.md); field validity is in `schemas/v4/`.

## Scheduling and outcomes

`jobctl next` selects one of `start_job`, `resume_job`, `ask_user`, `wait`, or
`run_complete` from authoritative state without mutation. The root records
transport facts through supported `jobctl` commands.

Workers return one normalized outcome: `completed`, `needs_input`, or
`failed`. `completed` requires a coherent outcome, an accessible required
report, no pending question, terminal required related jobs, and no active
session for that turn. The control plane validates execution coherence, not
domain correctness.

When a worker needs input, the root may answer from existing authority, ask the
user, register advisory jobs, or fail/cancel the job when continuation is not
appropriate. An advisory job is an ordinary job whose report becomes related
input to the origin job.

## Recovery and transport

Recovery classification and mutations are defined by [recovery.md](recovery.md).
Transport-adapter requirements are defined by
[transport-capabilities.md](transport-capabilities.md). A worker contract is
defined by [job-protocol.md](job-protocol.md).

## Workflow composition

The job prompt determines domain workflow and verification. Create another
explicit job when work needs independent scheduling, judgment, reporting,
recovery, or user authority. Maintainer guidance is indexed in
[maintainer-guidance.md](maintainer-guidance.md).

## Trusted v5 Protocol

New trusted runs use schema version 5. A v4 run is `legacy_unattested`: its
session references, report paths, outcomes, and completion state remain usable
only under the v4 rules and never satisfy v5 provenance requirements.

`next` creates an immutable dispatch containing the exact prompt digest. The
transport adapter must return a verifiable launch receipt before a session
attempt exists. Attempts are append-only; recovery is the only operation that
can authorize a replacement attempt.

The adapter returns an immutable raw response receipt. The control plane stores
the exact raw response before normalizing it. An empty response from a confirmed
live session gets a same-session response-retrieval continuation. Malformed
output gets a same-session format-repair continuation. Empty or malformed output
with uncertain liveness requires audit and recovery; workspace files never
substitute for a worker response.

Worker completion is a claim, not acceptance. Structured condition results use
`passed`, `failed`, `not_run`, `unavailable`, or `unknown`. Required independent
conditions are satisfied only by their designated verifier jobs. A terminal
`run_complete` response includes `run_status` and `successful`; failed and
canceled runs are terminal but unsuccessful.

When a dependency is accepted, its worker-attested report is propagated to each
dependent prompt automatically in deterministic order. `related_reports` is
advisory context, not a substitute for dependency propagation or provenance.
