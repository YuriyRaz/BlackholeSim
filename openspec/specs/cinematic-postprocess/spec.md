# Cinematic Post-Processing

## Purpose

Provides cinematic visual effects including motion blur, chromatic aberration, lens flare, depth of field, color grading, and vignette to enhance the visual quality of the simulation.

## Requirements

### Requirement: Motion blur
The system SHALL apply motion blur to moving objects using a velocity buffer. The blur direction SHALL follow each pixel's screen-space velocity. Motion blur SHALL only be active on High quality.

#### Scenario: Moving objects blur
- **WHEN** particles or objects are moving fast
- **THEN** they SHALL exhibit directional motion blur in the direction of movement

#### Scenario: Motion blur disabled on Low/Medium
- **WHEN** quality is "Low" or "Medium"
- **THEN** motion blur SHALL NOT be applied

### Requirement: Chromatic aberration
The system SHALL apply subtle chromatic aberration (color channel offset) that increases toward screen edges. Maximum offset SHALL be 1-2 pixels at 1080p.

#### Scenario: Subtle color fringing at edges
- **WHEN** the post-process pipeline is active
- **THEN** high-contrast edges near screen boundaries SHALL show subtle color fringing

#### Scenario: No aberration at center
- **WHEN** a pixel is at screen center
- **THEN** no chromatic aberration SHALL be applied

### Requirement: Lens flare
The system SHALL render lens flare effects around very bright light sources (accretion disk inner edge, merger flash). Flare SHALL be a additive-blend sprite with hexagonal shape.

#### Scenario: Bright sources produce flare
- **WHEN** a pixel exceeds brightness threshold (3× HDR)
- **THEN** a lens flare sprite SHALL be rendered at that screen position

#### Scenario: Flare intensity scales with brightness
- **WHEN** a source is brighter
- **THEN** the flare SHALL be larger and more opaque

### Requirement: Depth of field (optional)
The system SHALL optionally apply depth of field blur, focusing on the currently selected object or camera target. Objects outside the focus range SHALL be blurred.

#### Scenario: DOF blurs background
- **WHEN** depth of field is enabled
- **THEN** objects far from the focus point SHALL appear blurred

#### Scenario: DOF is toggleable
- **WHEN** the user disables depth of field in settings
- **THEN** all objects SHALL render in sharp focus

### Requirement: Color grading
The system SHALL apply cinematic color grading with a blue-orange tone: shadows tinted blue, highlights tinted orange. The effect SHALL be subtle (not overwhelming).

#### Scenario: Cinematic color tone
- **WHEN** the post-process pipeline is active
- **THEN** dark areas SHALL have a slight blue tint and bright areas SHALL have a slight orange tint

### Requirement: Vignette
The system SHALL apply a subtle vignette effect (darkening at screen edges). The vignette SHALL be barely noticeable but add cinematic framing.

#### Scenario: Vignette darkens edges
- **WHEN** the post-process pipeline is active
- **THEN** the corners and edges of the screen SHALL be slightly darker than the center

### Requirement: Post-process effects are toggleable
Each post-processing effect SHALL be independently toggleable via the display toggles or settings panel.

#### Scenario: Disable motion blur
- **WHEN** the user unchecks "Motion Blur" in settings
- **THEN** motion blur SHALL not be applied while other effects remain active

#### Scenario: Disable all post-processing
- **WHEN** the user disables post-processing entirely (from Prop 1)
- **THEN** none of the cinematic effects SHALL be applied
