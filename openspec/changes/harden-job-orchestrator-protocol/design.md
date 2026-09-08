## Context

The current v4 control plane persists and audits coherent job records, but its trust boundary begins too late. `session` accepts any non-empty caller-supplied string, `outcome` accepts a caller-supplied JSON file, required reports are validated primarily by path and non-empty content, and `completed` means that those structural inputs agree. Prompt delivery, worker identity, raw response provenance, report authorship, completion evidence, and independent verification are not authenticated.

The skill also has an instruction/implementation mismatch. The root is told not to perform domain work but retains enough authority to synthesize all accepted semantic inputs. Worker prompts expose run-relative report paths beside a workspace path, ordinary dependencies do not reliably receive predecessor reports, interruptions are not prominent in the normal loop, and the reusable completion prompt does not match the actual CLI.

The change spans the shared job-orchestrator skill, schemas, control-plane transitions, transport integration, generated prompts, recovery, documentation, and project-level completion guidance. Existing persisted v4 runs are a concrete migration concern, but treating their unauthenticated fields as trusted v6 evidence would preserve the vulnerability.

## Goals / Non-Goals

**Goals:**

- Make it impossible for normal `jobctl` commands to establish trusted execution using a caller-authored session label, altered prompt, synthesized response, or unbound report.
- Give the root a small, explicit control-plane allowlist and move semantic ownership to persistent workers and independent verifiers.
- Preserve exact transport facts in append-only attempts and route interruption or ambiguity through evidence-based recovery.
- Use unambiguous run-scoped artifact identities, prove report freshness and worker association, and propagate dependency reports automatically.
- Represent completion as a worker claim followed by condition-level acceptance, including independent verification where required.
- Keep state transitions deterministic, auditable, crash-safe, and testable with fake transport adapters.
- Make all operator and worker documentation executable against the real CLI and interpreter environment.

**Non-Goals:**

- Prove that arbitrary domain evidence is scientifically correct; configured verifier jobs remain responsible for domain judgment.
- Prevent a machine administrator from tampering with every component, transport credential, and state file. The target is an enforceable adapter/control-plane boundary under the configured trust model.
- Add a hidden sub-scheduler or infer domain workflows from report prose.
- Automatically trust or silently upgrade v4 session, response, report, or completion records.
- Implement transport-specific delivery guarantees inside the scheduler when an adapter cannot provide them.

## Decisions

### 1. Introduce a versioned trusted protocol instead of extending v4 in place

New runs use a new schema version with authenticated dispatches, session attempts, response receipts, artifact attestations, and condition results. v4 records remain explicitly `legacy_unattested`; they are never interpreted as satisfying the new provenance requirements.

Why: changing the meaning of existing fields such as `session_ref`, `outcome`, and `completed` in place would make old records appear stronger than their evidence permits and would complicate audit invariants.

Alternatives considered: mutate v4 schemas in place, or infer provenance for old runs from timestamps and files. Both were rejected because neither can recover facts that were never recorded.

### 2. Make dispatch an adapter-mediated operation with a verifiable receipt

`next` returns an immutable dispatch identity, canonical prompt path, SHA-256 digest, run/job correlation, and adapter requirement. The configured transport adapter reads that dispatch, sends the exact prompt, and returns a receipt containing at least:

```json
{
  "transport": "task",
  "dispatch_id": "DSP-...",
  "native_session_ref": "ses_...",
  "run_id": "RUN-...",
  "job_id": "J001",
  "prompt_sha256": "...",
  "created_at": "...",
  "proof": {"adapter_defined": "..."}
}
```

`jobctl` asks the configured adapter verifier to validate the receipt and rejects caller-authored strings. Fake adapters expose the same verification interface for deterministic tests. Unsupported adapters report that provenance is unavailable; they do not emulate it.

Why: a hash supplied by the root is not proof of delivery. Verification must be rooted in the component that launched the worker and observed the native session reference.

Alternatives considered: retain `--session-ref` with stricter ID syntax, or use a local HMAC key readable by the root. Syntax does not prove origin, and a same-privilege HMAC does not create a meaningful trust boundary.

### 3. Store append-only session attempts and immutable transport events

