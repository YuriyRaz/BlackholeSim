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

## Trusted v5 Receipts

An adapter used for a trusted v5 run MUST expose a capability profile and
verification methods for launch and response receipts. A launch receipt binds
the transport, dispatch ID, native session reference, run/job correlation,
exact prompt SHA-256, creation time, and adapter proof. A response receipt binds
the attempt, native session, exact raw response, response SHA-256, receive time,
and adapter proof.

The root may relay a receipt but MUST NOT author its native session reference,
proof, prompt digest, or raw response. Receipt verification failure is a hard
error. Unsupported or unknown adapter capability is reported as unavailable and
blocks trusted completion; it is never emulated by accepting a non-empty string.

The fake adapter in `scripts/transport_v5.py` is the conformance adapter. A
production adapter may use a platform-issued task ID and adapter-owned proof,
but it must preserve the same correlation and digest contract.
