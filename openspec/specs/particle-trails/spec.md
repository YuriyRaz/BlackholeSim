# particle-trails

## Requirements

### Requirement: Particle trail rendering
The system SHALL render particle trails as fading line segments showing each particle's recent trajectory. The renderer SHALL read trail history from the physics engine's `particleTrails` buffer. Trail length SHALL be configurable (0-50 segments). The existing `TrailRenderer` SHALL be extended to handle both body trails and particle trails.

#### Scenario: Trail shows particle path
- **WHEN** a particle moves through space
- **THEN** a line trail SHALL show its last N positions, fading with age

#### Scenario: Trail can be disabled
- **WHEN** particle trails are disabled in the UI
- **THEN** no trail lines SHALL be rendered

### Requirement: Trail color matches particle
Each trail segment SHALL have the same color as its corresponding particle, with alpha fading along the trail. Color is derived from the particle's temperature property via the temperature-to-color mapping (blue-white → red).

#### Scenario: Trail fades with age
- **WHEN** a trail renders
- **THEN** older segments SHALL be more transparent than recent segments

#### Scenario: Trail color from temperature
- **WHEN** a trail segment renders
- **THEN** its color SHALL be derived from the particle's temperature at that point (or the particle's current temperature if per-segment temperature is not stored)

### Requirement: Particle trail history buffer
The physics engine SHALL maintain a `particleTrails` buffer: a map of particle IDs to arrays of the last N positions. Default trail length is 50 frames. This buffer is exposed in `getState()`.

#### Scenario: Physics stores trail history
- **WHEN** particles move each frame
- **THEN** the physics engine SHALL push the new position to each particle's trail buffer, trimming to max length

#### Scenario: Trail buffer exposed in state
- **WHEN** `getState()` is called
- **THEN** `particleTrails` SHALL contain position history for all active particles

### Requirement: WebGPU trail fallback
The particle trail renderer SHALL be available in WebGL 2.0 mode. WebGPU trail rendering is a follow-up task and is not required for MVP.

#### Scenario: Trails work in WebGL 2.0
- **WHEN** the renderer backend is WebGL 2.0
- **THEN** particle trails SHALL render correctly
