# Celestial Objects

## Requirements

### Requirement: Black hole entity
The system SHALL provide a BlackHole entity class with properties: mass (solar masses), spin parameter (0-1), position (vec3), Schwarzschild radius, event horizon radius, ergosphere radius, and fixed (boolean). The Schwarzschild radius SHALL be computed as Rs = 2.95 km × (M/M_sun).

#### Scenario: Create black hole with mass
- **WHEN** a BlackHole is created with mass = 10 M_sun
- **THEN** its Schwarzschild radius SHALL be approximately 29.5 km (normalized to simulation units)

#### Scenario: Fixed black hole doesn't move
- **WHEN** a black hole has fixed = true
- **THEN** its position SHALL NOT change during simulation regardless of gravitational forces

#### Scenario: Kerr black hole has ergosphere
- **WHEN** a black hole has spin = 0.998
- **THEN** its ergosphere radius SHALL be computed and the ergosphere SHALL be visually represented

### Requirement: Star entity
The system SHALL provide a Star entity class with properties: mass (solar masses), radius (solar radii), temperature (Kelvin), luminosity (watts), color (RGB), position (vec3), velocity (vec3), and disrupted (boolean). Stars SHALL have a visual representation: textured sphere with corona glow.

#### Scenario: Create Sol-like star
- **WHEN** a Star is created with mass = 1 M_sun, radius = 1 R_sun, temperature = 5778 K
- **THEN** its color SHALL be approximately yellow-white (G2V spectral type)

#### Scenario: Star has corona
- **WHEN** a Star is rendered
- **THEN** a corona glow effect SHALL be visible around the star (additive blend sprite)

#### Scenario: Star pulsates
- **WHEN** the simulation runs
- **THEN** the star's radius SHALL oscillate subtly (±0.5%) with a per-star random frequency

### Requirement: Neutron star entity
The system SHALL provide a NeutronStar entity class extending Star with additional properties: magneticField (Tesla), rotationRate (Hz), and pulsarBeams (boolean). Neutron stars SHALL render as tiny, dense, bright blue-white spheres with optional pulsing beams from magnetic poles.

#### Scenario: Create neutron star
- **WHEN** a NeutronStar is created with mass = 1.4 M_sun
- **THEN** it SHALL render as a small bright sphere (visually smaller than main sequence stars)

#### Scenario: Pulsar beams
- **WHEN** pulsarBeams = true and rotationRate > 0
- **THEN** two beam cones SHALL emanate from magnetic poles and rotate with the star

### Requirement: Accretion disk component
The system SHALL provide an AccretionDisk component that attaches to a BlackHole entity. It SHALL have properties: innerRadius (ISCO), outerRadius, mass, and temperature profile. The disk SHALL be rendered using the accretion disk shader from core-renderer-01.

#### Scenario: Disk attaches to black hole
- **WHEN** an AccretionDisk is created and attached to a BlackHole
- **THEN** the disk SHALL orbit the black hole at the correct Keplerian velocity

#### Scenario: Disk inner radius follows ISCO
- **WHEN** the black hole has spin = 0 (Schwarzschild)
- **THEN** the disk inner radius SHALL be 3×Rs (ISCO for non-spinning BH)

#### Scenario: Disk inner radius for spinning BH
- **WHEN** the black hole has spin = 0.998 (maximal Kerr)
- **THEN** the disk inner radius SHALL be approximately 1×Rs (ISCO for prograde orbit)

### Requirement: Object registration and lifecycle
The system SHALL maintain a registry of all celestial objects. Objects SHALL be added with `addObject()` and removed with `removeObject()`. The registry SHALL support querying objects by type (black hole, star, neutron star).

#### Scenario: Add object to scene
- **WHEN** `addObject(star)` is called
- **THEN** the star SHALL be included in the physics simulation and rendered in the scene

#### Scenario: Query objects by type
- **WHEN** `getObjectsByType('star')` is called
- **THEN** all objects with type 'star' SHALL be returned

### Requirement: Visual representation for each type
Each celestial object type SHALL have a distinct visual representation:
- Black hole: Black sphere with photon ring glow
- Star: Textured sphere + corona + pulsation
- Neutron star: Small bright sphere + magnetic beams

#### Scenario: Black hole renders with photon ring
- **WHEN** a BlackHole is rendered
- **THEN** a bright ring (photon sphere) SHALL be visible around the black shadow

#### Scenario: Star renders with corona
- **WHEN** a Star is rendered
- **THEN** a glowing corona SHALL surround the star sphere
