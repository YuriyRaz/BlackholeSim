## ADDED Requirements

### Requirement: GW chirp frequency sweep
The GW sound SHALL map the gravitational wave frequency to an audible oscillator. During inspiral, the frequency SHALL sweep upward following the chirp formula, peaking at merger.

#### Scenario: Chirp sweeps upward
- **WHEN** a binary system is in inspiral
- **THEN** the GW sound oscillator SHALL increase in frequency from ~40 Hz to ~300 Hz

#### Scenario: Chirp peaks at merger
- **WHEN** the binary merges
- **THEN** the GW sound SHALL reach its highest frequency and volume

### Requirement: Dual-polarization oscillators
The GW sound SHALL use two detuned oscillators (h+ and h× polarizations) with slight frequency offset to create a richer, more complex sound than a single oscillator.

#### Scenario: Two oscillators create texture
- **WHEN** the GW sound plays
- **THEN** two sine oscillators SHALL be audible with 0.1-1 Hz frequency difference

### Requirement: Ringdown damped oscillation
After merger, the GW sound SHALL transition to a damped sinusoid at the QNM frequency (~250 Hz for 62 M_sun remnant), decaying over ~0.5 seconds.

#### Scenario: Ringdown decays
- **WHEN** the merger completes
- **THEN** the GW sound SHALL play a damped oscillation at 250 Hz, fading to silence over 0.5 seconds

### Requirement: GW sound amplitude scales with strain
The GW sound volume SHALL be proportional to the gravitational wave strain amplitude. Louder for more massive binaries, quieter for distant ones.

#### Scenario: Strain scales volume
- **WHEN** GW strain increases during inspiral
- **THEN** the GW sound volume SHALL increase proportionally

### Requirement: GW sound only during binary events
The GW sound SHALL only play when a binary system is present and in inspiral or merger phase. After ringdown, the sound SHALL fade to silence.

#### Scenario: GW sound silent for single BH
- **WHEN** only a single black hole is present (no binary)
- **THEN** the GW sound layer SHALL produce no output

### Requirement: GW sound toggle
The GW sound SHALL be independently toggleable via the per-layer mute controls.

#### Scenario: Mute GW sound
- **WHEN** the user mutes the GW sound layer
- **THEN** the GW chirp SHALL be silent while other audio layers continue
