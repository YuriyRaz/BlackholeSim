## ADDED Requirements

### Requirement: Root control-plane allowlist
The job-orchestrator skill SHALL define the root as a control-plane operator limited to run initialization, job registration, next-operation selection, adapter launch or resume, exact transport-fact ingestion, user-answer handling, audit, recovery, repair, and final status relay. The root MUST NOT perform repository investigation, application editing, domain testing, verification, semantic artifact authorship, outcome synthesis, or domain acceptance for an orchestrated job.

#### Scenario: Root receives a domain task
- **WHEN** domain investigation, implementation, testing, verification, or synthesis is required
- **THEN** the root creates or resumes an explicit worker job instead of performing the work directly

#### Scenario: Root attempts to substitute semantic work
- **WHEN** the root has workspace observations or files but no verified worker response
- **THEN** the control plane does not accept those observations or files as a worker outcome

### Requirement: Exact generated prompt delivery
The control plane SHALL bind every start and continuation dispatch to the exact generated prompt bytes and SHA-256 digest. A worker session MUST NOT become trusted unless the transport receipt verifies that those exact bytes were delivered without root-authored prefixes, suffixes, summaries, corrections, or replacements.

#### Scenario: Prompt delivered verbatim
- **WHEN** the adapter receipt contains the expected dispatch identity and prompt digest
- **THEN** the control plane accepts the prompt delivery fact for that attempt

#### Scenario: Prompt was modified
- **WHEN** the delivered prompt digest differs from the generated prompt digest
- **THEN** the control plane rejects the session receipt and does not start a trusted attempt

### Requirement: Exclusive worker semantic ownership
The semantic content of a job's report, checkpoint, raw response, normalized outcome, completion claim, and condition results SHALL originate from the assigned worker or designated verifier through a verified transport response. The root MUST NOT create, complete, repair, summarize, replace, or semantically modify those artifacts.

#### Scenario: Verified worker response supplies outcome
- **WHEN** a verified response contains a valid normalized outcome and worker-bound artifact digests
- **THEN** the control plane may accept the outcome and artifacts after all schema and coherence checks pass

#### Scenario: Root-authored outcome file is supplied
- **WHEN** an outcome is supplied without a response receipt from the active worker attempt
- **THEN** the control plane rejects it regardless of whether its JSON schema is valid

### Requirement: Invalid worker response handling
The normal loop SHALL distinguish valid, malformed, empty, and uncertain worker responses. A malformed response from a confirmed live session SHALL produce a same-session formatting-repair continuation, and an empty response from a confirmed live session SHALL produce a same-session response-retrieval continuation. An empty response with uncertain session status MUST enter recovery and MUST NOT be inferred from workspace state.

#### Scenario: Malformed response from live worker
- **WHEN** the adapter verifies a non-empty response that cannot be normalized and confirms the session remains resumable
- **THEN** the control plane returns a `resume_job` operation for formatting repair on the same native session

#### Scenario: Empty response with unknown liveness
- **WHEN** the adapter returns no response and cannot establish whether the session remains available
- **THEN** the job exits the normal loop and requires audit and recovery

### Requirement: Operational instructions match the control plane
The skill and reusable completion instructions SHALL document the actual script location, supported interpreter invocation, command names, option names, file-valued inputs, immediate continuation results, wait reasons, recovery triggers, and terminal status semantics. Documented command examples MUST be checked against the real CLI parser.

#### Scenario: Documentation command conformance
- **WHEN** maintainers run the instruction conformance tests
- **THEN** every executable `jobctl` example parses using the documented command and options

#### Scenario: Answer produces continuation
- **WHEN** the root records a valid answer for a waiting job
- **THEN** the instructions require it to process the returned `resume_job` operation immediately rather than call `next` as if no continuation was returned
