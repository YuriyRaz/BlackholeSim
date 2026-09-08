## Why

Verification of `harden-job-orchestrator-protocol` found that the v5 implementation can still default new runs to legacy v4, initialize without a usable production adapter, accept inadequately authorized verifier results, and authorize interrupted retries without enforcing configured side-effect evidence. Additional state and audit mismatches prevent the persisted record from fully supporting the trust guarantees described by the protocol.

## What Changes

- Make trusted v5 the default for new runs and require an explicit legacy-v4 selection when legacy execution is intentionally requested.
- Introduce a production Task transport adapter integration that preserves the platform-issued native task ID and produces adapter-verifiable launch and response receipts; if the host cannot provide these capabilities, reject trusted-run initialization with a precise capability error.
- Persist verified launch and response receipts, including proof material or an immutable proof reference, so audits can revalidate how each attempt and response entered authoritative state.
- Require every independent condition result to be authenticated by, and identify, the configured verifier job before it can alter the target completion claim.
- Enforce configured recovery checks and idempotency requirements before interrupted side-effecting jobs can be retried or replaced; unknown or contradictory effect state remains blocked.
- Reconcile `next` semantics with implementation reality by making dispatch creation an explicit locked mutation while preserving pure scheduling inspection through a separate read-only operation or documented phase.
- Persist terminal run disposition in `run.json` atomically when jobs derive a terminal state, while keeping `run_complete` explicit about success versus unsuccessful termination.
- Expand v5 audit to validate persisted receipt proofs, append-only attempts, dispatch/response linkage, artifact digests, verifier authority, recovery authorization, and persisted run status.
- Correct documentation and parser-backed examples to describe the final default version, adapter prerequisites, mutation semantics, receipt retention, recovery evidence, and terminal persistence.
- Migrate the pre-closure v4 and v5 test suites to the final protocol contract instead of adding compatibility behavior that silently restores v4 defaults, mutating `next`, or permits unauthenticated v5 fixtures.
- Require rejected `prepare-dispatch` operations, including missing recovery authorization, to leave prompt bytes, dispatches, job state, revisions, and run state byte-for-byte unchanged.
- Add focused and end-to-end regression coverage, then run and record the complete legacy-plus-v5 test suite rather than only selected v5 files.
- **BREAKING**: An unqualified `jobctl init` creates v5, and v4 creation requires an explicit legacy option. Trusted initialization and interrupted retries now fail closed when transport or side-effect evidence is unavailable.

## Capabilities

### New Capabilities

- `orchestrator-v5-activation`: Trusted-by-default initialization, production Task adapter capability negotiation, fail-closed startup, and auditable receipt retention.
- `orchestrator-v5-authorization`: Verifier identity enforcement and recovery authorization based on configured side-effect and idempotency evidence.
- `orchestrator-v5-state-coherence`: Locked dispatch mutation, read-only scheduling semantics, terminal run persistence, expanded audits, and complete protocol verification evidence.

### Modified Capabilities

None. The repository's main OpenSpec catalog does not yet contain archived job-orchestrator capabilities; this follow-up defines the remaining externally observable v5 behavior directly.

## Impact

- Affects the shared job-orchestrator CLI, v5 state engine, transport adapter contract, schemas, audit/recovery transitions, run initialization, and test infrastructure.
- Requires a concrete Task transport integration or a host capability check that blocks v5 startup before jobs are registered.
- Changes CLI defaults and legacy-run creation instructions.
- Adds persisted receipt/proof records and terminal run updates, requiring schema and migration handling for v5 runs created by the prior implementation.
- Updates `SKILL.md`, protocol references, recovery guidance, transport guidance, and `AUTONOMOUS_COMPLETION_PROMPT.md`.
- Requires full-suite execution with a recorded passing result before either this follow-up or the original protocol-hardening change is archived.
- Requires migration of shared-skill test fixtures and parser assertions: v5 tests use an explicit test-harness adapter and the two-step `next`/`prepare-dispatch` loop, while v4 tests explicitly request `--protocol-version 4`.
- Requires a regression test for authorization rejection before prompt persistence; the current preparation path must not leave a changed prompt when replacement authorization is absent.

## Verification Closure

The remaining archive gate is a contract migration, not a request to weaken the
closed protocol. Existing tests were written for the pre-closure behavior and
currently assume that direct v5 initialization can discover a fake adapter,
that `next` returns and persists `start_job`, and that an unqualified CLI init
creates v4. Those assumptions must be updated in the test infrastructure and
fixtures.

The migration will centralize a v5 test-run helper that binds
`FakeTransportAdapter` only with an explicit test-harness flag, plus a helper
that performs `next` inspection followed by locked dispatch preparation. It
will update v5 schema fixtures for the closed revision, adapter binding,
retained receipt links, and structured recovery evidence. It will update v4
CLI fixtures to pass `--protocol-version 4` and expect the
`legacy_unattested` result marker.

The final verification sequence remains mandatory:

1. Run all v5 tests and all v4 regression tests separately, recording exit codes and counts.
2. Run the complete `pytest` suite with the extended timeout until exit code zero.
3. Retain the successful output before verification and archive of this change.
