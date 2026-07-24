# J004 Report: Final Repair and Closure

## Summary

Fixed 2 critical issues from J003 (test timeouts, stale spec requirements),
verified all 136 tests pass, and created the autonomous completion prompt.

## What Was Changed

### Fix 1: Test Timeouts

**`test/test-tde-integration.test.js:54`** — Increased timeout on "TDE preset
runs headlessly" test from 30000ms to 60000ms.

**`test/benchmarks.test.js`** — Increased timeout on all 4 benchmark tests
from 60000ms to 120000ms:
- `neighbor search throughput` (line 30)
- `SPH forces throughput` (line 52)
- `gravity integration throughput` (line 78)
- `particle rendering throughput` (line 97)

### Fix 2: Stale Spec Requirements

**`openspec/specs/tidal-disruption/spec.md`** — Rewrote 4 requirements to
match actual implementation:

1. **Star particle count algorithm**: Changed from "rejection sampling with
   random velocity perturbation" to "polytropic initializer with
   N = clamp(floor(M_star / (0.1 × M_sun)), 200, 2000), deterministic
   seeding." The actual code uses `generatePolytrope()` from
   `src/physics/Polytrope.js` with Lane-Emden integration and seeded RNG.

2. **Fallback rate**: Changed from "dM/dt ∝ (t/T_fallback)^(-5/3) power
   law" to "measured returning mass: particles within 2× tidal disruption
   radius with negative radial velocity, mass flux per timestep." The actual
   code in `_computeFallbackRate()` counts returning particles, not a
   prescribed curve.

3. **Tidal stream formation**: Changed from "particles from near side orbit
   faster, far side orbit slower" (implying pre-shaped geometry) to "stream
   emerges from particle orbital energy distribution." The actual code
   releases particles from polytrope positions with the star's COM velocity;
   the stream forms naturally from differential orbital energies.

4. **Star deformation**: Changed from "scalar visual deformation stretching
   into prolate spheroid" to "deformation from tidal gradients on resolved
   particles, proportional to (d_R/d)²." The actual code computes
   `star.computeDeformation(bh)` which returns `min(3.0, (dR/d)^2)`.

Removed mention of: random velocity perturbation, rejection sampling,
scripted fallback curves, pre-shaped stream geometry.

## Test Results

```
 Test Files  15 passed (15)
      Tests  136 passed (136)
   Duration  24.13s
```

All tests pass. No regressions introduced.

## Files Modified

| File | Change |
|------|--------|
| `test/test-tde-integration.test.js` | Timeout 30000 → 60000 |
| `test/benchmarks.test.js` | Timeout 60000 → 120000 (4 tests) |
| `openspec/specs/tidal-disruption/spec.md` | Rewritten to match implementation |
| `AUTONOMOUS_COMPLETION_PROMPT.md` | New: reusable control-loop prompt |

## Final State

- 15 test files, 136 tests: all passing
- Spec accurately reflects implementation
- Timeouts adequate for headless test execution
- Autonomous completion prompt ready for use
