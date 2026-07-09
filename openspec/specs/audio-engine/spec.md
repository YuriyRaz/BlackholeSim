# Audio Engine

## Purpose

Manages the Web Audio API lifecycle, master gain/compressor chain, per-layer volume controls, and mute state persistence.

## Requirements

### Requirement: Audio context initialization
The system SHALL create a Web Audio API AudioContext on first user interaction (click or touch). The context SHALL start in suspended state and resume on user gesture.

#### Scenario: Audio context created on first interaction
- **WHEN** the user clicks or touches the page for the first time
- **THEN** an AudioContext SHALL be created and remain suspended until unmuted

#### Scenario: Audio context resumes on unmute
- **WHEN** the user clicks the unmute button
- **THEN** the AudioContext SHALL call `resume()` and audio output SHALL begin

### Requirement: Master gain and compressor
The system SHALL provide a master gain node and a dynamics compressor node in the signal chain. The compressor SHALL prevent clipping during loud events (mergers, disruptions).

#### Scenario: Master gain controls overall volume
- **WHEN** the user adjusts the master volume slider
- **THEN** the master gain SHALL change proportionally (0.0 to 1.0)

#### Scenario: Compressor prevents clipping
- **WHEN** a loud merger event occurs
- **THEN** the compressor SHALL reduce peak levels to prevent audio distortion

### Requirement: Audio starts muted
Audio SHALL be muted by default on first load. The mute toggle SHALL be visible and clickable. Mute state SHALL persist across sessions via localStorage.

#### Scenario: Audio muted on first load
- **WHEN** the application loads for the first time
- **THEN** all audio output SHALL be silent and the mute button SHALL show the muted state

#### Scenario: Mute state persists
- **WHEN** the user unmutes audio, then reloads the page
- **THEN** audio SHALL remain unmuted (persisted in localStorage)

### Requirement: Per-layer volume control
The system SHALL provide independent volume controls for three audio layers: spacetime hum, gravitational wave sound, and event sounds. Each layer SHALL have its own gain node.

#### Scenario: Adjust hum volume independently
- **WHEN** the user adjusts the spacetime hum volume slider
- **THEN** only the hum layer SHALL be affected; GW and event sounds SHALL remain unchanged

#### Scenario: Mute individual layer
- **WHEN** the user clicks the mute icon next to "Spacetime Hum"
- **THEN** only the hum layer SHALL be muted; other layers continue playing

### Requirement: Audio engine lifecycle
The audio engine SHALL initialize with the renderer, subscribe to physics state changes, and clean up on reset.

#### Scenario: Audio initializes with renderer
- **WHEN** the application starts
- **THEN** the audio engine SHALL create all audio nodes and connect them to the master output

#### Scenario: Audio resets on physics reset
- **WHEN** the physics engine resets (preset loaded)
- **THEN** all active sounds SHALL be stopped and re-initialized for the new state
