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

## Trusted v6 Receipts

An adapter used for a trusted v6 run MUST expose a capability profile and
verification methods for launch and response receipts. A launch receipt binds
the transport, dispatch ID, native session reference, run/job correlation,
exact prompt SHA-256, creation time, and adapter proof. A response receipt binds
the attempt, native session, exact raw response, response SHA-256, receive time,
and adapter proof.

The root may relay a receipt but MUST NOT author its native session reference,
proof, prompt digest, or raw response. Receipt verification failure is a hard
error. Unsupported or unknown adapter capability is reported as unavailable and
blocks trusted completion; it is never emulated by accepting a non-empty string.

A production adapter must be a host Task integration that receives the
platform-issued Task ID and adapter-owned proof from the host; a root-configured
shared-secret HMAC is never production authenticity. Capability negotiation
happens before a run directory is created.

## v6 Receipt Fields

### Launch Receipt

| Field | Type | Description |
|-------|------|-------------|
| `dispatch_id` | string | Dispatch identity |
| `native_session_ref` | string | Transport-native session reference |
| `run_id` | string | Run identity |
| `campaign_id` | string | Campaign identity |
| `job_id` | string | Job identity |
| `graph_revision` | integer | Graph revision at dispatch |
| `graph_generation` | integer | Graph generation at dispatch |
| `prompt_sha256` | string | SHA-256 of dispatched prompt |
| `created_at` | string | RFC 3339 creation timestamp |
| `adapter_proof` | string | Adapter-authenticated proof |

### Response Receipt

| Field | Type | Description |
|-------|------|-------------|
| `attempt_id` | string | Attempt identity |
| `native_session_ref` | string | Transport-native session reference |
| `run_id` | string | Run identity |
| `campaign_id` | string | Campaign identity |
| `job_id` | string | Job identity |
| `graph_revision` | integer | Graph revision at response |
| `graph_generation` | integer | Graph generation at response |
| `response_id` | string | Response identity |
| `raw_response` | string | Exact raw response bytes |
| `received_at` | string | RFC 3339 receive timestamp |
| `status` | string | Response status |
| `session_liveness` | string | Session liveness classification |
| `adapter_proof` | string | Adapter-authenticated proof |
