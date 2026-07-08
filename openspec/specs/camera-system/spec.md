# camera-system

## Requirements

### Requirement: Free orbit camera
The system SHALL provide a free-orbit camera controlled by mouse drag. Left-click drag SHALL orbit around the focus point. Right-click drag (or Shift+Left) SHALL pan the focus point. Scroll wheel SHALL zoom in/out.

#### Scenario: Left drag orbits camera
- **WHEN** the user left-clicks and drags horizontally
- **THEN** the camera SHALL orbit around the focus point, changing its azimuthal angle

#### Scenario: Right drag pans camera
- **WHEN** the user right-clicks and drags
- **THEN** the camera's focus point SHALL move in the screen plane

#### Scenario: Scroll zooms camera
- **WHEN** the user scrolls the mouse wheel down
- **THEN** the camera SHALL move farther from the focus point (zoom out)

### Requirement: Smooth camera damping
All camera movements SHALL use critically-damped interpolation. The camera position and orientation SHALL smoothly follow input with a damping factor that produces buttery-smooth motion without overshooting.

#### Scenario: Damped orbit response
- **WHEN** the user drags and releases the mouse
- **THEN** the camera SHALL continue moving briefly after release, decelerating smoothly to a stop within 200-400ms

#### Scenario: No jarring camera movements
- **WHEN** any camera control input is applied
- **THEN** the camera position SHALL never jump instantaneously; all changes SHALL be interpolated

### Requirement: Camera constraints
The camera SHALL be constrained to prevent gimbal lock (elevation between -85° and +85°) and to keep the camera above the event horizon (minimum distance = 2× Schwarzschild radius of the nearest black hole).

#### Scenario: Cannot orbit past poles
- **WHEN** the user drags the camera elevation toward 90°
- **THEN** the camera SHALL stop at 85° elevation and NOT flip over

#### Scenario: Cannot enter event horizon
- **WHEN** the user zooms in toward a black hole
- **THEN** the camera SHALL stop at 2× the Schwarzschild radius and NOT pass through the event horizon

### Requirement: Cinematic auto-orbit mode
The system SHALL provide a cinematic camera mode that automatically orbits the focus point at a configurable speed (0.1-1.0 rotations per minute). The user SHALL be able to toggle between free and cinematic modes.

#### Scenario: Enable cinematic mode
- **WHEN** the user presses 'C' or clicks the Cinematic button
- **THEN** the camera SHALL begin automatically orbiting the focus point at the configured speed

#### Scenario: User input overrides cinematic
- **WHEN** the user provides mouse input while in cinematic mode
- **THEN** the cinematic orbit SHALL pause and the camera SHALL respond to user input, then resume cinematic orbit after 3 seconds of inactivity

### Requirement: Camera presets
The system SHALL provide 5 camera presets: Cinematic (30° elevation, auto-orbit), Top-down (85° elevation), Edge-on (0° elevation), Close-up (3×Rs distance), and System view (200×Rs distance). Selecting a preset SHALL smoothly transition the camera over 1.5 seconds.

#### Scenario: Select camera preset
- **WHEN** the user selects a camera preset
- **THEN** the camera SHALL smoothly transition to the preset's position, elevation, and distance over 1.5 seconds using cubic ease-in-out

#### Scenario: Transition blocks input
- **WHEN** a camera transition is in progress
- **THEN** mouse input SHALL be ignored (or very heavily dampened) until the transition completes

### Requirement: Keyboard camera controls
The system SHALL support WASD for camera movement (forward/left/back/right), Q/E for up/down movement, and R for camera reset.

#### Scenario: WASD moves camera
- **WHEN** the user presses 'W'
- **THEN** the camera SHALL move forward relative to its current orientation at a speed proportional to its distance from the focus point

#### Scenario: R resets camera
- **WHEN** the user presses 'R'
- **THEN** the camera SHALL smoothly transition back to the default position and orientation over 1 second

### Requirement: Click-to-focus
The system SHALL allow clicking on an object in the 3D viewport to focus the camera on it with a smooth transition.

#### Scenario: Click object to focus
- **WHEN** the user clicks on a celestial object
- **THEN** the camera SHALL smoothly transition to focus on that object's position over 1.5 seconds

### Requirement: Touch camera controls
On touch devices, the system SHALL support: 1-finger drag for orbit, 2-finger drag for pan, and pinch for zoom.

#### Scenario: Single finger orbits
- **WHEN** the user drags with one finger on a touch device
- **THEN** the camera SHALL orbit around the focus point

#### Scenario: Pinch zooms
- **WHEN** the user performs a pinch gesture on a touch device
- **THEN** the camera SHALL zoom in or out based on the pinch distance change
