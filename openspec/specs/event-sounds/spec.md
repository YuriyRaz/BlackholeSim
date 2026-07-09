# Event Sounds

## Purpose

Generates procedural audio effects for physics events: disruption crackle, merger impact, and accretion whoosh. All sounds are triggered by physics state changes.

## Requirements

### Requirement: Disruption crackle sound
The system SHALL play a crackling/tearing sound when a star is tidally disrupted. The sound SHALL be generated from filtered white noise with rapid amplitude modulation.

#### Scenario: Disruption triggers sound
- **WHEN** a star crosses the Roche limit and is disrupted
- **THEN** a crackling/tearing sound SHALL play for ~1 second

#### Scenario: Disruption sound is procedural
- **WHEN** the disruption sound plays
- **THEN** it SHALL be generated from noise + filters, not from an audio file

### Requirement: Merger impact sound
The system SHALL play a deep impact sound when two black holes merge. The sound SHALL combine a noise burst with reverb tail, simulating the energy release.

#### Scenario: Merger triggers impact
- **WHEN** two black holes merge
- **THEN** a deep impact sound SHALL play with ~2 second reverb tail

#### Scenario: Impact sound has bass emphasis
- **WHEN** the merger impact plays
- **THEN** the sound SHALL be dominated by low frequencies (20-100 Hz)

### Requirement: Accretion whoosh sound
The system SHALL play a continuous whooshing sound when accretion is active. The sound SHALL be low-pass filtered white noise with volume proportional to accretion rate.

#### Scenario: Accretion produces whoosh
- **WHEN** matter is actively accreting onto a black hole
- **THEN** a low whooshing sound SHALL be audible

#### Scenario: Whoosh volume scales with accretion rate
- **WHEN** accretion rate increases (e.g., peak fallback in TDE)
- **THEN** the whoosh volume SHALL increase proportionally

### Requirement: Event sounds triggered by physics state
Each event sound type SHALL be triggered by changes in physics state, not by a scenario manager. The audio engine SHALL subscribe to physics state changes and trigger sounds accordingly.

#### Scenario: Disruption sound from physics state
- **WHEN** the physics engine reports a body as disrupted (body.disrupted = true)
- **THEN** the audio engine SHALL play the disruption crackle sound

#### Scenario: Merger sound from BH proximity
- **WHEN** the physics engine reports BH separation < 5×Rs
- **THEN** the audio engine SHALL play the merger impact sound

#### Scenario: Accretion sound from accretion rate
- **WHEN** the physics engine reports accretionRate > 0
- **THEN** the audio engine SHALL play the accretion whoosh sound

### Requirement: Event sounds layer independently
Event sounds SHALL play on their own gain node, independent of the spacetime hum and GW sound layers.

#### Scenario: Event sound overlaps with hum
- **WHEN** a disruption occurs while the spacetime hum is playing
- **THEN** both sounds SHALL be audible simultaneously without interference
