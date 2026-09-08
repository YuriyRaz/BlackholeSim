# Design: Fix TDE Physics Critical Issues

## Issue 1: SPH Gradient Direction

**Root cause:** In `SPHSolver.js:122-124`, `dir = (pj - pi)` = `(j-i)`. Combined with the `acc_i -= forceScale * gradW` application, this produces attraction instead of repulsion.

**Fix:** Change `dir` computation to `(pi - pj)` = `(i-j)`. This makes `gradW` point toward `j`, and the `acc_i -=` application correctly produces repulsion.

## Issue 2: Self-Gravity

**Finding:** Self-gravity is correctly excluded in direct sums (`pj.id === p.id` skip). Barnes-Hut internal nodes have a small residual self-force (~1/theta), which is standard. No fix needed — document as known approximation.

## Issue 3: Circularization/Disk Transition

**3a — Shock heating dead code:** `_shockHeating` is set in `integrateInternalEnergy`, then reset to 0 in `_integrateMatterSPH` cleanup (line 1169), before `_updatePhaseTransitions` reads it (line 670).

**Fix:** Move the `_shockHeating = 0` reset to after `_updatePhaseTransitions` in the substep loop, or pass the shock state via a separate variable.

**3b — Incomplete angular momentum:** `vPhi` computes only Y-component (`dx*vz - dz*vx`). For disks in XY-plane, this is near zero, blocking disk transition.

**Fix:** Use full angular momentum magnitude: `L = sqrt(Lx² + Ly² + Lz²)`, then `vPhi = L / r`.

## Issue 4: 30 FPS Benchmark

**Root cause:** All benchmark assertions use `.toBeGreaterThan(0)`.

**Fix:** Enforce minimum 30 FPS for rendering benchmark. Set realistic floors for physics sub-steps.

## Issue 5: Particle Trail Gaps

**Root cause:** `_updateParticleTrails()` is defined (line 840) but never called from `step()`.

**Fix:** Add `this._updateParticleTrails()` call in `step()` after body trail updates.

## Issue 6: Polytrope Sampling

**Root cause:** `cbrt(random)` gives uniform volume sampling, not density-proportional sampling.

**Fix:** Precompute cumulative mass profile `M(ξ)/M_total` from Lane-Emden solution, sample via inverse CDF.

## Issue 7: Conservation Ledger

**7a — Missing diagnostics:** `totalMomentum` and `totalAngularMomentum` computed but not in `getDiagnostics()` output.

**Fix:** Add `momentum: { linear, angular }` to diagnostics return.

**7b — Escape accounting:** `recordEscape()` never called when particles escape.

**Fix:** Call `this._ledger.recordEscape(p.mass)` in `_classifyBoundParticles()` when marking escaped.
