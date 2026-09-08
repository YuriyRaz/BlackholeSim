# Tasks: Fix TDE Physics Critical Issues

## 1. SPH Gradient Fix

- [x] 1.1 Fix `gradWCubicSpline` call site in `src/physics/SPHSolver.js`: change `dir` from `(pj - pi)` to `(pi - pj)` so pressure forces repel instead of attract.

## 2. Circularization/Disk Transition

- [x] 2.1 Fix shock heating dead code: move `_shockHeating = 0` reset in `_integrateMatterSPH` to after `_updatePhaseTransitions` reads it in the substep loop.
- [x] 2.2 Fix circularity calculation: replace single-component `vPhi` with full angular momentum magnitude in `_updatePhaseTransitions`.

## 3. Performance Benchmark

- [x] 3.1 Update `test/benchmarks.test.js` assertions to enforce minimum 30 FPS for rendering and realistic floors for physics sub-steps.

## 4. Particle Trails

- [x] 4.1 Add `this._updateParticleTrails()` call in `PhysicsEngine.step()` after body trail updates.

## 5. Polytrope Sampling

- [x] 5.1 Implement cumulative mass profile precomputation in `Polytrope.js` and replace `cbrt(random)` with inverse CDF sampling.

## 6. Conservation Ledger

- [x] 6.1 Add `momentum: { linear, angular }` to `ConservationLedger.getDiagnostics()` output.
- [x] 6.2 Call `this._ledger.recordEscape(p.mass)` in `PhysicsEngine._classifyBoundParticles()` when particles escape.
