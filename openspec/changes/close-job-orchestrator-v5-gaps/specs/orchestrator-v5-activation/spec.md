## ADDED Requirements

### Requirement: Trusted initialization is the default
An unqualified `jobctl init` SHALL select the closed v5 protocol revision. Legacy v4 creation MUST require an explicit protocol-version selection and SHALL identify the resulting run as `legacy_unattested`.

In the v6 implementation, legacy v4 and v5 runs are rejected by `reject_v5_or_earlier()` and classified with `"trust": "untrusted"`. The v5 trusted-initialization path no longer exists at runtime.

#### Scenario: Unqualified initialization
- **WHEN** an operator runs `jobctl init` without a protocol-version option in a supported trusted environment
- **THEN** the control plane creates a closed-revision v5 run

#### Scenario: Explicit legacy initialization
- **WHEN** an operator requests protocol version 4 explicitly
- **THEN** the control plane creates a v4 run and reports that its execution evidence is legacy and unattested

### Requirement: Trusted initialization fails closed on adapter capability
Before creating any v5 run directory or state file, the control plane SHALL verify that the configured production adapter supports authenticated launch receipts, authenticated response receipts, platform-native session correlation, exact prompt-digest reporting, and recovery status evidence. If any required capability is unavailable or unknown, initialization MUST fail without writing run state.

#### Scenario: Production Task adapter is capable
- **WHEN** the configured host Task adapter reports and proves every required capability
- **THEN** v5 initialization may create trusted run state bound to that adapter identity

#### Scenario: Adapter is missing or incomplete
- **WHEN** no adapter is configured or any required capability is false, unsupported, or unknown
- **THEN** v5 initialization fails with a capability-specific error and leaves no run directory

#### Scenario: Fake adapter is presented to normal CLI initialization
- **WHEN** normal production initialization is configured with the deterministic fake adapter
- **THEN** the control plane rejects the adapter outside the explicit test harness

### Requirement: Production Task receipts preserve native identity
The production Task adapter SHALL issue launch and response receipts from the component that observes the platform-issued Task session ID and exact delivered or returned bytes. The root MUST NOT be able to establish receipt authenticity by supplying its own shared secret or caller-authored native ID.

#### Scenario: Task launch succeeds
- **WHEN** the production adapter launches a worker through the host Task transport
- **THEN** its receipt binds the platform-issued native Task ID, run, job, dispatch, prompt digest, adapter identity, and proof

#### Scenario: Caller-controlled HMAC is supplied
- **WHEN** a caller supplies a receipt authenticated only by a secret the root can configure
- **THEN** the production adapter verifier rejects it as insufficient provenance

### Requirement: Verified receipts are retained for audit
The authoritative run SHALL retain the canonical verified launch and response receipts, or immutable retrievable receipt references, together with receipt digests, adapter identity, proof identity, and verification timestamps. Attempts, raw responses, outcomes, and artifacts MUST link to those retained receipt records.

#### Scenario: Launch receipt is accepted
- **WHEN** a launch receipt passes adapter verification and correlation checks
- **THEN** the control plane atomically stores its audit record before activating the attempt

#### Scenario: Response receipt is accepted
- **WHEN** a response receipt passes adapter verification and correlation checks
- **THEN** the raw response and accepted outcome retain a link to the stored response-receipt record

#### Scenario: Historical proof is unavailable
- **WHEN** audit cannot retrieve or revalidate retained receipt proof
- **THEN** audit reports receipt provenance as unknown and does not certify the run as trusted

### Requirement: Pre-closure v5 records remain unattested
The control plane SHALL identify v5 records created without retained authenticated receipts as `v5_preclosure_unattested`. It MUST NOT silently add empty proof fields or classify derived attempt data as authenticated receipt evidence.

In the v6 implementation, v5 runs are rejected entirely by `reject_v5_or_earlier()` and classified as `"trust": "untrusted"`. The `v5_preclosure_unattested` classification is superseded by this rejection.

#### Scenario: Existing v5 run lacks receipts
- **WHEN** the loader encounters a pre-closure v5 run without retained launch and response receipts
- **THEN** it permits read-only audit or export and blocks trusted mutation until fresh evidence or an explicit supported migration is provided

#### Scenario: Migration copies derived attempt fields
- **WHEN** a migration input contains session and digest fields but no adapter-issued receipt proof
- **THEN** the control plane refuses to promote the run to the closed trusted revision
