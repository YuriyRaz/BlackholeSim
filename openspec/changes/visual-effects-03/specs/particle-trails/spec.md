## ADDED Requirements

### Requirement: Particle trail rendering
The system SHALL render particle trails as fading line segments showing each particle's recent trajectory. The renderer SHALL read trail history from the physics engine. Trail length SHALL be configurable (0-50 segments).

#### Scenario: Trail shows particle path
- **WHEN** a particle moves through space
- **THEN** a line trail SHALL show its last N positions, fading with age

#### Scenario: Trail can be disabled
- **WHEN** particle trails are disabled in the UI
- **THEN** no trail lines SHALL be rendered

### Requirement: Trail color matches particle
Each trail segment SHALL have the same color as its corresponding particle, with alpha fading along the trail.

#### Scenario: Trail fades with age
- **WHEN** a trail renders
- **THEN** older segments SHALL be more transparent than recent segments
