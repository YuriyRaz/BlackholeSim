# disk-transition

## Purpose

Handle disk phase transition and circularization logic for particles transitioning from free-fall to bound disk orbits.

## Requirements

### Requirement: Disk phase transition triggers on circularity or shock
Disk phase transition SHALL fire when particles achieve sufficient circularity or experience shock heating. The transition SHALL work regardless of disk orientation.

#### Scenario: Shock heating persists until consumed
- **WHEN** a shock heating event sets the heating state
- **THEN** that state SHALL persist until `_updatePhaseTransitions` reads and clears it

#### Scenario: Circularity uses full angular momentum magnitude
- **WHEN** circularity is calculated for a particle
- **THEN** the calculation SHALL use the full angular momentum magnitude (all 3 components), not just one axis

#### Scenario: Existing phase transition tests pass
- **WHEN** the phase transition logic is updated
- **THEN** all existing phase transition tests SHALL continue to pass
