## MODIFIED Requirements

### Requirement: Particle rendering
The system SHALL render particles as point sprites with per-particle position, size, color, and alpha. A soft-circle texture SHALL be applied to create glowing appearance. The renderer reads particle data from the physics engine — it has no knowledge of particle type.

#### Scenario: Particles render as soft circles
- **WHEN** particles are active in the scene
- **THEN** each particle SHALL render as a soft, glowing circle

#### Scenario: Particle size attenuates with distance
- **WHEN** a particle is far from the camera
- **THEN** its screen-space size SHALL decrease proportionally to distance

### Requirement: Particle color from temperature
Each particle's color SHALL be derived from its temperature property: blue-white (>5×10⁶ K), white (1-5×10⁶ K), yellow-white (5×10⁵-10⁶ K), orange (1-5×10⁵ K), deep red (<10⁵ K). The temperature-to-color mapping SHALL be implemented in the fragment shader (not in JS) for performance with 35K particles.

#### Scenario: Hot particles are blue-white
- **WHEN** a particle has high temperature (>5×10⁶ K)
- **THEN** its color SHALL be blue-white

#### Scenario: Cool particles are red
- **WHEN** a particle has low temperature (<10⁵ K)
- **THEN** its color SHALL be deep red

#### Scenario: Color mapping in shader
- **WHEN** particles are rendered
- **THEN** the fragment shader SHALL map the `temperature` attribute to a color using a smooth gradient or stepped color bands

### Requirement: Additive blending for jet/glow particles
The renderer SHALL support additive blending mode for particles that should glow (jet particles, bright disk particles). This is controlled by a per-particle or per-group flag.

#### Scenario: Jet particles use additive blend
- **WHEN** jet particles are rendered
- **THEN** they SHALL use additive blending for a bright glow effect

### Requirement: Particle count adapts to quality
The maximum active particle count SHALL be controlled by the quality level: Low=12K, Medium=20K, High=35K.

#### Scenario: Low quality limits particles
- **WHEN** quality is "Low"
- **THEN** maximum active particles SHALL be 12,000

#### Scenario: High quality allows more particles
- **WHEN** quality is "High"
- **THEN** maximum active particles SHALL be 35,000

### Requirement: Particle data from physics engine
The renderer SHALL read particle positions, velocities, temperatures, and sizes from the physics engine's particle arrays each frame. The renderer SHALL NOT manage particle physics or lifecycle.

#### Scenario: Renderer reads from physics
- **WHEN** each frame begins
- **THEN** the renderer SHALL read particle state from the physics engine

#### Scenario: Renderer does not manage physics
- **WHEN** particles move
- **THEN** their movement SHALL be computed by the physics engine, not the renderer
