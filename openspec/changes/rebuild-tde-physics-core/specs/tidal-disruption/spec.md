## MODIFIED Requirements

### Requirement: Tidal force computation on any body
The system SHALL compute the tidal acceleration across any resolved body or matter-particle group near a black hole using the local gradient of the selected black-hole potential. Particles on different sides of the body SHALL receive the force at their own positions; a single visual deformation value SHALL NOT replace particle forces.

#### Scenario: Tidal force increases as distance decreases
- **WHEN** any resolved body moves closer to any black hole
- **THEN** the differential acceleration across its particles SHALL increase with the local tidal gradient

#### Scenario: Tidal force stretches body along radial direction
- **WHEN** a resolved star approaches a black hole
- **THEN** particles on the near side SHALL receive a different gravitational acceleration from particles on the far side and the body SHALL stretch along the radial direction

### Requirement: Body disruption detection
The system SHALL detect disruption from the evolving resolved matter state and mark the parent star as `disrupted = true` when self-binding can no longer contain the tidal deformation. After disruption, the existing constituent particles SHALL become free matter particles subject to gravity and hydrodynamics.

#### Scenario: Body approaches on eccentric orbit disrupts at periapsis
- **WHEN** a resolved star on an eccentric orbit passes within its configured tidal disruption condition
- **THEN** the star SHALL be marked disrupted near periapsis without a preset phase transition

#### Scenario: Disrupted body releases existing particles
- **WHEN** a star is marked disrupted
- **THEN** its existing particles SHALL continue as independent matter particles with no replacement by a hand-shaped stream

### Requirement: Resolved star particle count
Each star SHALL use a configured resolution within the supported particle budget. Particle masses SHALL sum to the configured stellar mass, and the initial distribution SHALL follow the selected stable stellar-density initializer rather than a fixed 50-500 visual-point formula.

#### Scenario: Solar-mass star has configured resolution
- **WHEN** a one-solar-mass TDE star is initialized
- **THEN** the number of particles SHALL equal the selected resolution setting and their total mass SHALL equal one solar mass within tolerance

#### Scenario: Resolution changes do not change total mass
- **WHEN** the same star is initialized at two supported resolutions
- **THEN** both runs SHALL preserve the same total stellar mass and SHALL expose the resolution in diagnostics

#### Scenario: Particles have resolved internal state
- **WHEN** a star is initialized
- **THEN** every constituent particle SHALL have position, velocity, mass, density, pressure, and internal energy

### Requirement: Star deformation before disruption
The system SHALL produce progressive deformation through the resolved tidal and hydrodynamic forces as the star approaches the disruption condition. Any deformation metric shown in the UI SHALL be measured from particle positions and SHALL not move particles itself.

#### Scenario: Star deforms before disruption
- **WHEN** a resolved star is at approximately 1.5 times its disruption radius
- **THEN** its particle cloud SHALL become measurably elongated along the radial direction before full disruption

#### Scenario: Star fully disrupts at the tidal condition
- **WHEN** the resolved binding condition is exceeded
- **THEN** the star SHALL transition to free particles whose subsequent stream is determined by integration

### Requirement: Fallback rate computation
The system SHALL measure fallback rate from the mass of bound debris returning through a configured pericenter or return surface per unit simulation time. A `t^(-5/3)` curve MAY be exposed as a comparison diagnostic but SHALL NOT drive particle positions, velocities, disk mass, or accretion.

#### Scenario: Fallback is measured from returning matter
- **WHEN** bound debris crosses the return surface
- **THEN** the reported fallback rate SHALL increase by the measured crossing mass divided by the elapsed simulation time

#### Scenario: Fallback has no fixed timer driver
- **WHEN** particle resolution or encounter parameters change
- **THEN** the fallback history SHALL be allowed to change rather than remaining locked to a fixed `T_fallback` constant

### Requirement: Tidal stream formation
After disruption, the system SHALL form the tidal stream from the integrated positions and velocities of existing matter particles. Particles with different orbital energies and angular momenta SHALL naturally produce bound and unbound branches, and no code SHALL place particles into a predefined arc or ring.

#### Scenario: Tidal stream evolves from particle dynamics
- **WHEN** a resolved star is disrupted
- **THEN** an elongated stream SHALL emerge from differential gravity and hydrodynamic forces in the particle state

#### Scenario: No stationary artificial cluster
- **WHEN** the simulation runs after disruption
- **THEN** particles near the black hole SHALL continue to move, accrete, escape, or circularize according to their state and SHALL NOT remain fixed because of initial visual placement
