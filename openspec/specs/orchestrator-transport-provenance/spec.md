# orchestrator-transport-provenance

## Purpose

Ensure all transport interactions—launches, responses, and interruptions—are authenticated, append-only, crash-safe, and explicitly classified by side-effect type, preventing unverified or contradictory state mutations.

## Requirements

### Requirement: Adapter-authenticated launch receipt
A trusted session attempt SHALL require a receipt verified by the configured transport adapter. The receipt MUST bind the transport name, dispatch identity, native session reference, run ID, job ID, exact prompt digest, creation time, and adapter proof. Caller-authored aliases, reconstructed IDs, descriptive labels, and unverified strings MUST be rejected.

#### Scenario: Genuine adapter receipt
- **WHEN** the configured adapter verifies a launch receipt whose correlation and prompt digest match the pending dispatch
- **THEN** the control plane records a trusted session attempt with the exact native session reference

#### Scenario: Fabricated session label
- **WHEN** a caller supplies a non-empty session label without a verifiable adapter receipt
- **THEN** the control plane rejects the session fact and leaves the dispatch unresolved

### Requirement: Append-only session attempts
Each job SHALL preserve an append-only sequence of session attempts and SHALL identify at most one active attempt. Creating a replacement attempt MUST require a recovery decision that classifies the prior attempt; normal scheduling MUST NOT overwrite or bypass an existing attempt.

#### Scenario: Recovery-authorized replacement
- **WHEN** recovery confirms that the prior attempt is unavailable and authorizes replacement
- **THEN** the next verified launch receipt appends a new attempt while retaining the prior attempt and recovery decision

#### Scenario: Direct replacement after cancellation
- **WHEN** a transport invocation is canceled and the root attempts to launch another worker without recovery authorization
- **THEN** the control plane rejects the replacement launch

### Requirement: Crash-safe launch reconciliation
The protocol SHALL represent a pending dispatch before transport launch and SHALL reconcile a worker created before local receipt persistence by querying direct adapter evidence during audit and recovery. It MUST NOT launch a second worker while the first launch remains possible but unclassified.

#### Scenario: Crash after worker creation
- **WHEN** the adapter created a worker but the controller crashed before recording the launch receipt
- **THEN** recovery correlates the adapter receipt to the pending dispatch and records the original attempt without launching a replacement

#### Scenario: Launch status unavailable after crash
- **WHEN** recovery cannot establish whether the pending dispatch created a worker
- **THEN** the job remains blocked or recovering until operator evidence resolves retry safety

### Requirement: Verifiable raw response receipt
Every accepted worker response SHALL be bound to the active attempt by an adapter-verified receipt containing the native session, response digest, receive time, and exact immutable raw response. The accepted normalized outcome SHALL retain a reference to that raw response and MUST NOT replace it.

#### Scenario: Response matches active attempt
- **WHEN** the adapter verifies a raw response receipt for the active attempt and its content is schema-valid
- **THEN** the control plane stores the immutable raw response and records the normalized outcome derived from it

#### Scenario: Response belongs to another session
- **WHEN** a response receipt identifies a different run, job, dispatch, attempt, or native session
- **THEN** the control plane rejects it without mutating the job outcome

### Requirement: Recovery-first interruption handling
Canceled, lost, unavailable, contradictory, or ambiguous transport results, including an empty response with uncertain session status, SHALL exit the normal scheduling loop. The root MUST run audit, gather direct transport evidence, and invoke recovery before resume, retry, replacement, failure, or cancellation is authorized.

#### Scenario: Transport cancellation
- **WHEN** the transport reports that a worker invocation was canceled
- **THEN** `next` does not authorize a replacement and recovery is required

#### Scenario: Contradictory evidence
- **WHEN** transport status, response receipts, artifact state, and persisted state disagree
- **THEN** recovery reports the contradiction rather than selecting the evidence most convenient for completion

### Requirement: Explicit side-effect classification
Every registered job SHALL declare exactly one side-effect class from `none`, `repository`, `external_idempotent`, or `external_non_idempotent`. A side-effecting job SHALL declare its recovery check, and an idempotent external job SHALL declare its idempotency key. Registration MUST reject missing or incoherent classifications.

#### Scenario: External non-idempotent job registration
- **WHEN** a job declares `external_non_idempotent` with a concrete recovery check
- **THEN** the prompt and recovery flow require that check before any interrupted retry

#### Scenario: Side-effect classification omitted
- **WHEN** a job definition has no side-effect classification
- **THEN** registration fails before the job enters the queue
