## MODIFIED Requirements

### Requirement: Jet particles rendered from physically produced state
The renderer SHALL draw jet particles only when the physics engine provides particles from an implemented jet-launching model. The renderer SHALL not create, redirect, classify, or reshape matter into a jet, and the TDE hydrodynamic core SHALL provide no synthetic jet particles.

#### Scenario: No MHD state means no jet
- **WHEN** the physics engine has accretion but no magnetic-field jet model
- **THEN** no jet particles SHALL be emitted or rendered

#### Scenario: Future MHD state is renderer-compatible
- **WHEN** a future MHD subsystem provides jet particle state with position, velocity, temperature, and lifecycle data
- **THEN** the generic renderer SHALL draw that supplied state without knowing the jet-launching equations
