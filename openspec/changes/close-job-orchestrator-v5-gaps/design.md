## Context

The first v5 implementation established schemas, adapter-verifiable receipts, append-only attempts, raw response ingestion, run-scoped artifacts, and evidence-gated completion. Verification nevertheless found four trust-critical gaps: new runs still default to v4, v5 state can be created without a production-capable adapter, verifier result identity is not enforced, and recovery can authorize replacement without checking side-effect evidence. It also found four coherence gaps: verified receipts are not retained, `next` mutates despite being documented as read-only, terminal disposition is derived but not persisted, and the complete legacy-plus-v5 suite was not recorded as passing.

The implementation is split between the repository-local OpenSpec artifacts and the shared skill at `C:\Projects\ai-skills\skills\job-orchestrator`. Existing v4 behavior is a concrete compatibility concern. Existing pre-closure v5 run records are also concrete persisted data, but they lack receipt proof and cannot be silently promoted to the strengthened trust level.

## Goals / Non-Goals

**Goals:**

- Make trusted v5 the normal initialization path while keeping intentional v4 creation explicit.
- Fail before run-state creation when a production transport cannot prove prompt delivery, native Task identity, and worker responses.
- Retain sufficient adapter-issued receipt evidence to revalidate attempt and response provenance during audit.
- Ensure only the configured verifier job can satisfy an independent condition.
- Prevent retry or replacement until configured side-effect checks establish that retry is safe.
- Restore a pure scheduling query and isolate dispatch persistence in an explicit locked mutation.
- Persist terminal run status atomically with the mutation that makes the run terminal.
- Make audit validate the complete trust chain and record a complete passing verification suite.

**Non-Goals:**

- Give legacy v4 records provenance they did not capture.
- Infer missing receipt proof, verifier identity, or side-effect facts from workspace files.
- Implement a host Task transport when the host exposes no adapter or proof interface; such environments fail closed instead.
- Prove domain correctness beyond configured verifier condition results and accepted evidence.
- Replace the existing v5 job model, artifact namespace, or condition-status vocabulary.

## Decisions

### 1. Default initialization to v5 and require explicit legacy selection

`jobctl init` defaults to protocol version 5. Creating a v4 run requires `--protocol-version 4` and returns an explicit `legacy_unattested` marker. Documentation never presents unqualified initialization as a v4 command.

Why: leaving v4 as the parser default silently bypasses every new trust guarantee and contradicts the migration plan.

Alternatives considered: remove v4 creation entirely, or continue requiring `--protocol-version 5`. Removing v4 would strand supported legacy workflows, while opt-in v5 keeps the insecure path as the easiest path.

### 2. Negotiate adapter capabilities before creating v5 state

The configured production adapter must advertise launch-receipt verification, response-receipt verification, native session correlation, exact prompt hashing, and status/recovery evidence. Initialization performs a capability handshake before creating the run directory. If no qualifying adapter is configured, initialization returns a capability error and writes no state.

The production Task bridge is a host integration contract, not the current environment-secret HMAC helper. It must receive the platform-issued Task ID from the component that launches the worker and must produce proof that the root cannot synthesize. The fake adapter remains injectable only through tests or an explicit non-production test harness; it is never selected by normal CLI configuration.

Why: creating a trusted run and failing only at first receipt ingestion permits unusable and misleading trusted state. A secret the root can set does not authenticate facts against the root.

Alternatives considered: retain `JOB_ORCHESTRATOR_TRANSPORT_SECRET` as production proof, or permit initialization with an `unknown` adapter. Both preserve the original provenance weakness.

### 3. Persist immutable receipts and adapter verification metadata

Each attempt stores or references the exact verified launch receipt, its canonical digest, adapter identity, adapter key/proof identity, and verification time. Each raw response stores the equivalent response-receipt evidence. Receipt records are append-only and are linked to dispatches, attempts, raw responses, and accepted outcomes by stable IDs and digests.

