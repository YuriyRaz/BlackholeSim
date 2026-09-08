# Fix TDE Physics Critical Issues

## Summary

Fix 7 critical physics issues identified during verification of the `rebuild-tde-physics-core` change. These bugs affect SPH fluid behavior, disk formation, performance benchmarks, particle trails, stellar initialization, and conservation accounting.

## Issues

1. **SPH gradient direction reversed** — `gradWCubicSpline` uses `(j-i)` direction causing pressure forces to attract instead of repel
2. **Self-gravity residual** — Barnes-Hut internal nodes include queried particle's mass (standard approximation, documented)
3. **Circularization/disk transition** — shock heating state reset before phase transition reads it; circularity uses only Y-component of angular momentum
4. **30 FPS benchmark not enforced** — `test/benchmarks.test.js` only requires throughput > 0
5. **Matter trail gaps** — `_updateParticleTrails` defined but never called from `step()`
6. **Polytrope sampling** — `cbrt(random)` uniform volume sampling doesn't match Lane-Emden density profile
7. **Conservation ledger gaps** — momentum/angular momentum omitted from diagnostics; `recordEscape` never invoked

## Approach

Minimal, focused fixes per issue. Each fix is isolated and testable independently.
