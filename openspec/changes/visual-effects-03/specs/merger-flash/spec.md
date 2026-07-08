## ADDED Requirements

### Requirement: Merger flash from BH proximity
A bright bloom flash SHALL appear when two black holes are within 5×Rs of each other. The flash intensity SHALL scale inversely with separation distance. This is driven by BH positions from the physics engine — no scenario-specific trigger.

#### Scenario: Flash when BHs are close
- **WHEN** two black holes are within 5×Rs of each other
- **THEN** a bright bloom SHALL appear at the midpoint

#### Scenario: Flash intensity scales with proximity
- **WHEN** BH separation decreases
- **THEN** the flash intensity SHALL increase

#### Scenario: Flash fades as BHs merge
- **WHEN** BHs merge (separation → 0)
- **THEN** the flash SHALL decay over 0.5 seconds

### Requirement: Flash is bloom, not geometry
The merger flash SHALL be implemented as a bloom intensity spike in the post-processing pipeline, not as additional geometry or particles. It reads BH positions from the physics engine.

#### Scenario: Flash uses bloom pipeline
- **WHEN** merger flash triggers
- **THEN** the bloom pass SHALL temporarily increase in intensity
