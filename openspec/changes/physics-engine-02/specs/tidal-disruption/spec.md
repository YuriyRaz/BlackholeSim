## MODIFIED Requirements

### Requirement: Tidal force computation on any body
The system SHALL compute tidal forces on any body near any black hole. The tidal acceleration across a body SHALL be: a_tidal = 2 × G × M_BH × R_body / d³, where d is the distance from the BH center to the body center.

#### Scenario: Tidal force increases as distance decreases
- **WHEN** any body moves closer to any black hole
- **THEN** the tidal force SHALL increase as 1/d³

#### Scenario: Tidal force stretches body along radial direction
- **WHEN** tidal forces are applied to a body's constituent particles
- **THEN** particles on the near side SHALL be pulled harder than particles on the far side

### Requirement: Body disruption detection
The system SHALL detect when a body is disrupted (tidal force exceeds self-gravity) and mark it as `disrupted = true`. After disruption, the body's particles SHALL be released as free bodies under gravitational influence.

#### Scenario: Body approaches on eccentric orbit disrupts at periapsis
- **WHEN** a body on an eccentric orbit passes within the tidal disruption radius at periapsis
- **THEN** the body SHALL be marked as disrupted at closest approach

#### Scenario: Disrupted body releases particles
- **WHEN** a body is marked as disrupted
- **THEN** its constituent particles SHALL become independent bodies subject to gravity from all objects

### Requirement: Star deformation before disruption
The system SHALL apply progressive deformation to a star as it approaches the tidal disruption radius, stretching it into a prolate spheroid. Deformation SHALL be proportional to (d_R / d)² where d is current distance and d_R is the disruption radius.

#### Scenario: Star deforms before disruption
- **WHEN** a star is at distance d = 1.5 × d_R (approaching disruption radius)
- **THEN** the star SHALL be visibly elongated along the radial direction (approximately 2:1 aspect ratio)

#### Scenario: Star fully disrupted at tidal radius
- **WHEN** a star crosses the tidal disruption radius (d < d_R)
- **THEN** the star SHALL fully disrupt into a tidal stream of particles

### Requirement: Fallback rate computation
The system SHALL compute the fallback rate of stellar debris after disruption: dM/dt ∝ (t / T_fallback)^(-5/3), where T_fallback is the orbital period of the most bound debris.

#### Scenario: Fallback rate follows power law
- **WHEN** a star is disrupted at time t_disrupt
- **THEN** the fallback rate SHALL increase from zero to a peak at T_fallback, then decrease as t^(-5/3)

### Requirement: Tidal stream formation
After disruption, the system SHALL arrange star particles into a tidal stream: particles from the near side of the star orbit faster (closer to BH), particles from the far side orbit slower, naturally forming an elongated stream.

#### Scenario: Tidal stream wraps around black hole
- **WHEN** a body is disrupted and particles evolve under gravity
- **THEN** the particles SHALL form an elongated stream that wraps around the black hole over time
