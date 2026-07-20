## ADDED Requirements

### Requirement: Persistent matter particle state
The system SHALL represent stellar matter and gas as persistent particles with position, velocity, mass, density, pressure, internal energy, temperature, phase, and lifecycle state. Particles SHALL remain in the physics state before, during, and after tidal disruption.

#### Scenario: Star exists as matter particles before disruption
- **WHEN** the TDE preset is loaded
- **THEN** the star's mass SHALL be distributed among persistent matter particles whose combined mass equals the configured stellar mass within tolerance

#### Scenario: Particle state survives disruption
- **WHEN** the star crosses the disruption condition
- **THEN** its existing particles SHALL continue with their current positions, velocities, and thermodynamic state without being replaced by a pre-shaped stream

### Requirement: SPH density and pressure
The system SHALL calculate each particle's density from neighboring particle masses and a compact smoothing kernel. Pressure SHALL be derived from density and internal energy using a documented equation of state.

#### Scenario: Density follows local concentration
- **WHEN** equal-mass particles are moved closer together
- **THEN** their estimated density SHALL increase and their pressure SHALL be recomputed from the updated state

#### Scenario: Sparse particles remain finite
- **WHEN** a particle has no neighbors within its smoothing support
- **THEN** its density, pressure, and acceleration SHALL remain finite using configured density and pressure floors

### Requirement: Hydrodynamic force integration
The system SHALL apply symmetric pressure forces and shock viscosity between neighboring matter particles. Hydrodynamic forces SHALL update velocity and internal energy through the same time integration step as gravity.

#### Scenario: Pressure resists compression
- **WHEN** a dense particle group is compressed
- **THEN** the resulting pressure acceleration SHALL oppose the compression and SHALL not be a renderer-only deformation

#### Scenario: Stream intersection produces shock heating
- **WHEN** bound debris streams intersect with converging relative velocity
- **THEN** artificial viscosity SHALL increase internal energy and temperature while reducing relative kinetic energy according to the configured dissipation model

### Requirement: Hydrodynamic transport conserves pair momentum
Pairwise hydrodynamic interactions SHALL apply equal and opposite momentum changes to interacting particles. Any configured cooling term SHALL be reported as an explicit energy sink rather than silently changing velocity.

#### Scenario: Pair force has zero net momentum
- **WHEN** one SPH pair is integrated without external gravity
- **THEN** the pair's total linear momentum SHALL remain constant within numerical tolerance

#### Scenario: Cooling is measurable
- **WHEN** cooling is enabled for hot gas
- **THEN** the removed thermal energy SHALL be included in the physics diagnostics and SHALL not be confused with accreted mass

### Requirement: Bounded neighbor search
The SPH solver SHALL use a spatial neighbor structure and SHALL cap the supported neighbor count or smoothing range so that runtime remains bounded for the configured particle budget.

#### Scenario: Neighbor lookup scales with local density
- **WHEN** the particle count increases within the supported budget
- **THEN** neighbor lookup SHALL avoid an unconditional all-pairs hydrodynamic comparison

#### Scenario: Solver reports overload
- **WHEN** the configured particle budget cannot meet the target step time
- **THEN** the engine SHALL expose a diagnostic or quality state instead of silently dropping matter interactions
