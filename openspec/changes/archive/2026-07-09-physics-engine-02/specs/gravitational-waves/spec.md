## ADDED Requirements

### Requirement: Chirp mass computation
The system SHALL compute the chirp mass from two orbital bodies: M_chirp = (m1 × m2)^(3/5) / (m1 + m2)^(1/5). The chirp mass SHALL be used in GW frequency and strain calculations.

#### Scenario: Equal mass binary
- **WHEN** m1 = m2 = M
- **THEN** the chirp mass SHALL be M × (1/4)^(3/5) = M × 0.4353

#### Scenario: Unequal mass binary
- **WHEN** m1 = 36 M_sun and m2 = 29 M_sun
- **THEN** the chirp mass SHALL be approximately 28.3 M_sun (matching GW150914)

### Requirement: GW frequency evolution
The system SHALL compute the gravitational wave frequency as the binary inspirals: f_GW = (1/π) × (5/(256 × τ))^(3/8) × (G × M_chirp / c³)^(-5/8), where τ = t_merge - t is the time to merger.

#### Scenario: Frequency increases during inspiral
- **WHEN** a binary system is inspiraling
- **THEN** the GW frequency SHALL increase over time (chirp)

#### Scenario: Frequency at ISCO
- **WHEN** the binary reaches the innermost stable circular orbit
- **THEN** the GW frequency SHALL be approximately c³ / (6√6 × π × G × M_total)

### Requirement: GW strain amplitude
The system SHALL compute the GW strain at distance d: h = (4/d) × (G × M_chirp / c²)^(5/3) × (π × f_GW / c)^(2/3).

#### Scenario: Strain increases with chirp mass
- **WHEN** two different binaries have different chirp masses at the same frequency
- **THEN** the binary with larger chirp mass SHALL produce larger strain

#### Scenario: Strain decreases with distance
- **WHEN** the same binary is observed at different distances
- **THEN** the strain SHALL be inversely proportional to distance

### Requirement: Quasi-normal mode (ringdown)
After merger, the system SHALL compute the ringdown frequency and damping time: f_QNM = c³ / (2π × G × M_final) × F(a_final), where F(a) depends on final spin. Damping time: τ = 1 / (2π × f_QNM × Q), where Q ≈ 2 × (1 - a)^(-0.45).

#### Scenario: Ringdown frequency for 62 solar mass remnant
- **WHEN** the remnant mass is 62 M_sun with spin a = 0.67
- **THEN** the QNM frequency SHALL be approximately 250 Hz

#### Scenario: Damping time for high-spin remnant
- **WHEN** the remnant has high spin (a > 0.9)
- **THEN** the damping time SHALL be shorter (faster ringdown)

### Requirement: Energy radiated in GWs
The system SHALL compute the energy radiated during binary inspiral: E_GW = (32/5) × G⁴ × m1² × m2² × (m1 + m2) / (c⁵ × a⁵) integrated over the inspiral duration.

#### Scenario: GW150914 energy budget
- **WHEN** a 36+29 M_sun binary merges
- **THEN** the total energy radiated SHALL be approximately 5 × 10^47 joules (about 3 M_sun × c²)

### Requirement: GW data for audio synchronization
The system SHALL expose GW frequency, strain, and phase as properties that can be read by the audio system (Proposal 4) for sonification. Values SHALL update each frame during simulation.

#### Scenario: GW data is available each frame
- **WHEN** the simulation is running with a binary system
- **THEN** properties gwFrequency, gwStrain, and gwPhase SHALL be readable from the physics engine
