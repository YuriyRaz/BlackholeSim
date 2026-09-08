# orchestrator-evidence-gates

## Purpose

Enforce structured, independently verifiable completion conditions with explicit evidence requirements, ensuring jobs cannot claim completion without satisfying all required conditions and that terminal run status is truthful.

## Requirements

### Requirement: Structured completion conditions
Every completion condition SHALL have a stable condition ID, description, required flag, evidence requirement, and verification mode. Registration MUST reject duplicate IDs, unresolved verifier references, and verifier dependency cycles.

#### Scenario: Valid independent condition
- **WHEN** a required condition names an existing verifier job that can schedule from the target's claim
- **THEN** registration preserves the condition identity and verifier relationship

#### Scenario: Duplicate condition IDs
- **WHEN** a job definition repeats a condition ID
- **THEN** registration rejects the definition before state mutation

### Requirement: Enumerated condition results
Worker and verifier responses SHALL report each assigned condition as `passed`, `failed`, `not_run`, `unavailable`, or `unknown`. Only `passed` SHALL satisfy a required condition, and a required evidence-bearing condition MUST include one or more accepted artifact references.

#### Scenario: Required browser verification not run
- **WHEN** a worker or verifier reports `not_run` for required browser verification
- **THEN** the condition remains unsatisfied and the target job cannot become completed

#### Scenario: Passed condition lacks required evidence
- **WHEN** a required evidence-bearing condition is marked `passed` without accepted evidence artifacts
- **THEN** the control plane rejects the result as incoherent

### Requirement: Completion claim precedes acceptance
A verified worker response requesting completion SHALL create a `completion_claimed` state before accepted completion. The control plane SHALL transition to `completed` only after every required condition is satisfied by an authorized worker or verifier result and all report and evidence provenance checks pass.

#### Scenario: All self-verified conditions pass
- **WHEN** a completion claim contains authorized `passed` results and accepted evidence for every required self-verified condition
- **THEN** the control plane accepts the claim and transitions the job to `completed`

#### Scenario: Claim omits required benchmark result
- **WHEN** a completion claim omits a required performance condition
- **THEN** the job remains uncompleted and the missing condition is reported explicitly

### Requirement: Independent verifier gate
Conditions configured for independent verification SHALL be satisfiable only by verified responses from their designated verifier jobs. A verifier SHALL be schedulable from the target's `completion_claimed` state with the target's accepted report and evidence as context, without requiring the target's final `completed` state.

#### Scenario: Verifier passes required conditions
- **WHEN** the designated verifier returns authenticated `passed` results with required evidence for all assigned conditions
- **THEN** those results are attached to the target claim and may allow target completion

#### Scenario: Implementation worker self-approves independent condition
- **WHEN** the implementation worker marks an independently verified condition as `passed`
- **THEN** the result is retained as a claim at most and does not satisfy the condition

### Requirement: Verification failure and evidence unavailability are explicit
A required verifier result of `failed` SHALL move the target to `repair_required`. A required result of `not_run`, `unavailable`, or `unknown` SHALL move or retain the target in `blocked` or `needs_input` according to configured policy. None of these states SHALL be normalized to completion.

#### Scenario: Verifier finds defects
- **WHEN** an independent verifier returns `failed` for a required condition
- **THEN** the target enters `repair_required` with the verifier report and evidence attached

#### Scenario: Browser capability unavailable
- **WHEN** the verifier reports `unavailable` for required browser evidence
- **THEN** the target is blocked or requests input and does not become completed

### Requirement: Truthful terminal run operation
When all required jobs are terminal, `next` SHALL return `run_complete` with the explicit derived `run_status` and a `successful` boolean. `successful` SHALL be true only when the run status is `completed`; failed and canceled runs are terminal but unsuccessful.

#### Scenario: Successful terminal run
- **WHEN** every required job has accepted completion
- **THEN** `next` returns `run_complete` with `run_status: completed` and `successful: true`

#### Scenario: Terminal failed run
- **WHEN** one or more required jobs failed and no jobs remain active
- **THEN** `next` returns `run_complete` with `run_status: failed` and `successful: false`
