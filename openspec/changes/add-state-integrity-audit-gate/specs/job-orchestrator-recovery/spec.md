## ADDED Requirements

### Requirement: State Integrity Audit Gate
The job orchestrator SHALL perform a state integrity audit before resuming an interrupted run, replacing a job session, recovering a dispatch, or scheduling new work after suspected interruption.

#### Scenario: Clean interrupted run resumes normally
- **WHEN** the root orchestrator resumes a run after suspected interruption and `jobctl audit` reports a replayable journal, matching snapshots, no unresolved dispatch contradiction, and one safe next action
- **THEN** the root orchestrator SHALL continue with the normal `jobctl next` control loop without creating a recovery investigation job

#### Scenario: Active run is idle but unresolved evidence exists
- **WHEN** a run is `active` with no active job, no active dispatch, an empty queue, and unresolved actions or worker evidence
- **THEN** the audit gate SHALL block normal dispatch and require recovery classification before any new work is scheduled

#### Scenario: Protocol hash mismatch blocks resume
- **WHEN** the protocol snapshot hash does not match the protocol manifest for the run
- **THEN** the audit gate SHALL block resume and classify the run as unsafe for automatic recovery

### Requirement: Recovery Finding Classification
The job orchestrator SHALL classify audit and recovery findings before performing any repair or retry decision.

#### Scenario: Derived snapshot drift is detected
- **WHEN** the event journal is replayable but derived snapshots such as queue, index, job, workflow, or step files disagree with replayed state
- **THEN** the finding SHALL be classified as `derived_snapshot_drift` or `stale_index_or_queue` and SHALL be eligible for deterministic rebuild

#### Scenario: Completed result was not applied
- **WHEN** a validated worker result, checkpoint, or progress artifact shows a dispatch completed but the corresponding action remains unresolved or the workflow node did not advance
- **THEN** the finding SHALL be classified as `completed_result_not_applied`

#### Scenario: External side effect is unknown
- **WHEN** a dispatch may have performed a side effect and local state cannot prove whether the side effect completed
- **THEN** the finding SHALL be classified as `external_effect_unknown` and SHALL require the dispatch recovery check before retry or acceptance

#### Scenario: Journal evidence is insufficient
- **WHEN** the journal and available worker or external evidence cannot establish one safe next action
- **THEN** the finding SHALL be classified as `journal_corrupt_or_insufficient`

### Requirement: Safe State Repair
The job orchestrator SHALL repair corrupted or stale state only through `jobctl.py` recovery operations that preserve authoritative evidence and avoid duplicate side effects.

#### Scenario: Stale index is rebuilt
- **WHEN** job records or journal events prove jobs exist but `jobs/index.json` is missing, stale, or empty
- **THEN** recovery SHALL rebuild the index from authoritative evidence without deleting job directories

#### Scenario: Completed result is reconciled
- **WHEN** a `completed_result_not_applied` finding has a worker result whose dispatch ID, nonce, session ID, protocol hash, contract revision, and artifact hashes validate
- **THEN** recovery SHALL persist the appropriate recovery events, mark the action resolved, advance the workflow according to control-plane rules, and recompute derived job and queue state

#### Scenario: Progress without validated result is treated as evidence only
- **WHEN** `progress.json` indicates completion but no matching validated worker result exists
- **THEN** recovery SHALL NOT mark the node completed solely from progress and SHALL request session status or classify the case for investigation

#### Scenario: Side effect retry is blocked until checked
- **WHEN** a dispatch has a side-effect class that may affect a repository or external service
- **THEN** recovery SHALL run or require the configured recovery check before retrying, accepting completion, or creating a replacement dispatch

### Requirement: Recovery Investigation Jobs
The job orchestrator SHALL create a recovery investigation job only when audit and recovery cannot prove one safe automatic next action.

#### Scenario: Automatic recovery is safe
- **WHEN** audit and dry-run recovery classify a finding and identify a deterministic repair
- **THEN** the system SHALL apply the repair through `jobctl recover` without creating a recovery investigation job

#### Scenario: Automatic recovery is unsafe
- **WHEN** evidence conflicts, external side-effect state is unknown, protocol identity is inconsistent, or no single safe next action can be established
- **THEN** the system SHALL either ask the user for authority or create a recovery investigation job

#### Scenario: Investigation job is constrained
- **WHEN** a recovery investigation job is created
- **THEN** its contract SHALL constrain it to run-state evidence, contradiction analysis, side-effect safety, and recommended next action, and SHALL NOT grant state mutation authority unless explicitly authorized
