## 1. Trusted Protocol Revision And Migration

- [x] 1.1 Add a closed-v5 protocol revision marker and strict schemas for adapter binding, retained launch receipts, retained response receipts, receipt links, recovery authorizations, and terminal commit metadata.
- [x] 1.2 Classify existing v4 runs as `legacy_unattested`, existing pre-closure v5 runs as `v5_preclosure_unattested`, and closed-revision v5 runs as trusted only when required records validate.
- [x] 1.3 Block trusted mutation of pre-closure v5 records while preserving explicit read-only audit and export behavior.
- [x] 1.4 Add migration tests proving derived session, digest, outcome, or artifact fields cannot promote a pre-closure run without adapter-issued receipt proof.
- [x] 1.5 Add schema and loader tests for missing revision fields, unknown revisions, strict nested receipt records, and trust classifications.

## 2. Adapter Capability And Trusted Initialization

- [x] 2.1 Extend the production adapter contract with capability negotiation for launch proof, response proof, native Task ID correlation, prompt hashing, status evidence, and proof revalidation.
- [x] 2.2 Add a host Task adapter entry point that consumes host-issued Task IDs and proof-bearing launch/response facts without accepting a root-configured shared secret as production authenticity.
- [x] 2.3 Restrict `FakeTransportAdapter` and caller-controlled HMAC adapters to explicit test harnesses and reject them during normal trusted CLI initialization.
- [x] 2.4 Perform adapter capability negotiation before creating a v5 run directory and return a field-specific error with no filesystem mutation when capability is missing or unknown.
- [x] 2.5 Change unqualified `jobctl init` to v5 and require `--protocol-version 4` for intentional legacy creation, returning `legacy_unattested` in the result.
- [x] 2.6 Add tests for capable Task startup, missing adapter, partial capabilities, fake production adapter rejection, no-state-on-failure, v5 default, and explicit v4 creation.

## 3. Receipt Retention And Auditability

- [x] 3.1 Persist canonical verified launch receipt bytes or immutable references, receipt digest, adapter identity, proof identity, and verification time before activating an attempt.
- [x] 3.2 Persist canonical verified response receipt evidence before accepting raw response, outcome, artifact, or condition state.
- [x] 3.3 Link dispatches, attempts, raw responses, outcomes, artifacts, and condition claims to their retained receipt IDs and digests, rejecting missing or contradictory links.
- [x] 3.4 Extend adapter verification so audit can revalidate retained proofs or report proof availability as unknown without certifying trust.
- [x] 3.5 Add tests for receipt round trips, proof tampering, unavailable historical verifier, cross-attempt receipt reuse, duplicate idempotence, and atomic rejection without partial records.

## 4. Verifier Authorization

- [x] 4.1 Require every condition result's `verified_by` to equal the authenticated response producer job before normalizing the response.
- [x] 4.2 Require the authenticated producer and `verified_by` to equal each independent condition's configured `verifier_job_id` before attaching results to a target claim.
- [x] 4.3 Reject unauthorized or identity-mismatched verifier responses atomically before changing the verifier job, target claim, artifacts, attempts, or run status.
- [x] 4.4 Add tests for matching verifier identity, forged `verified_by`, non-designated workers with matching condition IDs, evidence-bearing verifier passes, and unchanged state after rejection.

## 5. Side-Effect Recovery Authorization

- [x] 5.1 Replace permissive side-effect recovery metadata with structured check identity, direct observation, `retry_safe|effect_confirmed|unknown` result, reference, and idempotency-key fields.
- [x] 5.2 Validate that supplied recovery evidence names the exact configured check and comes from an accepted direct evidence source.
- [x] 5.3 Permit replacement for `none` jobs after transport classification, require `retry_safe` for repository and external non-idempotent jobs, and require `retry_safe` plus the registered key for external idempotent jobs.
- [x] 5.4 Route `effect_confirmed` to effect/response reconciliation and keep unknown or contradictory effect state blocked without replacement eligibility.
- [x] 5.5 Persist a recovery authorization record and require every replacement dispatch and attempt to reference it while preserving prior attempts.
- [x] 5.6 Add tests for missing and mismatched checks, wrong idempotency key, safe retry, confirmed effect, unknown effect, no-effect replacement, and direct replacement rejection.

## 6. Pure Scheduling And Locked Dispatch Preparation

