# Spec: Circularization and Disk Transition

## Requirement

Disk phase transition must fire when particles achieve sufficient circularity or experience shock heating, regardless of disk orientation.

## Acceptance Criteria

- Shock heating state persists until `_updatePhaseTransitions` reads it
- Circularity calculation uses full angular momentum magnitude (all 3 components)
- Existing phase transition tests still pass
