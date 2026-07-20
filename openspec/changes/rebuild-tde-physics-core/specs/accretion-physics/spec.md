## MODIFIED Requirements

### Requirement: ISCO as inner edge
The inner edge of the resolved disk SHALL be determined by the selected black-hole capture/ISCO model. Matter crossing the capture condition SHALL be removed only after its mass, momentum, and energy are recorded in the accretion ledger.

#### Scenario: Particles inside the capture condition plunge
- **WHEN** a matter particle crosses the configured ISCO or capture boundary
- **THEN** it SHALL be integrated toward capture and removed within the configured plunge timescale

#### Scenario: ISCO radius depends on the selected black-hole model
- **WHEN** the black-hole spin or potential model changes
- **THEN** the reported ISCO/capture radius SHALL be recomputed from that model rather than from a renderer constant

### Requirement: Temperature from orbital and hydrodynamic dynamics
Matter temperature and internal energy SHALL be derived from orbital compression, SPH pressure work, shock viscosity, and configured cooling. Orbital velocity MAY contribute to the initial thermal state but SHALL NOT be the sole temperature source.

#### Scenario: Shocked inner matter heats
- **WHEN** returning debris intersects with converging relative velocity
- **THEN** its internal energy and temperature SHALL increase according to the hydrodynamic dissipation model

#### Scenario: Cooling is explicit
- **WHEN** cooling is applied to hot matter
- **THEN** the thermal energy loss SHALL be reported and SHALL not alter particle mass or momentum without a corresponding force term

### Requirement: Accretion rate tracking
The system SHALL track accretion rate as measured captured particle mass per unit simulation time. The rate SHALL be exposed independently from fallback diagnostics and SHALL not be driven by a fixed analytic curve.

#### Scenario: Accretion rate tracks captured mass
- **WHEN** particles cross the capture condition
- **THEN** the reported accretion rate SHALL equal captured mass divided by the elapsed measurement interval within tolerance

#### Scenario: Accretion follows the simulated fallback
- **WHEN** encounter resolution or orbital parameters change
- **THEN** accretion history SHALL change according to the resulting particle trajectories rather than remaining locked to a fixed peak time

## REMOVED Requirements

### Requirement: Jet emission as part of accretion
**Reason**: Probability-based redirection at ISCO does not simulate magnetic fields or a physical jet-launching mechanism.
**Migration**: Keep jet launching disabled in this change. Add it only through a future MHD capability that supplies magnetic state and an energy/momentum budget.

### Requirement: Jet particle properties
**Reason**: Relativistic jet velocity and color are currently assigned to synthetic particles rather than derived from a magnetic/plasma state.
**Migration**: Preserve only generic renderer support for future jet data; do not emit these particles from the TDE core.

### Requirement: Jet particle lifecycle
**Reason**: A non-interacting synthetic particle stream is not a physical outflow.
**Migration**: Future MHD outflows must have their own mass, momentum, energy, and boundary accounting before a lifecycle requirement is restored.

### Requirement: Jet precession for tilted BH
**Reason**: The current wobble rule is not derived from magnetic fields or a relativistic disk state.
**Migration**: Defer precession to the future MHD/GR implementation.
