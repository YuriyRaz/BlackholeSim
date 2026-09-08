# Gravity Solver

## Requirements

### Requirement: N-body gravitational integration
The system SHALL compute gravitational forces between black holes, bodies, and massive matter particles using the selected gravitational potential. The integrator SHALL use Velocity Verlet or an equivalent symplectic method for all resolved massive matter that participates in gravity.

#### Scenario: Two-body orbit conserves energy
- **WHEN** two bodies are placed in a circular orbit around their center of mass
- **THEN** the total energy SHALL remain constant within the configured tolerance over 100 orbital periods

#### Scenario: Matter particles respond to all configured masses
- **WHEN** a stellar particle is placed near a black hole and other massive matter
- **THEN** its acceleration SHALL include the black hole and all configured matter sources according to the selected gravity approximation

#### Scenario: No self-force
- **WHEN** computing the force on a particle or body
- **THEN** its own mass SHALL NOT contribute to its acceleration

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
The system SHALL use a Barnes-Hut or equivalent hierarchical approximation for massive matter gravity when the configured particle count exceeds the direct-sum threshold. The approximation parameters SHALL be explicit and its error SHALL be measured against direct summation in tests.

#### Scenario: Resolved matter uses hierarchical gravity
- **WHEN** the TDE particle count exceeds the direct-sum threshold
- **THEN** the solver SHALL build a spatial hierarchy and use it for matter gravity without removing particles from the force model

#### Scenario: Tree accuracy is bounded
- **WHEN** the same particle configuration is evaluated by direct gravity and the hierarchy
- **THEN** acceleration error SHALL remain below the configured tolerance for the supported scene

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
