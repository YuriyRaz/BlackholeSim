## MODIFIED Requirements

### Requirement: Preset selector
The system SHALL display preset buttons at the top of the viewport. The active preset SHALL be visually highlighted. All presets SHALL be functional — clicking a preset loads its initial conditions into the physics engine.

#### Scenario: Preset buttons visible
- **WHEN** the application loads
- **THEN** preset selector buttons SHALL be displayed at the top center of the viewport

#### Scenario: Default preset active
- **WHEN** the application loads
- **THEN** the "Kerr" preset button SHALL be highlighted as active by default

#### Scenario: Clicking preset loads initial conditions
- **WHEN** the user clicks a preset button
- **THEN** the physics engine SHALL reset and load the preset's bodies and gas particles

### Requirement: Physics info panel
The system SHALL display a panel showing real-time physics data: black hole mass (solar masses), spin parameter, Schwarzschild radius, accretion rate, GW strain/frequency, particle count, and current FPS.

#### Scenario: Info panel displays BH properties
- **WHEN** the simulation is running
- **THEN** the info panel SHALL show the current black hole's mass, spin, and Schwarzschild radius

#### Scenario: Info panel displays accretion rate
- **WHEN** gas particles are being accreted
- **THEN** the info panel SHALL show the current accretion rate (dM/dt)

#### Scenario: Info panel displays GW data
- **WHEN** the physics engine reports gwStrain > 0
- **THEN** the info panel SHALL show GW frequency and strain

#### Scenario: FPS display updates
- **WHEN** the simulation is running
- **THEN** the FPS counter SHALL update at least every 10 frames

### Requirement: Display toggles
The system SHALL provide toggle switches for: lensing, particles, stars, jets, GW ripples, particle trails, and post-processing.

#### Scenario: Toggle lensing off
- **WHEN** the user unchecks the "Lensing" toggle
- **THEN** gravitational lensing SHALL be disabled

#### Scenario: Toggle particles off
- **WHEN** the user unchecks the "Particles" toggle
- **THEN** all particles (gas, jet, debris) SHALL not be rendered

#### Scenario: Toggle stars off
- **WHEN** the user unchecks the "Stars" toggle
- **THEN** the procedural starfield SHALL not be rendered

#### Scenario: Toggle jets off
- **WHEN** the user unchecks the "Jets" toggle
- **THEN** jet particles SHALL not be rendered (physics continues)

#### Scenario: Toggle GW ripples off
- **WHEN** the user unchecks the "GW Ripples" toggle
- **THEN** gravitational wave ripple distortion SHALL not be applied

#### Scenario: Toggle particle trails off
- **WHEN** the user unchecks the "Trails" toggle
- **THEN** particle trail lines SHALL not be rendered

### Requirement: Quality selector
The system SHALL provide a quality selector with options: Low, Medium, High, Auto. The current selection SHALL be visually indicated.

#### Scenario: Quality selector visible
- **WHEN** the UI renders
- **THEN** a quality selector with 4 options SHALL be visible

#### Scenario: Current quality highlighted
- **WHEN** quality is set to "Medium"
- **THEN** the "Medium" option SHALL be visually highlighted

### Requirement: Camera mode toggle
The system SHALL provide a toggle between "Free" and "Cinematic" camera modes.

#### Scenario: Toggle to cinematic
- **WHEN** the user clicks the "Cinematic" button
- **THEN** the camera SHALL begin auto-orbiting

#### Scenario: Toggle to free
- **WHEN** the user clicks the "Free" button
- **THEN** the camera SHALL stop auto-orbiting and respond to user input

### Requirement: Phase indicator
The system SHALL display a text element showing the current phase, derived from physics state (BH separation, accretion rate, tidal disruption status).

#### Scenario: Phase displayed
- **WHEN** the simulation runs
- **THEN** a text element SHALL show the current phase (e.g., "Inspiral — 12×Rs", "Active accretion")

### Requirement: Keyboard shortcuts overlay
The system SHALL display a keyboard shortcuts overlay that appears for 5 seconds after application load, then fades out.

#### Scenario: Shortcuts appear on load
- **WHEN** the application loads
- **THEN** a semi-transparent overlay listing keyboard shortcuts SHALL appear

#### Scenario: Shortcuts fade after 5 seconds
- **WHEN** 5 seconds have passed
- **THEN** the shortcuts overlay SHALL fade out

#### Scenario: H key toggles shortcuts
- **WHEN** the user presses 'H'
- **THEN** the shortcuts overlay SHALL toggle visibility

### Requirement: Responsive layout
The UI SHALL adapt to different screen sizes. On desktop (>1024px), all panels visible. On tablet (768-1024px), icon-only mode.

#### Scenario: Desktop layout
- **WHEN** viewport width > 1024px
- **THEN** all UI panels SHALL display with full labels

#### Scenario: Tablet layout
- **WHEN** viewport width is 768-1024px
- **THEN** UI panels SHALL collapse to icon-only mode

### Requirement: Mute toggle
The system SHALL provide a mute toggle button. Since audio is not implemented in this proposal, the button SHALL be present but non-functional.

#### Scenario: Mute button visible
- **WHEN** the UI renders
- **THEN** a mute toggle button SHALL be visible

### Requirement: Window resize handling
The system SHALL respond to browser window resize events by updating the canvas dimensions within 100ms.

#### Scenario: Resize updates canvas
- **WHEN** the browser window is resized
- **THEN** the canvas SHALL update to fill its container

### Requirement: Visibility change handling
The system SHALL pause the render loop when the browser tab is hidden and resume when visible.

#### Scenario: Tab hidden pauses rendering
- **WHEN** the browser tab becomes hidden
- **THEN** the render loop SHALL stop

#### Scenario: Tab visible resumes rendering
- **WHEN** the browser tab becomes visible
- **THEN** the render loop SHALL resume with delta time reset to 0
