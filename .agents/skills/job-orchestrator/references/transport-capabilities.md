# Transport Capabilities

This is the canonical contract for transport adapters. It describes adapter
capabilities, not a transport API or persistence schema.

## Required capabilities

- Provide a stable, opaque session reference for each job conversation.
- Continue that same session without silently creating a replacement.
- Publish an accurate capability profile; report unsupported or unknown facts
  instead of emulating guarantees the transport does not provide.

## Declared recovery capabilities

Adapters declare whether they can provide session status, transcript access,
cancellation or loss confirmation, and job-ID correlation. Missing evidence is
unknown—not proof that a session stopped, completed, or was canceled.

Recovery combines transport facts with reports, workspace state, and explicit
external-effect evidence. Transport liveness does not establish domain
correctness. See [recovery.md](recovery.md) for the operator procedure.

## Exclusions

The control plane does not emulate delivery guarantees with a local message
outbox, duplicate transcript, message IDs, delivery state, or cancellation
state machine. It records only orchestration facts needed to operate and audit
the run.
