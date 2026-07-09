# gw-visualization

## Requirements

### Requirement: GW ripple shader
The lensing shader SHALL render gravitational wave ripples as concentric distortion rings emanating from the source. The distortion SHALL affect the ray direction during ray-marching, causing background stars to wobble.

#### Scenario: Ripples propagate from source
- **WHEN** the physics engine reports gwStrain > 0
- **THEN** concentric distortion rings SHALL propagate outward from the GW source position

#### Scenario: Ripples distort background
- **WHEN** GW ripples are active
- **THEN** background stars behind the ripples SHALL appear to wobble or shift position

### Requirement: GW ripple amplitude from physics
The ripple amplitude SHALL be proportional to gwStrain from the physics engine. The maximum visual distortion SHALL be subtle (not overwhelming the lensing effect). No scenario-specific trigger — appears whenever strain > 0.

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

### Requirement: WebGW ripple implementation
The GW ripple shader SHALL be implemented in the existing `LensingPass` for both WebGL 2.0 and WebGPU backends. The `LensingPass` already has both `_initGL()` and `_initWebGPU()` methods. GW uniforms (gwSourcePosition, gwFrequency, gwStrain, time) SHALL be added to both backends.

#### Scenario: Ripples work in WebGL 2.0
- **WHEN** the renderer backend is WebGL 2.0
- **THEN** GW ripples SHALL render correctly in the lensing shader

#### Scenario: Ripples work in WebGPU
- **WHEN** the renderer backend is WebGPU
- **THEN** GW ripples SHALL render correctly in the lensing shader