## ADDED Requirements

### Requirement: Gas particle orbital dynamics
Gas particles SHALL orbit black holes under gravitational influence. Each gas particle SHALL have: position, velocity, mass, temperature, and an accretion flag. Gas particles SHALL be passive tracers — they respond to black hole gravity but NOT to each other (no gas-gas self-gravity).

#### Scenario: Gas particles form disk through angular momentum
- **WHEN** gas particles with angular momentum orbit a black hole
- **THEN** they SHALL form a disk-like distribution in the equatorial plane

#### Scenario: Gas particles are passive tracers
- **WHEN** gas particles evolve
- **THEN** they SHALL respond to black hole gravity only, not to each other

### Requirement: Viscous angular momentum transport
The system SHALL implement a simple viscous torque that transports angular momentum outward. The viscous timescale SHALL be proportional to the orbital period × (r/H)² where H is the disk scale height. This causes inner particles to migrate inward and outer particles to spread outward.

#### Scenario: Angular momentum transport outward
- **WHEN** viscous forces are applied to gas particles
- **THEN** angular momentum SHALL be transported from inner to outer particles

#### Scenario: Viscous timescale increases with radius
- **WHEN** particles are at different radii
- **THEN** outer particles SHALL evolve more slowly than inner particles

### Requirement: Disk spreading
Over time, the accretion disk SHALL spread: the inner edge remains at ISCO (particles plunge), while the outer edge expands as angular momentum is transported outward. The total disk mass SHALL decrease as particles are accreted.

#### Scenario: Outer edge expands over time
- **WHEN** the disk evolves under viscous forces
- **THEN** the outer radius SHALL increase slowly while the inner radius stays at ISCO

#### Scenario: Disk mass decreases through accretion
- **WHEN** particles are accreted at ISCO
- **THEN** the total disk mass SHALL decrease over time

### Requirement: Gas particle emission
Gas particles SHALL be emitted through two mechanisms: (1) initial placement when a preset loads (pre-existing disk), and (2) capture of infalling matter (e.g., from disrupted star debris circularizing). Emission SHALL respect angular momentum conservation.

#### Scenario: Initial disk from preset
- **WHEN** a preset initializes with a disk
- **THEN** gas particles SHALL be placed on orbits between inner and outer radii with appropriate velocities

#### Scenario: Disrupted debris forms disk
- **WHEN** a star is disrupted and bound debris circularizes
- **THEN** those particles SHALL be added to the gas particle system
