## ADDED Requirements

### Requirement: Play/pause control
The system SHALL provide play/pause control for the simulation. When paused, physics SHALL NOT advance but the scene SHALL remain renderable (camera can still orbit).

#### Scenario: Start in playing state
- **WHEN** the simulation loads
- **THEN** it SHALL be in playing state and physics SHALL advance each frame

#### Scenario: Pause freezes physics
- **WHEN** the user clicks pause (or presses Space)
- **THEN** the simulation time SHALL stop advancing and objects SHALL remain in their current positions

#### Scenario: Resume continues from pause point
- **WHEN** the user clicks play after pausing
- **THEN** the simulation SHALL continue from the exact state where it was paused

### Requirement: Speed multiplier
The system SHALL support a speed multiplier from 0.1× to 10× that scales the time step. The default speed SHALL be 1×.

#### Scenario: Slow motion at 0.1×
- **WHEN** speed is set to 0.1×
- **THEN** the simulation SHALL advance at 1/10th the normal rate

#### Scenario: Fast forward at 10×
- **WHEN** speed is set to 10×
- **THEN** the simulation SHALL advance at 10× the normal rate

#### Scenario: Speed change applies immediately
- **WHEN** the user changes speed from 1× to 5×
- **THEN** the next physics step SHALL use the new speed multiplier

### Requirement: Timeline scrubber
The system SHALL provide a timeline scrubber that shows the current simulation time and allows the user to drag to any point in time. Scrubbing SHALL recompute physics from the nearest prior state snapshot to the target time. Snapshots are taken every 100 simulation steps. For a forward scrub to a time beyond all snapshots, physics runs forward from the last snapshot. For a backward scrub, physics replays from the nearest earlier snapshot. Maximum recomputation for a scrub is 100 steps.

#### Scenario: Scrubber shows current time
- **WHEN** the simulation is at time t = 2.5 seconds
- **THEN** the scrubber position SHALL correspond to 2.5 seconds on the timeline

#### Scenario: Drag scrubber to rewind
- **WHEN** the user drags the scrubber from t = 2.5 to t = 1.0
- **THEN** the system SHALL find the nearest snapshot before t = 1.0 and recompute from that point (max 100 steps)

#### Scenario: Drag scrubber forward beyond last snapshot
- **WHEN** the user drags the scrubber to a time beyond all saved snapshots
- **THEN** the system SHALL run physics forward from the last snapshot to the target time

#### Scenario: Scrubber bounds
- **WHEN** the scrubber is displayed
- **THEN** it SHALL show the full range from t = 0 to the current maximum simulation time

### Requirement: Simulation time tracking
The system SHALL track total simulation time, independent of real wall-clock time. Simulation time SHALL advance by dt × speedMultiplier each frame when playing.

#### Scenario: Simulation time advances at 1×
- **WHEN** speed is 1× and 60 frames pass at 16.67ms each
- **THEN** simulation time SHALL advance by approximately 1.0 second

#### Scenario: Simulation time pauses
- **WHEN** the simulation is paused
- **THEN** simulation time SHALL NOT advance regardless of wall-clock time

### Requirement: Reset to initial state
The system SHALL provide a reset function that restores all objects to their initial positions, velocities, and states. The simulation time SHALL reset to 0.

#### Scenario: Reset restores initial conditions
- **WHEN** the user presses 'R' or clicks reset
- **THEN** all objects SHALL return to their positions and velocities at t = 0

#### Scenario: Reset after disruption
- **WHEN** a star has been disrupted and the user clicks reset
- **THEN** the star SHALL be restored to its intact state at its initial position

### Requirement: Time controls UI
The system SHALL display a time control bar with: play/pause button, speed selector (0.1×, 0.25×, 0.5×, 1×, 2×, 5×, 10×), current time display, and timeline scrubber.

#### Scenario: Time controls visible
- **WHEN** the simulation loads
- **THEN** a time control bar SHALL be visible at the bottom of the viewport

#### Scenario: Speed buttons update simulation
- **WHEN** the user clicks the "2×" speed button
- **THEN** the speed SHALL change to 2× and the button SHALL become highlighted
