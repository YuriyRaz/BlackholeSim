## Purpose

The accretion disk is NOT a geometric mesh with a shader. It is a collection of gas particles managed by the physics engine (Proposal 2). The renderer draws these particles as point sprites.

## Requirements

### Requirement: Disk rendered as particles
The accretion disk SHALL be rendered as a collection of point-sprite particles, each with position, velocity, temperature, and size. The renderer SHALL NOT use a geometric ring mesh or dedicated disk shader.

#### Scenario: Gas particles form disk visually
- **WHEN** the physics engine provides gas particle positions and temperatures
- **THEN** the renderer SHALL draw them as colored point sprites forming a disk-like distribution

#### Scenario: Disk shape emerges from particle distribution
- **WHEN** gas particles orbit a black hole
- **THEN** the visual disk shape SHALL emerge from the particle positions, not from a pre-defined mesh

### Requirement: Particle color from temperature
Each gas particle's color SHALL be determined by its temperature: blue-white (>5×10⁶ K), white (1-5×10⁶ K), yellow-white (5×10⁵-10⁶ K), orange (1-5×10⁵ K), deep red (<10⁵ K).

#### Scenario: Hot inner particles are blue-white
- **WHEN** a gas particle has high temperature (inner disk)
- **THEN** its color SHALL be blue-white

#### Scenario: Cool outer particles are red
- **WHEN** a gas particle has low temperature (outer disk)
- **THEN** its color SHALL be deep red

### Requirement: Disk light bending
The lensing shader SHALL bend light from disk particles, producing the characteristic wrap-around effect where the back of the disk appears above and below the black hole shadow.

#### Scenario: Back of disk visible above BH
- **WHEN** the camera views the disk at an oblique angle
- **THEN** particles on the far side of the disk SHALL appear to wrap over the top of the black hole shadow
