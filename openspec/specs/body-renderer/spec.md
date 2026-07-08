# body-renderer

## Requirements

### Requirement: Body type dispatch
The system SHALL render each celestial body differently based on its `type` property: 'blackhole', 'star', or 'neutronstar'. The renderer SHALL read `body.type` from physics state and dispatch to the appropriate rendering path.

#### Scenario: Black hole rendered as silhouette
- **WHEN** a body has `type: 'blackhole'`
- **THEN** the renderer SHALL render it as a black disk at the event horizon radius with a photon sphere glow ring

#### Scenario: Star rendered as colored sphere
- **WHEN** a body has `type: 'star'`
- **THEN** the renderer SHALL render it as a colored sphere with radius from `body.radius` and color from `body.temperature`

#### Scenario: Neutron star rendered with pulsar beams
- **WHEN** a body has `type: 'neutronstar'`
- **THEN** the renderer SHALL render it as a small bright sphere with bipolar pulsar beam cones along the spin axis

### Requirement: Star sphere rendering
Stars SHALL be rendered as solid-colored spheres. The sphere color SHALL be derived from the star's temperature property using a blackbody-inspired color mapping.

#### Scenario: Star radius from physics state
- **WHEN** the physics engine provides a star body with `radius` property
- **THEN** the renderer SHALL draw the star as a sphere with that radius in simulation units

#### Scenario: Star color from temperature
- **WHEN** a star has `temperature` property
- **THEN** its color SHALL be mapped from temperature: blue-white (>10,000 K), white (6,000-10,000 K), yellow (5,000-6,000 K), orange (3,500-5,000 K), red (<3,500 K)

#### Scenario: Star corona glow
- **WHEN** a star is rendered
- **THEN** the renderer SHALL apply a subtle radial glow effect (corona) extending beyond the sphere surface

### Requirement: Black hole silhouette rendering
Black holes SHALL be rendered as solid black disks at the event horizon radius. A bright photon sphere glow ring SHALL appear at 1.5× the Schwarzschild radius.

#### Scenario: Event horizon black disk
- **WHEN** a black hole body is rendered
- **THEN** the renderer SHALL draw a black disk (RGB 0,0,0) at the event horizon radius in screen space

#### Scenario: Photon sphere glow ring
- **WHEN** a black hole body is rendered
- **THEN** the renderer SHALL draw a bright ring at 1.5× the Schwarzschild radius, with intensity inversely proportional to distance from the ring center

#### Scenario: Black hole shadow scales with mass
- **WHEN** a black hole has larger mass (larger Schwarzschild radius)
- **THEN** the black disk and photon sphere ring SHALL scale proportionally

### Requirement: Neutron star pulsar beam rendering
Neutron stars SHALL be rendered as small bright spheres with bipolar beam cones along their spin axis. The beams SHALL rotate with the neutron star's spin.

#### Scenario: Neutron star sphere
- **WHEN** a body has `type: 'neutronstar'`
- **THEN** the renderer SHALL draw it as a small, bright (blue-white) sphere

#### Scenario: Pulsar beam cones
- **WHEN** a neutron star has a spin axis defined
- **THEN** the renderer SHALL draw two cone-shaped beams extending from the poles along the spin axis

#### Scenario: Beam rotation with spin
- **WHEN** the neutron star spins
- **THEN** the pulsar beams SHALL rotate synchronously, creating the lighthouse effect when viewed at an angle

### Requirement: Body rendering respects quality level
The body renderer SHALL respect the current quality level. At minimum quality, body rendering SHALL be simplified (no corona glow, no pulsar beam cones, reduced sphere tessellation).

#### Scenario: Full body rendering at high quality
- **WHEN** quality is "High" or "Medium"
- **THEN** body rendering SHALL include all effects (corona, pulsar beams, full tessellation)

#### Scenario: Simplified body rendering at minimum quality
- **WHEN** quality is "Minimum"
- **THEN** body rendering SHALL skip corona glow, skip pulsar beams, and use reduced sphere tessellation
