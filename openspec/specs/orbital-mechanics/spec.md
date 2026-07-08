# Orbital Mechanics

## Requirements

### Requirement: Keplerian orbit generation
The system SHALL generate elliptical orbits from orbital elements (semi-major axis a, eccentricity e, inclination i). Given a central mass and orbital elements, the system SHALL compute initial position and velocity vectors that produce the correct Keplerian orbit.

#### Scenario: Circular orbit from e=0
- **WHEN** eccentricity is 0 and semi-major axis is a
- **THEN** the orbit SHALL be circular with radius a and velocity v = √(GM/a)

#### Scenario: Elliptical orbit from 0<e<1
- **WHEN** eccentricity is 0.5 and semi-major axis is a
- **THEN** the orbit SHALL be elliptical with periapsis = a(1-e) and apoapsis = a(1+e)

#### Scenario: Orbital period matches Kepler's third law
- **WHEN** a body orbits a central mass M with semi-major axis a
- **THEN** the orbital period SHALL be T = 2π√(a³/GM)

### Requirement: Orbital element computation
The system SHALL compute orbital elements from position and velocity vectors: semi-major axis (from energy), eccentricity (from angular momentum), inclination (from angular momentum vector), argument of periapsis, longitude of ascending node, and true anomaly.

#### Scenario: Compute elements from state vectors
- **WHEN** position r and velocity v are known
- **THEN** the semi-major axis SHALL be computed as: a = -GM/(2ε) where ε = v²/2 - GM/r

#### Scenario: Circular orbit has e=0
- **WHEN** a body is in a circular orbit
- **THEN** the computed eccentricity SHALL be 0 (within floating-point tolerance)

### Requirement: Orbital decay from GW energy loss
The system SHALL compute orbital decay due to gravitational wave energy loss using the Peters formula: da/dt = -(64/5) × G³ × m1 × m2 × (m1 + m2) / (c⁵ × a³). This SHALL cause the orbit to shrink and the orbital period to decrease over time.

#### Scenario: Circular binary decays
- **WHEN** two bodies of mass m1 and m2 are in a circular orbit
- **THEN** the semi-major axis SHALL decrease over time at a rate matching the Peters formula

#### Scenario: Decay rate increases as orbit shrinks
- **WHEN** the semi-major axis decreases
- **THEN** the decay rate |da/dt| SHALL increase (faster decay at smaller separations)

#### Scenario: GW energy loss matches luminosity
- **WHEN** a binary system loses energy through GWs
- **THEN** the energy loss rate SHALL equal the GW luminosity: L_GW = (32/5) × G⁴ × m1² × m2² × (m1 + m2) / (c⁵ × a⁵)

### Requirement: Orbital path rendering
The system SHALL track the last 200 positions of each dynamic body and render them as a line trail. Trails SHALL be configurable (show/hide per object) and rendered with low opacity.

#### Scenario: Trail shows recent path
- **WHEN** a body is in orbit
- **THEN** a line trail SHALL show its path over the last 200 simulation steps

#### Scenario: Trail color matches object type
- **WHEN** a star has a trail
- **THEN** the trail SHALL be rendered in a color matching the star's visual (e.g., yellow-orange)

#### Scenario: Trail can be toggled
- **WHEN** the user unchecks "Orbital paths" in the UI
- **THEN** all trails SHALL be hidden

### Requirement: Orbit preview
The system SHALL display a semi-transparent orbit preview (the complete elliptical path) for selected objects, computed from current orbital elements.

#### Scenario: Selected object shows orbit preview
- **WHEN** an object is selected (clicked)
- **THEN** a semi-transparent ellipse showing its complete orbit SHALL be rendered

#### Scenario: Preview updates with orbital decay
- **WHEN** the orbit is decaying due to GW loss
- **THEN** the orbit preview SHALL update each frame to show the shrinking ellipse
