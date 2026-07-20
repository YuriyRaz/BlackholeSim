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
