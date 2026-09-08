# Spec: Particle Trails

## Requirement

Gas and matter particle trails must be updated each sub-step and visible in the renderer.

## Acceptance Criteria

- `_updateParticleTrails()` is called in `step()` after body trail updates
- `getState().particleTrails` is non-empty when trails are enabled
- Both gas and matter particles appear in trail data
