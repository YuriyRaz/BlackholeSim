## MODIFIED Requirements

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

### Requirement: Barnes-Hut tree optimization
The system SHALL use a Barnes-Hut or equivalent hierarchical approximation for massive matter gravity when the configured particle count exceeds the direct-sum threshold. The approximation parameters SHALL be explicit and its error SHALL be measured against direct summation in tests.

#### Scenario: Resolved matter uses hierarchical gravity
- **WHEN** the TDE particle count exceeds the direct-sum threshold
- **THEN** the solver SHALL build a spatial hierarchy and use it for matter gravity without removing particles from the force model

#### Scenario: Tree accuracy is bounded
- **WHEN** the same particle configuration is evaluated by direct gravity and the hierarchy
- **THEN** acceleration error SHALL remain below the configured tolerance for the supported scene
