## 1. Versioned Protocol Foundation

- [x] 1.1 Define the new run, job-definition, job-state, dispatch, attempt, launch-receipt, response-receipt, raw-response, artifact, outcome, completion-claim, condition-result, and recovery-evidence schemas.
- [x] 1.2 Add schema tests for required fields, strict additional-property rejection, digest formats, unique attempt IDs, condition IDs, condition statuses, and side-effect classifications.
- [x] 1.3 Add explicit version loading that recognizes v4 as `legacy_unattested` and never interprets v4 session, report, outcome, or completion fields as trusted new-protocol evidence.
- [x] 1.4 Add tests proving new runs use the new version while existing v4 runs remain available for explicit legacy audit and recovery without silent conversion.
- [x] 1.5 Extend atomic persistence and coherence validation for immutable dispatch records, append-only attempts, raw responses, artifact records, claims, and condition results.

## 2. Transport Adapter And Dispatch Provenance

- [x] 2.1 Define the transport adapter capability handshake and receipt-verification interface, including explicit unsupported and unknown results.
- [x] 2.2 Implement a deterministic fake adapter with launch, resume, response, cancellation, loss, transcript-status, and receipt-verification controls for protocol tests.
- [x] 2.3 Implement a supported production Task transport bridge using platform-issued native task IDs and adapter-verifiable receipts, or keep trusted initialization disabled with a precise capability error when the host cannot provide proof.
- [x] 2.4 Persist a pending immutable dispatch before launch and return its dispatch ID, canonical prompt path, prompt SHA-256, run/job correlation, and adapter requirement from `next`.
- [x] 2.5 Replace caller-authored session ingestion with launch-receipt ingestion that verifies adapter proof, exact native session reference, correlation, and prompt digest.
- [x] 2.6 Add tests for genuine receipt acceptance, fabricated session rejection, wrong correlation, altered prompt delivery, duplicate receipt idempotence, and conflicting receipt rejection.
- [x] 2.7 Add crash-reconciliation tests for failure after dispatch persistence, worker creation before receipt persistence, recovered original launch, and unresolved launch status that blocks replacement.

## 3. Attempts, Responses, And Recovery

- [x] 3.1 Replace singular session state with append-only attempts and an active-attempt reference, preserving prior launch and response events through recovery.
- [x] 3.2 Implement adapter-verified raw response ingestion that stores exact response bytes and digest before deriving any normalized outcome.
- [x] 3.3 Bind accepted outcomes to their raw response, attempt, dispatch, and native session, and reject standalone root-authored outcome files.
- [x] 3.4 Implement same-session format-repair operations for malformed live responses and response-retrieval operations for empty responses from confirmed live sessions.
- [x] 3.5 Route canceled, lost, unavailable, contradictory, and empty-with-uncertain-liveness results to recovery without authorizing a direct replacement.
- [x] 3.6 Require every job definition to declare a side-effect class and validate recovery checks and idempotency keys for the applicable classes.
- [x] 3.7 Extend audit and recovery to classify pending dispatches and attempts, reconcile direct adapter evidence, and authorize a replacement attempt only after the previous attempt is resolved.
- [x] 3.8 Add tests for malformed and empty responses, root-authored outcome rejection, cancellation recovery, ambiguous evidence, contradictory evidence, replacement-attempt history, and interrupted non-idempotent effects.

## 4. Run-Scoped Artifact Integrity

- [x] 4.1 Implement canonical `run://` artifact reference parsing and safe resolution to run-owned absolute paths without traversal or cross-run escape.
- [x] 4.2 Update initial and continuation prompts to provide canonical artifact references plus absolute report, checkpoint, and evidence paths.
- [x] 4.3 Extend normalized worker responses with artifact references and SHA-256 digests, and bind accepted artifacts to producer job, attempt, response digest, content digest, and acceptance time.
- [x] 4.4 Reject missing, changed, stale, prior-attempt, wrong-job, and cross-run report or checkpoint claims even when a file exists and is non-empty.
- [x] 4.5 Automatically include accepted dependency reports in dependent prompts in deterministic relationship order, without pre-registering incomplete reports in `related_reports`.
- [x] 4.6 Preserve distinct labels and deduplicate canonical identities when ordinary dependency, advisory, and continuation report contexts coexist.
- [x] 4.7 Add tests for cross-run isolation, repeated job IDs, stale report reuse, root replacement after worker response, missing dependency reports, multi-dependency ordering, and advisory/dependency coexistence.

