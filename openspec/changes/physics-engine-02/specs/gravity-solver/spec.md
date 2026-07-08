## ADDED Requirements

### Requirement: N-body gravitational integration
The system SHALL compute gravitational forces between all bodies using Newton's law of universal gravitation: F = G × m1 × m2 / r². The integrator SHALL use Velocity Verlet (symplectic) to update positions and velocities each time step.

#### Scenario: Two-body orbit conserves energy
- **WHEN** two bodies are placed in a circular orbit around their center of mass
- **THEN** the total energy (kinetic + potential) SHALL remain constant within 0.01% over 100 orbital periods

#### Scenario: Three-body interaction
- **WHEN** three bodies are placed in a gravitational system
- **THEN** the integrator SHALL compute forces from all pairs and update all positions consistently

#### Scenario: No self-force
- **WHEN** computing the force on body i
- **THEN** the force from body i on itself SHALL NOT be included (only pairs i≠j)

### Requirement: Softening parameter
The system SHALL use a softening parameter (ε = 0.01) in the gravity calculation to prevent singularities when two bodies are very close: F = G × m1 × m2 / (r² + ε²)^(3/2) × r̂.

#### Scenario: Close approach prevents NaN
- **WHEN** two bodies are at distance r = 0
- **THEN** the force SHALL be finite (not NaN or Infinity) due to softening

#### Scenario: Softening has negligible effect at large distances
- **WHEN** two bodies are at distance r = 100 (far from softening scale)
- **THEN** the softened force SHALL differ from unsimplified force by less than 0.001%

### Requirement: Adaptive time stepping
The system SHALL compute time step size based on the shortest orbital period: dt = 0.01 × T_min, where T_min = min(2π√(a³/GM)) for all pairs. dt SHALL be clamped between dt_min (0.0001) and dt_max (0.01).

#### Scenario: Close binary uses small time step
- **WHEN** two bodies are in a tight orbit with period T = 0.1
- **THEN** the time step SHALL be approximately 0.001 (0.01 × 0.1)

#### Scenario: Wide orbit uses larger time step
- **WHEN** the closest pair has orbital period T = 10
- **THEN** the time step SHALL be 0.01 (capped at dt_max)

#### Scenario: During merger, time step is minimal
- **WHEN** any two bodies are within 5× the Schwarzschild radius
- **THEN** the time step SHALL be forced to dt_min (0.0001)

### Requirement: Barnes-Hut tree optimization
The system SHALL use a Barnes-Hut tree for O(n log n) gravity computation when body count exceeds 100. The tree SHALL be rebuilt every frame. The opening angle θ SHALL be 0.5.

#### Scenario: 500 bodies compute in under 5ms
- **WHEN** 500 bodies are simulated with Barnes-Hut enabled
- **THEN** the physics step SHALL complete in under 5ms on a modern CPU

#### Scenario: Tree structure is rebuilt each frame
- **WHEN** bodies move during simulation
- **THEN** the Barnes-Hut tree SHALL be rebuilt from scratch at the start of each physics step

### Requirement: Velocity Verlet update rules
The integrator SHALL use the Velocity Verlet algorithm: position update x(t+dt) = x(t) + v(t)dt + 0.5a(t)dt², then compute new acceleration a(t+dt), then velocity update v(t+dt) = v(t) + 0.5(a(t) + a(t+dt))dt.

#### Scenario: Symplectic property preserves phase space volume
- **WHEN** a Hamiltonian system is integrated with Velocity Verlet
- **THEN** the phase space volume SHALL be preserved (no artificial dissipation)

#### Scenario: Time-reversible
- **WHEN** the simulation runs forward N steps then backward N steps
- **THEN** the final state SHALL match the initial state within floating-point precision

### Requirement: Fixed and dynamic bodies
The system SHALL support both fixed bodies (massive objects like black holes that don't move) and dynamic bodies (lighter objects that respond to gravity).

#### Scenario: Black hole remains fixed
- **WHEN** a black hole is marked as `fixed = true`
- **THEN** its position and velocity SHALL NOT change during simulation

#### Scenario: Star orbits black hole
- **WHEN** a star with `fixed = false` is placed near a fixed black hole
- **THEN** the star SHALL orbit the black hole according to Keplerian mechanics

### Requirement: Total energy computation
The system SHALL compute total system energy (kinetic + potential) for debugging and verification purposes.

#### Scenario: Energy calculation matches analytical
- **WHEN** two bodies are in a circular orbit
- **THEN** the computed total energy SHALL match the analytical value: E = -G×m1×m2/(2a)
