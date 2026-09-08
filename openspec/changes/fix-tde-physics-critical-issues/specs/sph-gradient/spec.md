# Spec: SPH Gradient Direction

## Requirement

SPH pressure forces must repel particles when compressed, not attract them.

## Acceptance Criteria

- `gradWCubicSpline` receives `dir = (pi - pj)` = `(i-j)` direction
- Particles under high pressure accelerate away from each other
- Existing SPH density/force unit tests still pass