Each job has `attempts[]` and `active_attempt_id`, not a single mutable session reference. An attempt binds one verified launch receipt to subsequent verified response receipts and records its lifecycle without deleting prior evidence. Only recovery can authorize a replacement attempt after classifying the previous attempt.

Why: interruption, cancellation, and a crash between worker creation and local recording cannot be represented faithfully by a singular field. Attempt history also makes replacement and duplicate-delivery analysis auditable.

Alternatives considered: overwrite `session_ref`, or add `previous_session_ref`. Both lose history after more than one recovery and encourage direct replacement outside recovery.

### 4. Ingest verified raw responses before normalized outcomes

The adapter returns a response receipt binding the attempt, native session, exact raw response bytes, response hash, and receive time. `jobctl` stores the raw response as immutable evidence, parses the normalized outcome from it, and records an accepted outcome only if schema and provenance checks pass.

Malformed but live responses produce a same-session format-repair continuation. An empty response with a confirmed live session produces a response-retrieval continuation. Cancellation, loss, unavailable status, contradictory facts, or uncertain liveness moves the job to recovery. Workspace files never substitute for a worker response.

Why: accepting a second caller-authored outcome file allows the root to replace worker semantics. Preserving raw and accepted forms supports audit without conflating transport receipt with normalization.

Alternatives considered: continue accepting `--outcome <file>` and add a declaration that it was copied exactly. A declaration is not provenance and cannot detect root synthesis.

### 5. Bind worker artifacts to the verified response

Generated prompts give each artifact both a canonical reference and an absolute authorized write path, for example:

```json
{
  "report_ref": "run://RUN-123/jobs/J001/report",
  "report_write_path": "C:/Projects/BlackholeSim/.job-orchestrator/runs/RUN-123/jobs/J001/report.md"
}
```

A completed worker response includes artifact references and SHA-256 digests. At ingestion, `jobctl` resolves each reference within the run, hashes the file, and requires an exact match to the adapter-authenticated response. The accepted artifact record stores the producer job, attempt, response digest, content digest, and acceptance time. Checkpoints use the same model when claimed as recovery evidence.

Why: an existing file at a plausible path does not establish freshness, run identity, worker authorship, or unchanged content.

Alternatives considered: rely on file modification times or delete reports when registering a run. Timestamps are weak provenance, and deletion cannot prove who authored the replacement.

### 6. Propagate immutable dependency artifacts by relationship

When a dependency reaches accepted completion, its accepted report artifact is added to every dependent job's generated context in deterministic dependency order. The prompt includes canonical references, resolved read paths, producer IDs, and content hashes. Registration no longer requires a not-yet-completed dependency report to be listed manually in `related_reports`.

Why: `depends_on` already expresses the semantic relationship, and manual report duplication creates timing problems and stale cross-run references.

Alternatives considered: keep `related_reports` as the only context mechanism. That preserves the documented/implemented mismatch and cannot naturally reference incomplete predecessors.

### 7. Separate completion claims from accepted completion

Completion conditions become structured definitions with stable IDs, descriptions, evidence requirements, and verification mode. Worker and verifier responses return condition results using only `passed`, `failed`, `not_run`, `unavailable`, or `unknown`, with artifact evidence references where required.

A worker completion response creates `completion_claimed`. Self-verifiable jobs become `completed` only when every required result is `passed` and evidence/provenance checks succeed. Conditions configured for independent verification allow their designated verifier jobs to schedule from the claim; only those verifier responses can satisfy the conditions. Failed verifier results lead to `repair_required`; unavailable or unknown required evidence leads to `blocked` or `needs_input` according to the job policy.

Why: a binary worker-authored `completed` status hides the difference between a claim, independent verification, and protocol acceptance.

Alternatives considered: keep `completed` and add free-form verifier reports. Free-form reports cannot deterministically gate state or distinguish missing evidence from failure.

### 8. Require explicit side-effect and recovery policy for every job

Every job declares one of `none`, `repository`, `external_idempotent`, or `external_non_idempotent`. Side-effecting jobs declare the check required before retry and an idempotency key when applicable. Any canceled, lost, unavailable, empty-with-uncertain-status, or contradictory transport event exits the normal loop, requires `audit`, and is reconciled by `recover` before the control plane can resume or create a replacement attempt.

