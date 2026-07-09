# gravitational-lensing

## Requirements

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

### Requirement: GW ripple shader
The lensing shader SHALL render gravitational wave ripples as concentric distortion rings emanating from the source. The distortion SHALL affect the ray direction during ray-marching, causing background stars to wobble.

#### Scenario: Ripples propagate from source
- **WHEN** the physics engine reports gwStrain > 0
- **THEN** concentric distortion rings SHALL propagate outward from the GW source position

#### Scenario: Ripples distort background
- **WHEN** GW ripples are active
- **THEN** background stars behind the ripples SHALL appear to wobble or shift position

### Requirement: GW ripple amplitude from physics
The ripple amplitude SHALL be proportional to gwStrain from the physics engine. The maximum visual distortion SHALL be subtle (not overwhelming the lensing effect).

#### Scenario: Amplitude scales with strain
- **WHEN** gwStrain increases (e.g., during binary inspiral)
- **THEN** the ripple distortion SHALL become more pronounced

#### Scenario: Ripples appear for any GW source
- **WHEN** any two masses accelerate (binary, TDE debris, etc.)
- **THEN** GW ripples SHALL appear if the physics engine reports nonzero strain

### Requirement: GW ripple frequency
The ripple frequency SHALL match gwFrequency from the physics engine. The ripples SHALL be visible as periodic distortions.

#### Scenario: Ripple frequency matches GW frequency
- **WHEN** the physics engine reports gwFrequency = f
- **THEN** the ripple pattern SHALL repeat at frequency f

### Requirement: GW ripple fade
After gwStrain drops to zero, existing ripples SHALL propagate outward and fade over ~1 second.

#### Scenario: Ripples fade after source stops
- **WHEN** gwStrain drops to zero
- **THEN** existing ripples SHALL propagate outward and fade

### Requirement: GW ripple toggle
GW ripples SHALL be toggleable via the display toggles UI.

#### Scenario: Toggle ripples off
- **WHEN** the user unchecks "GW Ripples"
- **THEN** no GW ripple distortion SHALL be applied

### Requirement: GW ripple implementation in LensingPass
The GW ripple shader SHALL be implemented in the existing `LensingPass` for both WebGL 2.0 and WebGPU backends. The `LensingPass` already has both `_initGL()` and `_initWebGPU()` methods. GW uniforms (gwSourcePosition, gwFrequency, gwStrain, time) SHALL be added to both backends.

#### Scenario: Ripples work in WebGL 2.0
- **WHEN** the renderer backend is WebGL 2.0
- **THEN** GW ripples SHALL render correctly in the lensing shader

#### Scenario: Ripples work in WebGPU
- **WHEN** the renderer backend is WebGPU
- **THEN** GW ripples SHALL render correctly in the lensing shader
