# Black Hole Spin Effects

## Requirements

### Requirement: Frame dragging
The system SHALL compute frame dragging effects for spinning black holes. Test particles orbiting a spinning BH SHALL precess in the direction of the BH's spin. The precession rate SHALL decrease with distance from the BH.

#### Scenario: Particles precess in spin direction
- **WHEN** test particles orbit a spinning black hole
- **THEN** their orbits SHALL precess in the direction of the black hole's rotation

#### Scenario: Precession rate decreases with distance
- **WHEN** particles are at different radii
- **THEN** inner particles SHALL precess faster than outer particles

### Requirement: ISCO shift from spin
The ISCO radius SHALL depend on the BH spin parameter: r_isco = 6×Rs for a*=0 (Schwarzschild), decreasing to 1×Rs for a*=1 (maximal Kerr). Prograde orbits have smaller ISCO than retrograde orbits.

#### Scenario: ISCO for Schwarzschild BH
- **WHEN** BH spin = 0
- **THEN** ISCO SHALL be at 6×Rs

#### Scenario: ISCO for maximal Kerr BH
- **WHEN** BH spin = 1
- **THEN** ISCO SHALL be at 1×Rs for prograde orbits

### Requirement: Ergosphere region
The system SHALL compute the ergosphere region around a spinning black hole. The ergosphere SHALL be largest at the equator and smallest at the poles (oblate spheroid). The outer boundary SHALL be: r_ergo = Rs × (1 + √(1 - a*² × cos²θ)).

#### Scenario: Ergosphere visible as oblate region
- **WHEN** a spinning BH is rendered
- **THEN** an ergosphere region SHALL be computable from the spin parameter

#### Scenario: Ergosphere vanishes for Schwarzschild
- **WHEN** BH spin = 0
- **THEN** the ergosphere SHALL have zero extent (no ergosphere)

### Requirement: Ergosphere particle interaction
Particles that enter the ergosphere SHALL be forced to co-rotate with the black hole. Their orbital direction SHALL align with the BH spin regardless of initial velocity.

#### Scenario: Ergosphere forces co-rotation
- **WHEN** a particle enters the ergosphere
- **THEN** its velocity SHALL be forced to align with the black hole's rotation direction
