## ADDED Requirements

### Requirement: Scheduling inspection is read-only
`jobctl next` SHALL derive the next operation without writing prompts, dispatches, attempts, statuses, revisions, locks, or terminal run state. Repeated calls against unchanged state MUST return identical results and leave all authoritative and derived files byte-for-byte unchanged.

#### Scenario: Queued job is inspected repeatedly
- **WHEN** `next` is called multiple times while the same job remains eligible
- **THEN** every result identifies the same `prepare_dispatch` candidate and no run file changes

#### Scenario: Terminal run is inspected
- **WHEN** `next` reads a coherently persisted terminal run
- **THEN** it returns `run_complete` with the persisted disposition without mutating state

### Requirement: Dispatch preparation is an explicit locked mutation
Preparing an initial or replacement dispatch SHALL occur through an explicit mutation command that acquires the run lock, verifies the selected job and expected revision remain eligible, persists the exact prompt and immutable pending dispatch, and only then returns `start_job`.

#### Scenario: Eligible dispatch is prepared
- **WHEN** the operator prepares the job and expected revision returned by `next`
- **THEN** the control plane atomically records the dispatch and returns the exact persisted prompt and digest

#### Scenario: Scheduling state changed after inspection
- **WHEN** dispatch preparation receives a stale revision or the job is no longer eligible
- **THEN** it rejects the request without writing a prompt, dispatch, or status change

#### Scenario: Concurrent preparation occurs
- **WHEN** two controllers attempt to prepare the same dispatch concurrently
- **THEN** locking and revision checks permit exactly one authoritative dispatch

### Requirement: Terminal run disposition is persisted atomically
The mutation that causes all required jobs to become terminal SHALL also persist the derived terminal `run.json.status` and revision in the same recoverable commit sequence. `completed`, `failed`, and `canceled` dispositions MUST remain distinct.

#### Scenario: Final job completes successfully
- **WHEN** accepted evidence completes the final active required job
- **THEN** the job and `run.json.status: completed` are persisted before the mutation reports success

#### Scenario: Final job fails
- **WHEN** the final active required job becomes failed
- **THEN** the control plane persists `run.json.status: failed` and subsequent `next` returns `successful: false`

#### Scenario: Crash occurs between job and run writes
- **WHEN** the controller crashes during terminal persistence
- **THEN** audit and recovery identify and restore or complete the interrupted commit without reporting a coherent terminal run prematurely

### Requirement: Persisted and derived run status must agree
Loading, audit, and `next` SHALL verify that persisted terminal status agrees with job-derived status. A terminal mismatch MUST be reported as a coherence error and MUST NOT be normalized silently.

#### Scenario: Persisted run is active after terminal jobs
- **WHEN** all required jobs are terminal but `run.json.status` remains active
- **THEN** audit reports incomplete terminal persistence and provides the supported recovery action

#### Scenario: Persisted success hides failure
- **WHEN** `run.json.status` is completed but a required job is failed
- **THEN** loading or scheduling rejects the incoherent state

### Requirement: Audit validates the complete v5 trust chain
V5 audit SHALL validate protocol revision, adapter capability identity, retained receipt proof, dispatch-attempt-response linkage, append-only attempt history, artifact content digests, condition-result producer authority, recovery authorization, and persisted run disposition. Each unavailable fact MUST be reported as unknown rather than valid.

In the v6 implementation, `audit_v6.py` supersedes the v5 audit requirements. The v6 audit validates the same trust chain categories but uses the v6 schema, field names, and classification rules. The v5 audit path is retained only for legacy runs classified as `legacy_unattested` or `v5_preclosure_unattested`.

#### Scenario: Complete trust chain is valid
- **WHEN** all receipts, links, artifacts, authorities, recovery records, and run status validate
- **THEN** audit reports the run as trusted and coherent

#### Scenario: Receipt proof cannot be revalidated
- **WHEN** a retained receipt exists but its proof verifier is unavailable
- **THEN** audit reports unknown provenance and does not certify the run

#### Scenario: Artifact changed after acceptance
- **WHEN** an accepted artifact's current digest differs from its attested digest
- **THEN** audit reports the artifact and dependent completion evidence as invalid

### Requirement: Documentation and complete verification match the final protocol
Operator and worker documentation SHALL describe v5 defaults, explicit legacy initialization, adapter prerequisites, pure `next`, locked dispatch preparation, retained receipts, side-effect recovery evidence, and persisted terminal status using parser-valid commands. Archive verification MUST include the complete v4 and v5 suite with a recorded command, exit code, test count, and passing result.

#### Scenario: Documentation examples are checked
- **WHEN** documentation conformance tests run
- **THEN** every executable command parses against the final CLI and reflects the implemented mutation semantics

#### Scenario: Complete suite passes
- **WHEN** archive verification is performed with the documented extended timeout
- **THEN** all legacy, v5, instruction, schema, recovery, artifact, and end-to-end tests finish with exit code zero and the result is retained

#### Scenario: Focused tests pass but full suite times out
- **WHEN** selected v5 tests pass but the complete suite does not finish successfully
- **THEN** verification remains incomplete and the change is not archive-ready