- [x] 6.1 Refactor v5 `next` into a byte-for-byte read-only query that returns `prepare_dispatch` with the selected job ID and expected state revision.
- [x] 6.2 Add `prepare-dispatch` CLI and core mutation paths that lock the run, revalidate eligibility and revision, persist the exact prompt and immutable dispatch, transition to `starting`, and return `start_job`.
- [x] 6.3 Reject stale revisions, ineligible jobs, missing recovery authorization, duplicate concurrent preparation, and changed dependency evidence without writing state.
- [x] 6.4 Preserve atomic continuation-dispatch creation in `answer`, malformed-response repair, and empty-response retrieval while returning `resume_job` for the existing session.
- [x] 6.5 Add purity snapshot tests for repeated queued, waiting, and terminal `next` calls plus locking, stale-revision, concurrent-preparation, and continuation tests.

## 7. Terminal Persistence And Expanded Audit

- [x] 7.1 Add a recoverable commit mechanism that atomically coordinates final job mutation and terminal `run.json` status/revision persistence.
- [x] 7.2 Recompute and persist `completed`, `failed`, or `canceled` run disposition from response, verifier, repair, and recovery mutations that make the run terminal.
- [x] 7.3 Make loading, `next`, and audit reject or report persisted-versus-derived terminal mismatches instead of silently deriving over them.
- [x] 7.4 Add crash recovery for interruption before job write, between job and run writes, and after run write but before command response.
- [x] 7.5 Expand v5 audit to validate protocol revision, adapter binding, receipt proof, all receipt links, append-only attempts, artifact digests, verifier authority, recovery authorization, and terminal disposition.
- [x] 7.6 Add tests for successful, failed, and canceled terminal persistence; mismatch rejection; interrupted commits; unknown proof; unauthorized verifier state; and changed artifacts.

## 8. Instructions And Complete Verification

- [x] 8.1 Update `SKILL.md` and protocol references for v5-by-default initialization, explicit legacy creation, adapter prerequisites, pure `next`, `prepare-dispatch`, retained receipts, recovery evidence, and persisted terminal status.
- [x] 8.2 Update `AUTONOMOUS_COMPLETION_PROMPT.md` with the final parser-valid commands, adapter capability failure behavior, two-step scheduling loop, receipt handling, and terminal semantics.
- [x] 8.3 Update parser-backed documentation tests and remove claims that a caller-controlled HMAC constitutes a production Task bridge.
- [x] 8.4 Run focused activation, receipt, verifier, recovery, scheduling, terminal, audit, and migration tests using Python 3.14.2 and record the command and result.
- [x] 8.4a Add a shared v5 test-run fixture that binds `FakeTransportAdapter` only through the explicit test-harness path and migrate every direct v5 initialization helper to use it.
- [x] 8.4b Migrate v5 lifecycle tests from mutating `next` to the read-only `next` plus locked `prepare-dispatch` sequence, preserving dedicated byte-for-byte purity assertions.
- [x] 8.4c Update v5 schema, loader, classification, proof, adapter-binding, retained-receipt, terminal-commit, and strict nested-record fixtures for the closed revision.
- [x] 8.4d Update v5 recovery and audit fixtures for structured side-effect checks, idempotency keys, retained authorization links, and explicit adapter-based proof revalidation.
- [x] 8.4e Update all v4 CLI initialization fixtures to pass `--protocol-version 4` and assert the `legacy_unattested` result marker without changing v4 behavior.
- [x] 8.4f Add a regression test proving rejected `prepare-dispatch` requests, including missing recovery authorization, leave prompt bytes, dispatches, job state, revisions, and run state unchanged; fix any implementation path that writes before authorization validation.
- [x] 8.4g Run the migrated focused v4/v5, documentation, schema, recovery, scheduling, and terminal subsets and record the result before starting the complete-suite gates.
- [x] 8.5 Run all v5 tests and all v4 regression tests separately with sufficient timeout, recording exit codes and test counts.
- [x] 8.6 Run the complete `pytest` suite with an extended timeout until it finishes with exit code zero, and persist the final output as verification evidence.
- [x] 8.7 Run strict OpenSpec validation and verify both this follow-up and the original hardening change have no remaining critical protocol findings before archive.
- [x] 8.8 Update spec vocabulary to match v6 implementation: replace legacy_unattested and v5_preclosure_unattested with documentation of v6 classification behavior, and add a v6 evolution note to design.md.