Audit revalidates proof through the configured adapter verifier or a retained public verification mechanism. If proof can no longer be checked, audit reports provenance as `unknown`; it never treats prior ingestion as sufficient by itself.

Why: persisting only derived fields proves internal consistency but not how transport facts entered state.

Alternatives considered: persist only a receipt hash, or trust the historical `verified_at` flag. A hash without retrievable bytes cannot be revalidated, and a boolean is caller-controlled state rather than evidence.

### 4. Bind condition-result identity to the authenticated response producer

For every result in a verified response, `verified_by` must equal the response producer job ID. When applying an independent result, that producer must also equal the target condition's configured `verifier_job_id`. Any mismatch rejects the response atomically before changing the verifier or target job.

Why: matching condition IDs without checking `verified_by` allows a designated verifier response to assert another identity and undermines condition authority.

Alternatives considered: ignore `verified_by` and infer identity from the receipt. Inference would avoid forgery but leave persisted semantic data contradictory; requiring both keeps the response self-consistent and auditable.

### 5. Make side-effect checks an authorization gate, not advisory metadata

Recovery evidence for every interrupted side-effecting job includes the configured check identity, direct observation metadata, a result of `retry_safe`, `effect_confirmed`, or `unknown`, and the applicable idempotency key. The recorded check must match the job's recovery policy.

Only `retry_safe` authorizes replacement for repository and external non-idempotent effects. External idempotent work additionally requires the exact registered idempotency key. `effect_confirmed` routes to response/effect reconciliation without repeating the effect; `unknown` or contradictory evidence leaves the job blocked. Jobs classified `none` require transport classification but no effect check.

Why: checking only that a policy exists does not prevent duplicate or unsafe effects.

Alternatives considered: authorize external-idempotent retries solely from an idempotency key, or let the operator declare retry safety in a free-form reason. The first ignores provider behavior and the second is not structured direct evidence.

### 6. Separate pure scheduling from locked dispatch preparation

`jobctl next` becomes a pure query. For queued work it returns `prepare_dispatch` with the selected job and current state revision, but does not write a prompt, dispatch, or status. A new `prepare-dispatch` mutation acquires the run lock, revalidates eligibility and revision, renders and persists the exact prompt and dispatch, transitions the job to `starting`, and returns `start_job`.

Same-session continuations returned by `answer` or response repair remain explicit mutations because those commands already record a fact. They persist their continuation dispatch atomically before returning `resume_job`.

Why: dispatch creation is a real authoritative mutation. Separating selection from preparation preserves repeatable inspection and closes scheduling races without pretending mutation is read-only.

Alternatives considered: document `next` as mutating, or keep mutation but add `peek`. Both retain surprising behavior in the primary control-loop query and differ from the established v4 contract.

### 7. Persist terminal status in the same mutation that makes it true

Response ingestion, repair, recovery, and verifier-result application recompute the run disposition after validating proposed job changes. If the run becomes terminal, the same locked operation writes the job changes and terminal `run.json` status as one recoverable commit sequence. `next` validates persisted-versus-derived status and returns `run_complete` with `successful` only when both are coherent.

Why: returning terminal status while `run.json` remains active weakens restart and audit semantics.

Alternatives considered: let read-only `next` persist terminal status, or add a manual finalize command. The first violates query purity; the second leaves an avoidable window of incoherence.

### 8. Treat pre-closure v5 runs as a distinct trust revision

The strengthened persisted format gains an explicit protocol revision. Existing v5 runs without retained receipts are classified `v5_preclosure_unattested` and remain available for read-only audit/export. They cannot be migrated to trusted receipt provenance by copying derived state. Active work must restart under the closed protocol or collect fresh transport, worker, and verifier evidence through an explicit supported migration path.

Why: mutating strict schemas in place would either reject existing records opaquely or falsely upgrade their trust.

Alternatives considered: silently add empty receipt fields, or bump every record to an unrelated protocol name. Empty fields do not create evidence; an explicit v5 trust revision communicates the actual migration boundary.

