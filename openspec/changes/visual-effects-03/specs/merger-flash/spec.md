## ADDED Requirements

### Requirement: Merger flash from BH proximity
A bright bloom flash SHALL appear when two black holes are within 5×Rs of each other. The flash intensity SHALL scale inversely with separation distance. This is driven by the `bhPairs` array from `PhysicsEngine.getState()` — no scenario-specific trigger.

#### Scenario: Flash when BHs are close
- **WHEN** two black holes are within 5×Rs of each other (from `bhPairs[].distance`)
- **THEN** a bright bloom SHALL appear at the midpoint

#### Scenario: Flash intensity scales with proximity
- **WHEN** BH separation decreases
- **THEN** the flash intensity SHALL increase

#### Scenario: Flash fades as BHs merge
- **WHEN** BHs merge (separation → 0)
- **THEN** the flash SHALL decay over 0.5 seconds

### Requirement: Flash is bloom, not geometry
The merger flash SHALL be implemented as a bloom intensity spike in the post-processing pipeline, not as additional geometry or particles. It reads BH pair distances from the `bhPairs` array in physics state.

#### Scenario: Flash uses bloom pipeline
- **WHEN** merger flash triggers
- **THEN** the bloom pass SHALL temporarily increase in intensity

### Requirement: bhPairs exposed in physics state
The physics engine SHALL expose a `bhPairs` array in `getState()` containing distances between all black hole pairs. Format: `[{ a: index, b: index, distance: float }]`. This is defined in DESIGN.md §7.3.

#### Scenario: bhPairs available to renderer
- **WHEN** `getState()` is called
- **THEN** `bhPairs` SHALL contain all black hole pair distances
