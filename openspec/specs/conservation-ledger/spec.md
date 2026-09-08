# conservation-ledger

## Purpose

Track and diagnose conservation of mass, momentum, angular momentum, and energy across the simulation.

## Requirements

### Requirement: Conservation diagnostics include momentum
Conservation diagnostics SHALL include both linear and angular momentum totals. `getDiagnostics()` SHALL return `momentum.linear` and `momentum.angular` in addition to existing mass accounting.

#### Scenario: Linear momentum reported
- **WHEN** `getDiagnostics()` is called
- **THEN** `momentum.linear` SHALL be a 3-vector representing the system's total linear momentum

#### Scenario: Angular momentum reported
- **WHEN** `getDiagnostics()` is called
- **THEN** `momentum.angular` SHALL be a 3-vector representing the system's total angular momentum

### Requirement: Escape accounting
The system SHALL invoke escape accounting when particles leave the simulation boundary. `recordEscape(mass)` SHALL be called with the escaped particle's mass when particles are marked as escaped.

#### Scenario: Escaped particle recorded
- **WHEN** a particle is marked as escaped
- **THEN** `recordEscape(mass)` SHALL be called with that particle's mass

### Requirement: Mass conservation
Total accounted mass SHALL remain approximately equal to initial total mass when no accretion events occur.

#### Scenario: Mass conserved without accretion
- **WHEN** the simulation runs with no accretion
- **THEN** `getDiagnostics().mass.accounted` SHALL approximately equal the initial total mass (within numerical tolerance)
