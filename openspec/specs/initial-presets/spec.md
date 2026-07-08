# Initial Presets

## Requirements

### Requirement: Presets are data functions, not classes
Initial condition presets SHALL be functions that return arrays of bodies and gas particles. They SHALL NOT be classes with state machines, phase transitions, or update logic. A preset is just data: positions, velocities, masses, spins, gas particle distributions.

#### Scenario: Preset returns body array
- **WHEN** a preset function is called
- **THEN** it SHALL return an object: { bodies: [...], gas: [...], camera: {...} }

#### Scenario: Preset has no state or update method
- **WHEN** a preset is loaded
- **THEN** it SHALL NOT have init(), update(), reset(), or dispose() methods — just a function returning data

### Requirement: Binary BH preset
The "Binary BH" preset SHALL place two black holes (36 M_sun and 29 M_sun) on a decaying circular orbit at separation 20×Rs. No gas particles. The orbital decay emerges from GW energy loss in the physics engine.

#### Scenario: Binary BH initial conditions
- **WHEN** the Binary BH preset is loaded
- **THEN** two BHs SHALL be placed at 20×Rs separation with circular orbit velocities

#### Scenario: Merger emerges from physics
- **WHEN** the simulation runs with Binary BH preset
- **THEN** the BHs SHALL spiral together due to GW emission, merge when close, and form a remnant — all from the physics engine, not from preset logic

### Requirement: TDE preset
The "TDE" preset SHALL place a 10^6 M_sun black hole at the origin and a 1 M_sun, 1 R_sun star on an eccentric orbit (e=0.9) with periapsis within the tidal disruption radius. The disruption, tidal stream formation, disk formation, and jet emission all emerge from the physics engine.

#### Scenario: TDE initial conditions
- **WHEN** the TDE preset is loaded
- **THEN** a BH and star SHALL be placed on an eccentric orbit with periapsis inside the tidal radius

#### Scenario: Disruption emerges from physics
- **WHEN** the simulation runs with TDE preset
- **THEN** the star SHALL be disrupted by tidal forces, form a tidal stream, circularize into a disk, and potentially produce jets — all from the physics engine

### Requirement: Kerr preset
The "Kerr" preset SHALL place a 10 M_sun black hole with spin=0.998 and a pre-existing gas disk (100 gas particles on circular orbits between 10-50×Rs). Frame dragging, ISCO effects, disk evolution, and jet emission emerge from the physics engine.

#### Scenario: Kerr initial conditions
- **WHEN** the Kerr preset is loaded
- **THEN** a spinning BH and gas disk particles SHALL be placed

#### Scenario: Kerr effects emerge from physics
- **WHEN** the simulation runs with Kerr preset
- **THEN** frame dragging, ISCO plunge, disk spreading, and jets SHALL emerge from the physics engine

### Requirement: Custom preset
The "Custom" preset SHALL allow the user to place arbitrary bodies and gas particles. The UI SHALL provide controls for adding BHs, stars, and gas clouds at specified positions.

#### Scenario: Custom preset with user-placed objects
- **WHEN** the user selects Custom preset and places objects
- **THEN** those objects SHALL be used as initial conditions for the physics engine

### Requirement: Preset loading
The UI SHALL provide buttons to load each preset. Loading a preset SHALL reset the physics engine and load the new initial conditions. The camera SHALL transition to a sensible viewing angle for the preset.

#### Scenario: Preset button loads initial conditions
- **WHEN** the user clicks a preset button
- **THEN** the physics engine SHALL reset and load the preset's bodies and gas particles

#### Scenario: Camera adjusts to preset
- **WHEN** a preset is loaded
- **THEN** the camera SHALL transition to a viewing angle appropriate for the preset
