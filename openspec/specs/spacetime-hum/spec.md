# Spacetime Hum

## Purpose

Generates the ambient spacetime hum sound with harmonics, LFO breathing, proximity-based volume, pitch shifting, and multi-black-hole dissonance.

## Requirements

### Requirement: Base frequency harmonics
The spacetime hum SHALL generate a base frequency at 40 Hz with harmonics at 80 Hz, 120 Hz, and 160 Hz. Each harmonic SHALL have independently configurable amplitude.

#### Scenario: 40 Hz base tone
- **WHEN** the spacetime hum is active
- **THEN** a 40 Hz sine wave SHALL be audible at the base amplitude

#### Scenario: Harmonic series
- **WHEN** the spacetime hum is active
- **THEN** sine waves at 80, 120, and 160 Hz SHALL be audible with decreasing amplitude (1.0, 0.5, 0.3, 0.2)

### Requirement: LFO breathing modulation
The spacetime hum SHALL use a low-frequency oscillator (LFO) at 0.5 Hz to modulate the amplitude, creating a "breathing" effect with ±10% depth.

#### Scenario: Breathing effect
- **WHEN** the spacetime hum plays
- **THEN** the volume SHALL oscillate subtly at 0.5 Hz (one cycle every 2 seconds)

### Requirement: Proximity-based volume
The spacetime hum volume SHALL scale inversely with distance to the nearest black hole. Closer = louder, farther = quieter.

#### Scenario: Louder near black hole
- **WHEN** the camera is close to a black hole (within 10×Rs)
- **THEN** the hum volume SHALL be at maximum

#### Scenario: Quieter far from black hole
- **WHEN** the camera is far from all black holes (beyond 100×Rs)
- **THEN** the hum volume SHALL decrease to near silence

### Requirement: Pitch shift with approach
The spacetime hum pitch SHALL shift slightly upward as the camera approaches a black hole, simulating a blueshift feel.

#### Scenario: Pitch increases on approach
- **WHEN** the camera moves toward a black hole
- **THEN** the hum frequency SHALL increase by up to 20% (40 Hz → 48 Hz)

### Requirement: Multi-BH dissonance
When multiple black holes are present, the spacetime hum SHALL layer frequencies from each BH with slight detuning, creating audible dissonance.

#### Scenario: Two black holes create dissonance
- **WHEN** two black holes are present in the scene
- **THEN** two sets of hum frequencies SHALL play with slight pitch offset (1-2 Hz difference)
