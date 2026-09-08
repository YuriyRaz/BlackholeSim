# polytrope-sampling

## Purpose

Sample particle positions from the Lane-Emden density profile to accurately represent stellar interiors.

## Requirements

### Requirement: Lane-Emden density profile sampling
Particle positions SHALL follow the Lane-Emden density profile rather than uniform volume sampling. A cumulative mass profile SHALL be precomputed from the Lane-Emden solution. Particles SHALL be sampled via inverse CDF matching `M(ξ)/M_total`.

#### Scenario: Cumulative mass profile precomputed
- **WHEN** the polytrope is initialized
- **THEN** a cumulative mass profile `M(ξ)/M_total` SHALL be precomputed from the Lane-Emden solution

#### Scenario: Inverse CDF sampling
- **WHEN** a particle position is sampled
- **THEN** it SHALL be placed using inverse CDF sampling matching the cumulative mass profile

### Requirement: Density gradient preserved
Central density SHALL be higher than surface density after sampling. The density gradient SHALL be preserved, with particles concentrated toward the center.

#### Scenario: Central concentration
- **WHEN** particles are sampled from the polytrope
- **THEN** the central region SHALL contain a higher density of particles than the surface region
