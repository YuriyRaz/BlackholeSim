## ADDED Requirements

### Requirement: Condition results identify the authenticated producer
Every condition result in a verified worker response SHALL have `verified_by` equal to the producer job identified by that response's authenticated receipt. A mismatch MUST reject the response atomically before either producer or target state changes.

In the v6 implementation, the v5 `verified_by` field is replaced by `producer_job_id` on the condition result record. The producer identity is still validated against the authenticated receipt, but the field name and storage location differ.

#### Scenario: Verifier identity matches receipt producer
- **WHEN** a response from verifier job `J002` contains results with `verified_by: J002`
- **THEN** the control plane may evaluate those results against conditions assigned to `J002`

#### Scenario: Verifier claims another identity
- **WHEN** a response authenticated for `J002` contains a result with `verified_by: J003`
- **THEN** the control plane rejects the response and leaves all job and claim records unchanged

### Requirement: Independent results require designated verifier authority
An independent target condition SHALL be satisfiable only when the authenticated response producer and `verified_by` both equal the condition's configured `verifier_job_id`. Matching condition IDs alone MUST NOT grant authority.

#### Scenario: Designated verifier passes condition
- **WHEN** the designated verifier returns an authenticated `passed` result for its assigned target condition
- **THEN** the result may satisfy that target condition after evidence validation

#### Scenario: Non-designated worker uses matching condition ID
- **WHEN** another authenticated worker returns a result whose condition ID matches the target condition
- **THEN** the control plane does not attach or apply the result to the target claim

### Requirement: Recovery evidence matches the configured side-effect check
Recovery for a side-effecting job SHALL require structured evidence naming the exact configured recovery check, direct observation metadata, and a result of `retry_safe`, `effect_confirmed`, or `unknown`. Evidence for a different check, indirect assumptions, or free-form declarations MUST NOT authorize retry.

In the v6 implementation, the v5 `retry_safe` and `effect_confirmed` result values are unified into the `recovery_check` field. The check identity is still validated against the registered job policy, but the evidence structure uses a single recovery check enum rather than separate safe/confirmed values.

#### Scenario: Configured check establishes retry safety
- **WHEN** direct recovery evidence names the job's configured check and reports `retry_safe`
- **THEN** recovery may authorize replacement subject to the job's side-effect class and idempotency rules

#### Scenario: Check identity does not match
- **WHEN** recovery evidence names a different check than the registered job policy
- **THEN** recovery rejects the authorization without changing the active attempt

#### Scenario: Effect state is unknown
- **WHEN** the configured check reports `unknown` or evidence is contradictory
- **THEN** the job remains blocked and no replacement dispatch is eligible

### Requirement: Retry authorization follows side-effect class
Jobs classified `none` SHALL require transport recovery classification but no side-effect check. Repository and external non-idempotent jobs MUST require `retry_safe` before replacement. External idempotent jobs MUST require `retry_safe` and the exact registered idempotency key before replacement.

#### Scenario: Non-idempotent effect is confirmed
- **WHEN** direct evidence reports `effect_confirmed` for an interrupted external non-idempotent job
- **THEN** recovery blocks replay and routes the job to effect or response reconciliation

#### Scenario: Idempotent retry uses wrong key
- **WHEN** an external idempotent retry supplies an idempotency key different from the registered key
- **THEN** recovery rejects replacement authorization

#### Scenario: No-effect job is lost
- **WHEN** transport evidence confirms a `none` side-effect job was lost
- **THEN** recovery may authorize replacement without a side-effect check

### Requirement: Recovery authorization is retained and linked
Every replacement attempt SHALL link to the recovery decision and evidence record that authorized it. Normal scheduling MUST reject replacement when the prior attempt lacks a successful authorization record.

#### Scenario: Authorized replacement starts
- **WHEN** recovery records a valid retry authorization and the next attempt is launched
- **THEN** the new attempt references that recovery authorization while preserving the prior attempt

#### Scenario: Direct replacement is attempted
- **WHEN** an operator or scheduler attempts to prepare a replacement without valid authorization
- **THEN** dispatch preparation fails without appending a dispatch or attempt