Why: retry safety cannot be inferred after an interruption, and cancellation is transport evidence rather than authorization to replace a worker.

Alternatives considered: keep recovery policy optional and apply conservative defaults. An absent classification is itself ambiguity and should fail registration rather than surface during an incident.

### 9. Return explicit terminal disposition

The terminal operation retains the recognizable `run_complete` operation but includes `run_status` and `successful`, where only an accepted `completed` run is successful. Failed and canceled runs are terminal but never reported as successful completion.

Why: callers need to stop scheduling at every terminal state without conflating termination with goal satisfaction.

Alternatives considered: rename the operation for each disposition. A stable operation plus explicit disposition minimizes control-loop branching while removing semantic ambiguity.

### 10. Make instructions layered and mechanically checked

`SKILL.md` owns the root allowlist and normal loop. `protocol.md` owns state transitions, relationships, claims, and acceptance. `job-protocol.md` owns worker artifact/output rules. `transport-capabilities.md` owns receipt and adapter requirements. `recovery.md` owns interruption, attempt replacement, and side-effect handling. `maintainer-guidance.md` indexes evidence-driven changes and protocol tests. The reusable completion prompt uses commands extracted from or checked against the real parser.

Why: duplicated or misplaced rules drift, while CLI examples without conformance tests become operational hazards.

Alternatives considered: place all detail in `SKILL.md`. That would make the always-loaded instruction too large and retain multiple sources of truth.

## Risks / Trade-offs

- [Transport adapters do not yet provide verifiable receipts] -> Define a strict capability handshake and block trusted execution for unsupported adapters; ship a fake adapter for tests and implement supported production adapters before enabling v6 by default.
- [Same-machine privilege limits absolute authenticity] -> Document the trust model, isolate adapter verification material from the root where the host permits it, and treat failed or unavailable verification as unknown rather than trusted.
- [More states and records increase protocol complexity] -> Keep transitions explicit, use append-only transport events, centralize coherence validation, and cover every state edge with table-driven tests.
- [Independent verification can create dependency deadlocks] -> Validate verifier relationships at registration, allow designated verifiers to schedule from `completion_claimed`, and reject cycles or verifier jobs that depend on final acceptance of the job they verify.
- [Hashing large artifacts adds ingestion cost] -> Hash only declared orchestration artifacts, stream file reads, and record immutable digests once. Expected reports and evidence are small relative to domain workloads.
- [Absolute paths reduce prompt portability] -> Pair paths with canonical `run://` identities and regenerate resolved paths per run; never persist an absolute path as the artifact identity.
- [Strict provenance may block workflows that previously appeared successful] -> Surface precise capability and evidence errors and provide recovery/verification paths instead of permissive fallback.
- [Shared-skill deployment and project prompt updates can drift] -> Version the protocol, update instruction conformance tests, and validate both the shared skill and project-level prompt in the same change.

## Migration Plan

1. Add new schemas, adapter interfaces, and read-only recognition of v4 runs without changing v4 state semantics.
2. Implement v6 registration, dispatch, response ingestion, attempts, artifact records, completion claims, verification gates, recovery, and terminal dispositions behind the new run version.
3. Add fake-adapter, transition, crash-recovery, artifact, completion, and CLI documentation tests before enabling v6 initialization by default.
4. Update all skill references and `AUTONOMOUS_COMPLETION_PROMPT.md`, then run documentation command conformance and the full orchestrator suite.
5. Make new `init` operations create v6 runs. Keep v4 audit/export/recovery available only as explicit legacy operations and label their execution evidence unattested.
6. For an active v4 run, either finish it under its documented legacy semantics or start a v6 replacement run. An explicit migration may preserve job definitions and durable files, but all imported provenance and condition results remain `unknown` until new worker/verifier evidence is collected.
7. Roll back by disabling new v6 initialization while retaining v6 state for audit; do not rewrite v6 records into v4 or discard receipts.

## Open Questions

- Which production transport adapters can expose a verifier API or signed receipt without making proof material available to the root agent?
- Should project-level tool permissions enforce the root allowlist in addition to protocol rejection, and which host environments support that separation?
- Which existing job-definition producers should automatically translate string completion conditions into draft structured conditions for operator review, versus requiring manual conversion?