## 5. Evidence-Gated Completion

- [x] 5.1 Replace string completion conditions with stable structured conditions containing ID, description, required flag, evidence requirement, verification mode, and designated verifier where applicable.
- [x] 5.2 Validate condition uniqueness, verifier existence, verifier authorization, schedulability from claims, and dependency or verifier cycles during registration.
- [x] 5.3 Parse worker and verifier condition results using only `passed`, `failed`, `not_run`, `unavailable`, and `unknown`, requiring accepted artifact evidence for evidence-bearing passes.
- [x] 5.4 Implement `completion_claimed` and accept direct completion only when all required self-verified conditions, report provenance, and evidence checks pass.
- [x] 5.5 Schedule designated verifier jobs from a target claim with the target's accepted report and evidence context, without prematurely marking the target completed.
- [x] 5.6 Apply authorized verifier results to target conditions, transition failed verification to `repair_required`, and route unavailable or unknown required evidence to configured blocked or input handling.
- [x] 5.7 Return `run_complete` with explicit `run_status` and `successful`, setting success only for an accepted completed run.
- [x] 5.8 Add tests for omitted conditions, missing evidence, unauthorized self-approval, verifier pass, verifier defect, unavailable browser evidence, repair flow, successful terminal run, failed terminal run, and canceled terminal run.

## 6. Root And Worker Instructions

- [x] 6.1 Rewrite `SKILL.md` with the closed root allowlist, exact adapter dispatch loop, semantic-artifact prohibition, invalid-response flow, interruption recovery trigger, wait-reason handling, and terminal disposition rules.
- [x] 6.2 Update `protocol.md` with attempts, raw responses, claims, condition acceptance, verifier scheduling, dependency report propagation, and successful-versus-terminal semantics.
- [x] 6.3 Update `job-protocol.md` with exclusive worker ownership, run-scoped artifact paths, artifact digests, structured condition results, same-session formatting repair, and replacement-worker recovery context.
- [x] 6.4 Update `transport-capabilities.md` with adapter verification, dispatch and response receipts, capability negotiation, prompt-delivery proof, session correlation, and unsupported-proof behavior.
- [x] 6.5 Update `recovery.md` with cancellation, ambiguity, crash reconciliation, append-only replacement attempts, side-effect checks, evidence priority, and the prohibition on normal-loop retry before recovery.
- [x] 6.6 Update composite and maintainer guidance to make ordinary dependency report propagation, independent verification, responsibility boundaries, and evidence-driven protocol testing authoritative in the correct references.

## 7. Completion Prompt And Conformance Verification

- [x] 7.1 Rewrite `AUTONOMOUS_COMPLETION_PROMPT.md` to use the resolved skill script path and an interpreter invocation available in the target environment.
- [x] 7.2 Document exact launch-receipt, response-receipt, answer, advisory-decision, audit, recover, and repair command syntax, including which options consume files and which commands return immediate continuation operations.
- [x] 7.3 Correct the sample sequence so every job is started before its response is recorded, exact native task IDs come from verified receipts, and no worker artifacts or outcomes are root-authored.
- [x] 7.4 Document wait reasons separately and state that terminal failed or canceled `run_complete` results are unsuccessful.
- [x] 7.5 Add parser-backed documentation tests for executable CLI examples, option names, script paths, outcome/receipt file inputs, answer continuation behavior, and recovery triggers.
- [x] 7.6 Run all schema, unit, transition, recovery, adapter, artifact, completion, instruction-architecture, and documentation-conformance tests and record the passing command and result.
- [x] 7.7 Run an end-to-end fake-adapter orchestration covering implementation claim, automatic dependency report delivery, independent verification, evidence acceptance, and successful `run_complete`.
- [x] 7.8 Run an end-to-end interruption scenario covering canceled transport, audit, recovery-authorized replacement, append-only attempts, failed required evidence, and unsuccessful terminal disposition.
