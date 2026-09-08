## ADDED Requirements

### Requirement: Canonical run-scoped artifact identity
Every orchestration artifact crossing the worker boundary SHALL have a canonical `run://<run-id>/jobs/<job-id>/<artifact>` reference and a resolved absolute read or write path. Generated prompts MUST NOT present an unqualified run-relative path as the worker's artifact destination.

#### Scenario: Worker receives report destination
- **WHEN** the control plane generates a worker prompt for a required report
- **THEN** the prompt includes both the canonical run-scoped report reference and the absolute authorized write path under that run root

#### Scenario: Same job ID appears in another run
- **WHEN** two runs both contain job `J001`
- **THEN** their canonical references and resolved paths identify different artifacts without namespace collision

### Requirement: Worker-bound artifact provenance
A completed response that claims a report or checkpoint SHALL include its canonical reference and SHA-256 digest. The control plane SHALL accept the artifact only when the reference resolves to the same run and producer job, the current bytes match the claimed digest, and the claim is bound to a verified response from that job's active attempt.

#### Scenario: Worker report matches authenticated claim
- **WHEN** a verified worker response claims the authoritative report reference and the file hash matches
- **THEN** the control plane records the report with producer job, attempt, response digest, content digest, and acceptance time

#### Scenario: Root creates a replacement report
- **WHEN** the report bytes do not match the digest in the verified worker response
- **THEN** the control plane rejects completion and does not accept the replacement report

### Requirement: Stale and cross-run artifact rejection
The control plane SHALL reject artifacts produced for another run, another job, an earlier unaccepted attempt, or a prior content digest. File existence, non-empty content, matching job ID text, and modification time alone MUST NOT establish freshness or ownership.

#### Scenario: Old report reused by a new worker
- **WHEN** the report path contains bytes from an earlier attempt or run and the current response does not attest to their digest
- **THEN** the artifact is rejected as stale or unproven

#### Scenario: Cross-run path supplied
- **WHEN** a worker outcome references a report whose canonical run ID differs from the active run
- **THEN** the outcome is rejected before state completion

### Requirement: Automatic dependency-report propagation
When a dependency reaches accepted completion with a required report, the control plane SHALL add that immutable report to every direct dependent job's generated context without requiring manual `related_reports` registration. Reports SHALL appear in deterministic dependency order with reference, resolved read path, producer job, and accepted content digest.

#### Scenario: Verification job starts after implementation
- **WHEN** an implementation dependency completes and its verification dependent becomes schedulable
- **THEN** the verification prompt includes the accepted implementation report automatically

#### Scenario: Multiple dependencies complete out of order
- **WHEN** a job has multiple dependencies that finish in a different order from their declaration
- **THEN** its prompt lists all accepted dependency reports in deterministic relationship order

### Requirement: Missing dependency report blocks dependent dispatch
If a dependency requires a report but has no accepted worker-bound report artifact, the dependency MUST NOT count as accepted completion and dependent jobs MUST NOT be dispatched with missing or substituted context.

#### Scenario: Dependency claims completion without report provenance
- **WHEN** the dependency response is otherwise valid but its required report cannot be authenticated
- **THEN** the dependency remains unaccepted and its dependents remain blocked

#### Scenario: Advisory report and ordinary dependency report coexist
- **WHEN** a continuation has advisory reports and ordinary dependency reports
- **THEN** the prompt labels and includes both relationship types without path collision or duplicate artifact identity
