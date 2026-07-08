## ADDED Requirements

### Requirement: Schwarzschild gravitational lensing
The system SHALL render gravitational lensing by ray-marching through an approximated Schwarzschild metric. For each pixel, the shader SHALL cast a ray from the camera and deflect it toward each black hole center using the post-Newtonian approximation α = Rs/r, where Rs is the Schwarzschild radius and r is the distance to the black hole.

#### Scenario: Background stars bend around black hole
- **WHEN** a background star is positioned such that its light passes near a black hole
- **THEN** the star's image SHALL appear displaced from its true position, with displacement increasing as the impact parameter decreases

#### Scenario: Einstein ring forms
- **WHEN** the camera, black hole, and a distant light source are approximately aligned
- **THEN** the light source SHALL appear as a ring around the black hole (Einstein ring)

#### Scenario: Event horizon produces black pixels
- **WHEN** a ray enters the event horizon radius of a black hole during ray-marching
- **THEN** the pixel SHALL render as black (RGB 0,0,0) with no further ray-marching

#### Scenario: Photon sphere produces bright ring
- **WHEN** a ray passes near 1.5× the Schwarzschild radius (photon sphere)
- **THEN** the ray SHALL be deflected significantly, producing a bright ring-like feature around the shadow

### Requirement: Multiple black hole support
The system SHALL support gravitational lensing from up to 4 black holes simultaneously. The deflection from each black hole SHALL be applied additively at each ray-march step.

#### Scenario: Two black holes lens simultaneously
- **WHEN** two black holes are present in the scene
- **THEN** the lensing shader SHALL apply deflection from both black holes at each step, creating overlapping lensing distortions

#### Scenario: Black hole count uniform
- **WHEN** the shader receives `blackHoleCount = 2`
- **THEN** the shader SHALL only iterate over the first 2 entries in the black hole data array

### Requirement: Ray-march step count
The system SHALL support configurable ray-march steps (15-40) controlled by the quality level. Fewer steps reduce visual quality but improve performance.

#### Scenario: 30 steps at default quality
- **WHEN** quality level is set to "Medium"
- **THEN** the lensing shader SHALL perform 30 ray-march steps per pixel

#### Scenario: 15 steps at low quality
- **WHEN** quality level is set to "Low"
- **THEN** the lensing shader SHALL perform 15 ray-march steps per pixel

### Requirement: Early ray termination
The system SHALL terminate ray-marching early when the ray is far from all black holes and moving away from the scene center, to avoid wasting computation on rays that will clearly escape.

#### Scenario: Ray escapes scene bounds
- **WHEN** a ray's distance from all black holes exceeds 50× the largest black hole mass AND the ray is moving away from the camera origin
- **THEN** the ray-march loop SHALL terminate and the background shall be sampled at the current ray direction

### Requirement: Half-resolution lensing
The system SHALL support rendering the lensing pass at half the canvas resolution (540p at 1080p display) with bilateral upsampling to full resolution. This SHALL be togglable via the quality selector.

#### Scenario: Half-resolution mode active
- **WHEN** quality level is "Low" or "Medium"
- **THEN** the lensing pass SHALL render to a framebuffer at 50% of canvas width and height, then upsample to full resolution

#### Scenario: Full-resolution mode active
- **WHEN** quality level is "High"
- **THEN** the lensing pass SHALL render at full canvas resolution

### Requirement: Kerr black hole frame dragging
The system SHALL apply Lense-Thirring frame dragging deflection for black holes with non-zero spin parameter. The additional tangential deflection SHALL be proportional to spin × Rs / r².

#### Scenario: Spinning black hole drags light
- **WHEN** a black hole has spin parameter a > 0
- **THEN** the lensing shader SHALL apply an additional tangential deflection to rays passing near the black hole, causing asymmetric lensing

#### Scenario: Non-spinning black hole
- **WHEN** a black hole has spin parameter a = 0
- **THEN** the lensing shader SHALL apply only the standard radial deflection (Schwarzschild lensing)