### 9. Expand audit and require complete verification evidence

Audit checks version/revision classification, receipt proof, dispatch/attempt/response linkage, append-only identity, artifact content hashes, condition-result producer authority, recovery authorization, and persisted run disposition. Tests include fail-closed initialization, receipt revalidation, verifier mismatch, side-effect outcomes, pure repeated `next`, stale-revision dispatch preparation, terminal persistence, pre-closure classification, documentation parsing, and full v4 regression coverage.

Why: focused v5 tests can pass while legacy behavior or cross-cutting instruction architecture regresses.

Alternatives considered: continue relying on selected test files. That does not satisfy the task or provide archive-quality evidence.

## Risks / Trade-offs

- [Default v5 may make unconfigured environments unable to initialize] -> Return a precise adapter capability report before writing state and document explicit v4 legacy creation when trusted execution is unavailable.
- [Production host adapter API may not exist] -> Implement the capability boundary and fail closed; do not substitute a caller-controlled HMAC. Track host integration separately if the host must add the bridge.
- [Receipt retention increases state size] -> Store compact canonical JSON receipts and proof references; reports and raw responses dominate expected storage, so added receipt overhead is small.
- [Receipt revalidation depends on adapter/key availability] -> Retain adapter identity and verification metadata and report unavailable proof as `unknown`, never as valid.
- [Two-step scheduling adds one CLI operation] -> Return exact next-command arguments and state revision from `next`; reject stale preparation deterministically.
- [Terminal multi-file persistence can be interrupted] -> Use the existing atomic predecessor/recovery pattern or a small transaction manifest, and add crash-point tests around job/run writes.
- [Strict side-effect evidence blocks more retries] -> Surface the exact missing check, expected result, and idempotency key instead of falling back to permissive behavior.
- [Full suite duration exceeds short tool timeouts] -> Use a documented extended timeout and record the exact command, exit code, test count, and result artifact.

## Migration Plan

1. Add protocol-revision classification and schemas for retained receipts, adapter metadata, recovery authorization, and terminal coherence.
2. Implement adapter capability negotiation and change the CLI default only after fail-closed tests pass.
3. Add pure `next` plus locked `prepare-dispatch`, then migrate control-loop documentation and parser tests together.
4. Enforce verifier identity and side-effect authorization before enabling replacement attempts under the new revision.
5. Persist and audit terminal run status, including crash recovery between job and run writes.
6. Classify existing pre-closure v5 runs as unattested; do not rewrite them into trusted state. Restart active runs or collect fresh evidence through an explicit migration tool.
7. Run focused security tests, all v5 tests, all v4 tests, instruction architecture tests, and the complete suite with an extended timeout. Store the final passing output.
8. Roll back by disabling new trusted initialization while preserving new-revision state for audit. Do not downgrade retained receipts or terminal records to the pre-closure format.

## Open Questions

- Which host component will expose the production Task adapter launch and proof interface? Until one is available, trusted initialization intentionally remains unavailable.

## v6 Evolution Note

The following clarifies how the v6 implementation supersedes the v5 spec terminology:

- **No v4 or v5 runtime exists.** `reject_v5_or_earlier()` raises for protocol versions below v6. There is no code path that creates or loads a v4 or v5 run at runtime.
- **`classify_run_protocol` returns `"trust": "untrusted"` for v5.** The `v5_preclosure_unattested` classification described in the spec is superseded by this unified rejection.
- **Receipt retention is implemented in v6.** Verified launch and response receipts are stored atomically as part of the v6 run lifecycle, fulfilling the receipt-retention requirements under the v6 protocol.
- **v5 test files do not exist.** The test suite covers v6 behavior exclusively; legacy v4 regression tests pass because `reject_v5_or_earlier()` is the entry point.
- **Spec terminology was written for v5.** The requirements about `legacy_unattested`, `v5_preclosure_unattested`, and trusted v5 initialization are preserved as historical specification but do not describe v6 runtime behavior.
