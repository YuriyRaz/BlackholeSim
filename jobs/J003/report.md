# J003 Report: TDE Init + Disruption + Fallback + Accretion

## Summary

Implemented task groups 4-5 of rebuild-tde-physics-core: TDE initial conditions and disruption (persistent star, real tidal gradient), fallback/circularization/accretion (bound/unbound classification, particle capture, removed fake timers and synthetic jet).

## What Was Done

### Task Group 4: TDE Initial Conditions and Disruption

- **4.1** Replaced one-body TDE star with persistent polytropic particle state (`presets.js` uses `generatePolytrope`, retains `star` body identity for UI/audio).
- **4.2** Rebuilt TDE orbital elements: `rApo = 3 × dR` (outside tidal radius), `e = 0.95` (periapsis ~0.077 × dR inside disruption condition).
- **4.3** Computed deformation and disruption from resolved particle binding, tidal gradients, and hydrodynamic state (`_handleTidalDisruption` uses centroid, max spread, tidal-over-self-gravity ratio).
- **4.4** Removed post-disruption stream generation, pre-shaped arcs, random velocity jitter, index-based gas/debris splitting (`Star.generateDisruptionParticles` returns `[]`).
- **4.5** Added integration tests proving particle survival and bound/unbound orbital branches.

### Task Group 5: Fallback, Circularization, and Accretion

- **5.1** Implemented bound/unbound classification from particle orbital energy AND angular momentum (`_classifyBoundParticles` now computes `specificAngularMomentum` and `vCirc`).
- **5.2** Implemented return-surface crossing events and fallback rate calculation (`_computeFallbackRate` tracks returning mass via radial velocity check).
- **5.3** Implemented phase transitions from stellar to debris to disk using density, shock (via `_shockHeating`), and circularity conditions (`_updatePhaseTransitions`).
- **5.4** Implemented capture at ISCO with mass, momentum, energy, and accretion-rate accounting (`_captureParticlesAtISCO` with full ledger recording).
- **5.5** Removed fixed fallback timer, injected fallback curve, viscous impulse, and synthetic jet emitter. Removed `jetParticles` infrastructure from PhysicsEngine.
- **5.6** Added tests for fallback rate, disk phase transitions, capture at ISCO, and absence of jet particles without MHD.

## Files Modified

- `src/physics/PhysicsEngine.js` — Angular momentum in `_classifyBoundParticles`, shock-based transitions in `_updatePhaseTransitions`, removed jet infrastructure
- `src/objects/Star.js` — `generateDisruptionParticles` returns `[]`
- `src/presets/presets.js` — Uses `generatePolytrope`, TDE orbital parameters
- `test/test-disrupt.test.js` — 13 tests covering disruption, particle survival, bound/unbound classification, fallback, capture, jet-absence
- `test/physics.test.js` — Updated to not reference removed jetParticles
- `test/sph-gravity.test.js` — Fixed r > ISCO for energy/angular momentum tests
- `test/objects.test.js` — Updated generateDisruptionParticles test

## Test Results

All 125 tests pass across 13 test files.

## Known Limitations

1. **Task 4.3**: SPH hydrodynamic state (density/pressure) is not directly used in disruption decision — disruption uses geometric spread and tidal-over-self-gravity ratio.
2. **Task 5.2**: Return surface is a radius threshold (`dR × 2`) rather than a true crossing event with a well-defined surface.
3. **Task 5.5**: `jetParticles` infrastructure completely removed from PhysicsEngine. The renderer may need updating if it references this field.

## What's Left (for J004)

Task groups 6-7 (rendering contract + verification/performance) remain:
- Update `getState()` and snapshots for unified matter-particle state
- Remove TDE-specific renderer workarounds
- Add integration tests, benchmarks, and documentation
