## ADDED Requirements

### Requirement: Phase indicator derives from physics state
The phase indicator SHALL read physics state (BH separation, accretion rate, GW strain, body disruption status) and derive the current phase. There are no hardcoded phase transitions — the phase is a function of the current physics state.

#### Scenario: Phase derived from BH separation
- **WHEN** two BHs are present
- **THEN** the phase SHALL be derived from their separation: "Inspiral" (separation > 5×Rs), "Merger" (separation < 5×Rs), "Remnant" (single BH)

#### Scenario: Phase derived from accretion
- **WHEN** gas particles are present and accretion rate is nonzero
- **THEN** the phase SHALL include accretion status: "Active accretion" or "Quiescent"

#### Scenario: Phase derived from tidal disruption
- **WHEN** a body is disrupted (tidal force > self-gravity)
- **THEN** the phase SHALL show "Tidal disruption" until debris circularizes

### Requirement: Phase indicator updates continuously
The phase indicator SHALL update every frame based on the current physics state. It SHALL NOT have fixed duration phases or manual transitions.

#### Scenario: Phase changes with physics
- **WHEN** BH separation crosses 5×Rs threshold
- **THEN** the phase indicator SHALL update within one frame

### Requirement: Phase indicator UI
The phase indicator SHALL be a small text overlay in the UI showing the current derived phase.

#### Scenario: Phase text displayed
- **WHEN** the simulation runs
- **THEN** a text element SHALL show the current phase (e.g., "Inspiral — 12×Rs", "Active accretion — dM/dt = 1.2×10⁻⁴ M☉/yr")
