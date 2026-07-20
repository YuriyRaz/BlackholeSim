## MODIFIED Requirements

### Requirement: TDE preset
The "TDE" preset SHALL place a 10^6 M_sun black hole at the origin and a resolved 1 M_sun, 1 R_sun star on a physically defined eccentric encounter that starts outside the tidal disruption radius and has a periapsis inside it. The preset SHALL contain the star's initial matter-particle state but SHALL NOT contain a pre-created tidal stream, accretion disk, fallback timer, or jet.

#### Scenario: TDE initial conditions
- **WHEN** the TDE preset is loaded
- **THEN** the black hole and resolved star SHALL be separated by more than the tidal radius and the orbital elements SHALL imply a periapsis inside the tidal radius

#### Scenario: Disruption and disk emerge from initial conditions
- **WHEN** the simulation runs with the TDE preset
- **THEN** tidal deformation, stream formation, fallback, circularization, and accretion SHALL emerge from the physics engine state without preset update logic or injected particle effects
