# celestial-background

## Requirements

### Requirement: Nebula skybox
The system SHALL render a background using an equirectangular HDR texture (1K resolution) mapped to a sphere surrounding the scene. The texture SHALL be sampled based on the ray direction from the lensing shader.

#### Scenario: Nebula visible in background
- **WHEN** the lensing ray escapes all black holes without hitting anything
- **THEN** the pixel color SHALL be sampled from the nebula texture at the corresponding spherical coordinates

#### Scenario: Background rotates with camera
- **WHEN** the camera orbits the scene
- **THEN** the nebula background SHALL appear fixed at infinite distance (no parallax from camera orbit)

### Requirement: Procedural starfield
The system SHALL render a procedural starfield layered over the nebula skybox. Stars SHALL be generated deterministically from a hash of their direction vector, with configurable star count (1000-5000).

#### Scenario: Stars appear as bright points
- **WHEN** the procedural star shader evaluates a direction that contains a star
- **THEN** the pixel SHALL be significantly brighter than the nebula background (at least 10× brighter)

#### Scenario: Star positions are deterministic
- **WHEN** the same direction vector is evaluated twice
- **THEN** the star color and brightness SHALL be identical both times

#### Scenario: No stars in empty cells
- **WHEN** the procedural star shader evaluates a direction where no star exists
- **THEN** the contribution SHALL be zero (nebula shows through)

### Requirement: Star color temperature
Stars SHALL be colored based on a temperature hash: blue-white (hot, <30% of stars), white (medium, 40% of stars), orange (cool, >30% of stars).

#### Scenario: Hot star appears blue-white
- **WHEN** a star's temperature hash is below 0.3
- **THEN** the star color SHALL be approximately (0.7, 0.8, 1.0)

#### Scenario: Cool star appears orange
- **WHEN** a star's temperature hash is above 0.7
- **THEN** the star color SHALL be approximately (1.0, 0.8, 0.6)

### Requirement: Star twinkling
Stars SHALL exhibit subtle brightness variation over time using a sinusoidal function with per-star random phase, creating a twinkling effect.

#### Scenario: Star brightness oscillates
- **WHEN** simulation time advances
- **THEN** each star's brightness SHALL oscillate with amplitude ±30% of its base brightness at a rate of 0.5-2.0 Hz (per-star random frequency)

### Requirement: Parallax star layers
The starfield SHALL render at least 2 depth layers with different parallax rates, creating a sense of depth when the camera moves.

#### Scenario: Parallax depth effect
- **WHEN** the camera pans laterally
- **THEN** stars in the nearer layer SHALL appear to move faster than stars in the farther layer

### Requirement: Star count configurable
The star count SHALL be adjustable via the UI, with options for 1000, 2000, 3000, and 5000 stars.

#### Scenario: Reduce star count
- **WHEN** the user selects "1000 stars" from the UI
- **THEN** the procedural shader SHALL only render stars in 1/5 of the spatial cells, reducing visual density
