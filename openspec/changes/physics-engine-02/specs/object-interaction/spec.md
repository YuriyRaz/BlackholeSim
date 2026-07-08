## ADDED Requirements

### Requirement: Click-to-focus
The system SHALL allow clicking on any celestial object in the 3D viewport to focus the camera on it. The camera SHALL smoothly transition to focus on the selected object over 1.5 seconds.

#### Scenario: Click on star to focus
- **WHEN** the user clicks on a star in the viewport
- **THEN** the camera SHALL smoothly transition to orbit that star, centering it in view

#### Scenario: Click on empty space to deselect
- **WHEN** the user clicks on empty space (no object hit)
- **THEN** the selection SHALL be cleared and the camera SHALL remain at its current position

#### Scenario: Click transitions are smooth
- **WHEN** an object is selected via click
- **THEN** the camera transition SHALL use cubic ease-in-out over 1.5 seconds (no jarring jumps)

### Requirement: Object selection highlighting
The system SHALL visually highlight the currently selected object with a subtle glow or outline effect. Only one object SHALL be selected at a time.

#### Scenario: Selected object has visual indicator
- **WHEN** an object is selected
- **THEN** a subtle glow or outline SHALL appear around it

#### Scenario: Selecting new object deselects old
- **WHEN** a new object is clicked while another is selected
- **THEN** the old object SHALL lose its highlight and the new object SHALL gain it

### Requirement: Object list panel
The system SHALL display a panel listing all objects in the scene with their type icon, name, and key properties (mass, velocity). Clicking an item in the list SHALL focus the camera on that object.

#### Scenario: Object list shows all bodies
- **WHEN** the scene contains a black hole, a star, and 10 particles
- **THEN** the object list SHALL show 12 entries with type icons and names

#### Scenario: Click list item focuses camera
- **WHEN** the user clicks on a star entry in the object list
- **THEN** the camera SHALL transition to focus on that star (same as viewport click)

### Requirement: Orbital path visualization
The system SHALL render orbital trajectories for selected objects as semi-transparent line trails. Trails SHALL show the last 200 positions and fade with age.

#### Scenario: Selected object shows trail
- **WHEN** an object is selected
- **THEN** a line trail showing its recent path SHALL appear

#### Scenario: Trail fades with age
- **WHEN** the trail renders
- **THEN** older segments SHALL be more transparent than recent segments

#### Scenario: Trail can be toggled
- **WHEN** the user unchecks "Orbital paths" in display toggles
- **THEN** all orbital trails SHALL be hidden

### Requirement: Orbit preview ellipse
The system SHALL display a semi-transparent ellipse showing the complete orbital path of a selected object, computed from its current orbital elements.

#### Scenario: Selected object shows orbit preview
- **WHEN** an object is selected and is in a bound orbit
- **THEN** a semi-transparent ellipse showing its full orbit SHALL be rendered

#### Scenario: Preview updates with decay
- **WHEN** the orbit is decaying
- **THEN** the preview ellipse SHALL shrink each frame to match the current orbital elements

### Requirement: Object info on hover
The system SHALL display a tooltip when the user hovers over a celestial object, showing its name, type, and mass.

#### Scenario: Hover tooltip appears
- **WHEN** the mouse hovers over a celestial object for 500ms
- **THEN** a tooltip SHALL appear near the cursor showing the object's name, type, and mass

#### Scenario: Tooltip follows cursor
- **WHEN** the tooltip is visible and the mouse moves
- **THEN** the tooltip SHALL follow the cursor position

### Requirement: Physics info panel expansion
The system SHALL expand the physics info panel from core-renderer-01 to include: orbital frequency, orbital velocity, GW strain (if binary), object count, and simulation time.

#### Scenario: Info panel shows orbital data
- **WHEN** a star is orbiting a black hole
- **THEN** the info panel SHALL display the star's orbital frequency and velocity

#### Scenario: Info panel shows GW strain
- **WHEN** two black holes are in a binary
- **THEN** the info panel SHALL display the current GW strain amplitude
