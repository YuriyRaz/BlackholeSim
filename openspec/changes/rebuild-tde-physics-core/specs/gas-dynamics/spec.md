## MODIFIED Requirements

### Requirement: Gas particle orbital dynamics
Gas and stellar matter particles SHALL evolve under black-hole gravity, configured matter self-gravity, and SPH hydrodynamic forces. Each particle SHALL have position, velocity, mass, density, pressure, internal energy, temperature, and an accretion/lifecycle state. Gas SHALL NOT be treated as a passive tracer when pressure or shocks are relevant.

#### Scenario: Gas particles respond to shared dynamics
- **WHEN** gas particles evolve around a black hole
- **THEN** their positions and velocities SHALL be updated by gravity and hydrodynamic interactions from neighboring matter

#### Scenario: Disk-like structure follows angular momentum
- **WHEN** bound matter has a shared angular-momentum plane and loses orbital energy through resolved shocks
- **THEN** the particle distribution SHALL become disk-like without a pre-created ring

### Requirement: Viscous angular momentum transport
The system SHALL transport angular momentum through resolved SPH viscosity, shocks, and any explicitly configured subgrid stress term. Transport SHALL apply equal and opposite momentum changes to interacting matter and SHALL expose the associated energy dissipation.

#### Scenario: Angular momentum transport is measurable
- **WHEN** inner and outer disk matter exchange angular momentum
- **THEN** the change in angular momentum SHALL be observable in diagnostics and the total change SHALL match external torque and boundary flux within tolerance

#### Scenario: Outer matter responds on a longer timescale
- **WHEN** particles occupy different radii in a disk
- **THEN** the transport timescale SHALL increase with radius according to the configured disk model

### Requirement: Disk spreading
The disk's inner edge SHALL be determined by the capture/ISCO condition and its outer evolution SHALL be determined by particle angular momentum and transport. Total disk mass SHALL decrease only through measured accretion or explicit outflow.

#### Scenario: Disk structure emerges after circularization
- **WHEN** bound debris undergoes stream intersection and loses orbital energy
- **THEN** a disk-like population SHALL emerge from the resulting particle positions and velocities

#### Scenario: Disk mass has an accounting trail
- **WHEN** disk particles are accreted or leave the resolved domain
- **THEN** the mass change SHALL be recorded as accreted or escaped mass rather than silently deleting particles

### Requirement: Gas particle emission
Gas particles SHALL enter the gas/disk phase only through initial conditions explicitly describing a pre-existing disk or through a resolved transition of bound matter after circularization. TDE particles SHALL not be injected into a disk by index, timer, or renderer logic.

#### Scenario: Kerr preset may contain an initial disk
- **WHEN** a preset explicitly declares a pre-existing disk
- **THEN** its particles SHALL be initialized with positions, thermodynamic state, and angular-momentum-consistent velocities

#### Scenario: Disrupted debris transitions through physics
- **WHEN** disrupted matter becomes bound and circularizes through resolved interactions
- **THEN** its phase SHALL transition to gas/disk state without creating replacement particles or changing total mass
