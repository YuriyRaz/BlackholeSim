## MODIFIED Requirements

### Requirement: Jet particles rendered from accretion
The renderer SHALL draw jet particles provided by the physics engine. Jet particles are emitted as part of the accretion process (see physics-engine-02/specs/accretion-physics). The renderer has no knowledge of jet emission logic — it just reads position, velocity, temperature from the physics engine's jetParticles[] array and draws them.

#### Scenario: Renderer reads jet particles
- **WHEN** the physics engine has jet particles (accretion onto spinning BH)
- **THEN** the renderer SHALL draw them as point sprites with additive blending

#### Scenario: No jet particles without accretion + spin
- **WHEN** the physics engine has no jet particles (no spin or no accretion)
- **THEN** no jet rendering SHALL occur

### Requirement: Jet additive blending
Jet particles SHALL be rendered with additive blending to create a luminous glow effect.

#### Scenario: Additive glow
- **WHEN** jet particles render
- **THEN** they SHALL use additive blending for a bright glow
