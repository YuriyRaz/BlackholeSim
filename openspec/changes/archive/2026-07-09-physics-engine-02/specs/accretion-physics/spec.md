## ADDED Requirements

### Requirement: ISCO as inner edge
The inner edge of the gas particle distribution SHALL be at the Innermost Stable Circular Orbit (ISCO). Gas particles that migrate inside ISCO SHALL plunge into the black hole and be removed from the simulation.

#### Scenario: Particles inside ISCO plunge
- **WHEN** a gas particle's orbital radius drops below ISCO
- **THEN** it SHALL spiral inward rapidly and be removed within a few orbital periods

#### Scenario: ISCO radius depends on BH spin
- **WHEN** the black hole has spin parameter a*
- **THEN** the ISCO radius SHALL be: r_isco = 6×Rs for a*=0 (Schwarzschild), decreasing to 1×Rs for a*=1 (maximal Kerr)

### Requirement: Temperature from orbital dynamics
Gas particle temperature SHALL be derived from the local orbital velocity and viscous dissipation: T(r) ∝ v_orbital² × (1 + α_visc × dissipation_factor), where α_visc is the Shakura-Sunyaev viscosity parameter. Inner particles (faster orbits) SHALL be hotter than outer particles.

#### Scenario: Inner disk is hottest
- **WHEN** temperature is computed for particles at different radii
- **THEN** inner particles SHALL have higher temperature than outer particles

#### Scenario: Temperature follows orbital velocity
- **WHEN** a particle's orbital velocity increases (e.g., during inspiral)
- **THEN** its temperature SHALL increase proportionally

### Requirement: Accretion rate tracking
The system SHALL track the accretion rate (dM/dt) as the mass of particles accreted per unit time. This value SHALL be exposed as a readable property on the PhysicsEngine.

#### Scenario: Accretion rate tracks particle accretion
- **WHEN** particles are accreted at ISCO
- **THEN** the accretion rate SHALL be computed as mass_accreted / dt

#### Scenario: Accretion rate peaks during TDE
- **WHEN** a tidal disruption delivers a large mass to the disk
- **THEN** the accretion rate SHALL peak at T_fallback and decay as t^(-5/3)

### Requirement: Jet emission as part of accretion
When a gas particle reaches ISCO around a spinning black hole (a* > 0), a fraction of particles SHALL be redirected along the BH spin axis instead of plunging. The fraction SHALL be proportional to a*² (Blandford-Znajek proportionality). This is NOT a separate system — it is what accretion does for spinning BHs.

#### Scenario: Accretion produces jet for spinning BH
- **WHEN** gas particles reach ISCO around a spinning BH (a* > 0)
- **THEN** a fraction (proportional to a*²) SHALL be redirected along the spin axis as jet particles

#### Scenario: Accretion does not produce jet for Schwarzschild BH
- **WHEN** the black hole has a* = 0
- **THEN** all particles at ISCO SHALL plunge (no jet emission)

#### Scenario: Jet intensity follows accretion × spin
- **WHEN** accretion rate increases or BH spin increases
- **THEN** jet particle count and velocity SHALL increase proportionally

### Requirement: Jet particle properties
Jet particles SHALL travel outward along the BH spin axis at relativistic speeds (0.9-0.99c scaled). Core particles (on-axis) SHALL be blue-white; edge particles (off-axis) SHALL be redder.

#### Scenario: Jet particles move relativistically
- **WHEN** jet particles are emitted
- **THEN** they SHALL travel outward along the spin axis at 0.9-0.99c (simulation-scaled)

#### Scenario: Jet color gradient
- **WHEN** jet particles render
- **THEN** on-axis particles SHALL be blue-white and off-axis particles SHALL be redder

### Requirement: Jet particle lifecycle
Jet particles SHALL be removed from the simulation when they travel beyond 200× the Schwarzschild radius from the emitting black hole along the spin axis. The maximum simultaneous jet particle count SHALL be 2,000. When the limit is reached, the oldest jet particles SHALL be removed first (FIFO). Jet particles SHALL NOT interact with other particles (no collisions, no gravitational influence on other bodies).

#### Scenario: Jet particles removed at distance limit
- **WHEN** a jet particle travels beyond 200×Rs from the emitting black hole
- **THEN** it SHALL be removed from the simulation

#### Scenario: Jet particle count cap
- **WHEN** jet particle count reaches 2,000
- **THEN** new jet particles SHALL displace the oldest jet particles

#### Scenario: Jet particles are non-interacting
- **WHEN** a jet particle is in the simulation
- **THEN** it SHALL NOT exert gravitational force on other particles and SHALL NOT collide with gas or debris particles

### Requirement: Jet precession for tilted BH
For black holes with spin axis tilted relative to the orbital plane, the jet emission direction SHALL precess (wobble) around the average spin axis, driven by frame dragging.

#### Scenario: Precessing jet
- **WHEN** BH spin axis is tilted relative to orbital plane
- **THEN** jet emission direction SHALL wobble around the average axis

#### Scenario: Steady jet for aligned BH
- **WHEN** BH spin axis is aligned with orbital plane normal
- **THEN** jet SHALL point steadily along spin axis without precession
