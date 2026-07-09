# particle-renderer

## Requirements

### Requirement: Generic point-sprite rendering
The system SHALL render all particles (gas, jet, debris, tidal stream, test) as point sprites using a single generic particle shader. The renderer SHALL NOT use different shaders per particle type.

#### Scenario: Gas particles rendered as point sprites
- **WHEN** the physics engine provides gas particle positions, velocities, temperatures, and sizes
- **THEN** the renderer SHALL draw each particle as a colored point sprite at its position

#### Scenario: Jet particles rendered with additive blending
- **WHEN** the physics engine provides jet particle data
- **THEN** the renderer SHALL draw jet particles using additive blending to produce a bright glow effect

#### Scenario: Debris particles rendered normally
- **WHEN** the physics engine provides tidal disruption debris particles
- **THEN** the renderer SHALL draw them as standard point sprites (normal alpha blending)

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

### Requirement: Soft-circle particle fragment shader
The particle fragment shader SHALL render each point sprite as a soft circle with alpha falloff at the edges, producing a smooth, anti-aliased particle appearance.

#### Scenario: Soft alpha at particle edges
- **WHEN** a fragment is within the point sprite bounds but far from center
- **THEN** the alpha SHALL decrease smoothly from 1.0 at center to 0.0 at the edge using `1.0 - smoothstep(0.3, 0.5, dist)`

#### Scenario: Fragments outside point sprite discarded
- **WHEN** a fragment is outside the point sprite's circular bounds (dist > 0.5)
- **THEN** the fragment SHALL be discarded (not rendered)

### Requirement: Perspective point size
The rendered size of each particle SHALL be scaled inversely by distance from the camera, producing natural perspective foreshortening.

#### Scenario: Near particles appear larger
- **WHEN** a particle is close to the camera
- **THEN** its point size SHALL be large (size / small_distance)

#### Scenario: Far particles appear smaller
- **WHEN** a particle is far from the camera
- **THEN** its point size SHALL be small (size / large_distance)

### Requirement: Particle count budget per quality level
The system SHALL enforce a maximum particle count per quality level. Particles exceeding the budget SHALL be culled (not rendered). The budget SHALL be configurable per quality level.

#### Scenario: Low quality particle budget
- **WHEN** quality is "Low"
- **THEN** the maximum rendered particle count SHALL be 12,000

#### Scenario: Medium quality particle budget
- **WHEN** quality is "Medium"
- **THEN** the maximum rendered particle count SHALL be 20,000

#### Scenario: High quality particle budget
- **WHEN** quality is "High"
- **THEN** the maximum rendered particle count SHALL be 35,000

#### Scenario: Minimum quality particle budget
- **WHEN** quality is "Minimum"
- **THEN** the maximum rendered particle count SHALL be 6,000

### Requirement: Additive blending for jet/glow particles
The renderer SHALL support additive blending mode for particles that should glow (jet particles, bright disk particles). This is controlled by a per-particle or per-group flag.

#### Scenario: Jet particles use additive blend
- **WHEN** jet particles are rendered
- **THEN** they SHALL use additive blending for a bright glow effect

#### Scenario: No jet particles without accretion + spin
- **WHEN** the physics engine has no jet particles (no spin or no accretion)
- **THEN** no jet rendering SHALL occur

### Requirement: Particle data from physics engine
The renderer SHALL read particle positions, velocities, temperatures, and sizes from the physics engine's particle arrays each frame. The renderer SHALL NOT manage particle physics or lifecycle.

#### Scenario: Renderer reads from physics
- **WHEN** each frame begins
- **THEN** the renderer SHALL read particle state from the physics engine

#### Scenario: Renderer does not manage physics
- **WHEN** particles move
- **THEN** their movement SHALL be computed by the physics engine, not the renderer

### Requirement: Accretion disk particle rendering
The accretion disk SHALL be rendered as a collection of gas particles using the generic particle renderer. The disk shape SHALL emerge from the particle positions — no geometric ring mesh or dedicated disk shader SHALL be used.

#### Scenario: Disk shape emerges from particle distribution
- **WHEN** gas particles orbit a black hole
- **THEN** the visual disk-like distribution SHALL emerge from particle positions, not from a pre-defined mesh

#### Scenario: Disk color gradient from temperature
- **WHEN** gas particles orbit at different radii
- **THEN** inner particles (hotter) SHALL appear blue-white and outer particles (cooler) SHALL appear red, creating a visible temperature gradient across the disk

### Requirement: Disk light bending
The lensing shader SHALL bend light from disk particles, producing the characteristic wrap-around effect where the back of the disk appears above and below the black hole shadow.

#### Scenario: Back of disk visible above BH
- **WHEN** the camera views the disk at an oblique angle
- **THEN** particles on the far side of the disk SHALL appear to wrap over the top of the black hole shadow
