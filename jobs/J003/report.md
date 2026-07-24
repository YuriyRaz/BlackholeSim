# J003 Independent Verification: TDE Physics Rebuild

## Executive Summary

The TDE physics rebuild has **critical test failures** that prevent release. 5 of 136 tests fail due to timeouts, the benchmark infrastructure is non-functional, and the tidal-disruption spec still contains stale fake-physics requirements that contradict the implementation. The core physics code (PhysicsEngine.js, Star.js) is clean of fake-physics artifacts, but the test suite is not viable.

## Test/Build State

**`npm test` output (157s):**
```
Test Files  3 failed | 12 passed (15)
     Tests  5 failed | 131 passed (136)
```

**`npm run build`:** PASS (vite build, 55 modules, 1.47s)

**Git status:** Uncommitted changes from J001/J002 repairs (README.md, tasks.md, test files, benchmarks.test.js)

## Findings (Severity-Ordered)

### 1. CRITICAL: TDE Integration Tests Timeout

**File:** `test/test-tde-integration.test.js:54,118,164`

Three TDE integration tests fail with timeout errors. The tests specify insufficient timeouts for the computational load of the physics simulation.

- **Line 54** (`TDE preset runs headlessly without errors`): 30s timeout, runs 2 steps with 1000 particles. Times out.
- **Line 118** (`low and high resolution both conserve mass`): No custom timeout (defaults to 5s). Runs 20 steps with 50 particles. Times out.
- **Line 164** (`angular momentum distribution shows debris spreading`): No custom timeout (defaults to 5s). Runs 30 steps with 50 particles. Times out.

**Evidence:**
```
FAIL  test/test-tde-integration.test.js > Task 7.1: Deterministic headless TDE integration test > TDE preset runs headlessly without errors
Error: Test timed out in 30000ms.

FAIL  test/test-tde-integration.test.js > Task 7.3: Resolution comparison tests > low and high resolution both conserve mass
Error: Test timed out in 5000ms.

FAIL  test/test-tde-integration.test.js > Task 7.3: Resolution comparison tests > angular momentum distribution shows debris spreading
Error: Test timed out in 5000ms.
```

**Impact:** Tasks 7.1, 7.3 verification claims cannot be validated. The TDE lifecycle test (line 9) passes, but the headless preset test and resolution comparison tests are broken.

### 2. CRITICAL: Benchmark Infrastructure Non-Functional

**File:** `test/benchmarks.test.js:30`

The benchmark test creates 1000 particles and times neighbor search, but the SpatialHashGrid query is extremely slow. The neighbor search alone takes ~95s for 10 iterations, exceeding the 60s timeout.

**Evidence:**
```
FAIL  test/benchmarks.test.js > Benchmarks > neighbor search throughput
Error: Test timed out in 60000ms.
stdout: Neighbor search: 94623.90ms for 10 iterations, 106 queries/sec
```

**Impact:** Task 7.4 (benchmark neighbor search, SPH, gravity, rendering) cannot be validated. The benchmark infrastructure J002 created is non-functional at the target particle count of 1000.

### 3. MAJOR: Stale Fake-Physics Requirements in Spec

**File:** `openspec/specs/tidal-disruption/spec.md:28,58`

The tidal-disruption spec still contains requirements that contradict the rebuilt implementation:

1. **Line 28**: Specifies random velocity perturbation (`±10% of orbital velocity`) for particle creation — this was explicitly removed by task 4.4 ("Remove post-disruption stream generation, random velocity jitter"). The actual implementation uses `generatePolytrope()` with deterministic mulberry32 PRNG.

2. **Line 58**: Specifies `dM/dt ∝ (t / T_fallback)^(-5/3)` power-law fallback rate — this was explicitly removed by task 5.5 ("Remove the fixed fallback timer, injected fallback curve"). The actual implementation computes fallback rate from measured returning mass via `_computeFallbackRate()`.

3. **Line 28**: Specifies particle count `N = clamp(floor(star.mass / (0.1 × M_sun)), 50, 500)` with rejection sampling — the actual implementation uses polytropic stellar initializer (task 1.4).

**Impact:** The spec describes the old fake-physics model. Anyone reading the spec will expect behavior that does not match the implementation.

### 4. MAJOR: Binary Black Hole Test Timeout

**File:** `test/physics.test.js:85`

The binary BH merger test times out at 5s (default timeout). This is a pre-existing test, not part of the TDE rebuild, but it indicates the test suite has systemic timeout issues.

**Evidence:**
```
FAIL  test/physics.test.js > PhysicsEngine > should inspiral and merge the binary black hole preset
Error: Test timed out in 5000ms.
```

**Impact:** Not directly TDE-related, but indicates the test suite needs timeout tuning across the board.

### 5. MINOR: Benchmark Uses Math.random() in Particle Setup

**File:** `test/benchmarks.test.js:14,16`

The `createParticleRing()` function uses `Math.random()` for particle radius variation and Z-axis offset. While this is acceptable in a benchmark helper (not physics code), it means benchmark results are not deterministic across runs.

**Evidence:**
```js
const r = radius * (0.8 + 0.4 * Math.random());  // line 14
position: [..., (Math.random() - 0.5) * radius * 0.1],  // line 16
```

**Impact:** Minor. Benchmark measures throughput, not correctness. Non-determinism in setup is acceptable.

### 6. MINOR: `_fallbackStartTime` Field Name Potentially Confusing

**File:** `src/physics/PhysicsEngine.js:31,195-196`

The field `_fallbackStartTime` was flagged by J001 as a potential leftover from the timer-driven fallback. Inspection confirms it is used ONLY as a timestamp to record when the first fallback event occurs (line 195-196), not as a timer input to any `t^(-5/3)` curve. The field is correctly used — it's just named in a way that could cause confusion during audits.

**Evidence:** Line 195: `if (returningCount > 0 && this._fallbackStartTime < 0)` — this is a one-time flag, not a timer.

**Impact:** None functionally. Naming is slightly misleading for audit purposes.

## Verification Checklist

| Item | Status | Evidence |
|---|---|---|
| `npm test` runs | PARTIAL | 131/136 pass, 5 timeout failures |
| Lifecycle tests test temporal progression | PASS | `test-tde-integration.test.js:9-51` tests stellar→debris phase transition |
| Benchmark has separate timing | FAIL | Benchmark times out; can't validate |
| README states units, potential, cooling, MHD, performance | PASS | `README.md:46-53` has all required content |
| All tasks 1.1-7.6 checked | PASS | `tasks.md` shows all tasks checked |
| No stale fake-physics in spec | FAIL | `spec.md:28,58` has stale random-jitter and t^-5/3 requirements |
| No Math.random() in physics/objects | PASS | Grep returns zero matches in `src/physics/` and `src/objects/` |
| No jet references in physics/objects | PASS | Grep returns zero matches in `src/physics/` and `src/objects/` |
| No timer-driven physics | PASS | `_fallbackStartTime` is a timestamp, not a timer input |
| PhysicsInfo handles matter particles | PASS | `PhysicsInfo.js:39-42` shows matter count; line 16 shows "N/A (no MHD)" |
| PhaseIndicator handles matter particles | PASS | `PhaseIndicator.js:55` checks matterParticles for quiescent; line 58 shows "No MHD jet model" |
| main.js renders matterParticles | PASS | `main.js:152-161` maps matterParticles into camState.particles |
| main.js trails include matter particles | PASS | `PhysicsEngine.js:852-862` updates matter particle trails |
| git status clean | NO | Uncommitted changes from J001/J002 |
| build script exists | PASS | `package.json:8` has `"build": "vite build"` |
| `npm run build` succeeds | PASS | Built in 1.47s, 153KB JS bundle |

## Release-Readiness Verdict

**NOT READY FOR RELEASE.**

Two critical issues block release:
1. **5 test failures** — The TDE integration tests and benchmark are non-functional due to timeouts. The test suite cannot be relied upon for regression detection.
2. **Stale spec requirements** — The tidal-disruption spec describes fake-physics behavior that was explicitly removed. This creates a contract mismatch between documentation and implementation.

**Required fixes before release:**
1. Increase test timeouts or reduce particle counts in failing tests to bring them within 30s bounds
2. Fix the benchmark test to use a manageable particle count or increase the timeout
3. Update `openspec/specs/tidal-disruption/spec.md` to remove stale random-jitter, t^(-5/3), and rejection-sampling requirements
4. Optionally: rename `_fallbackStartTime` to `_firstFallbackRecordedTime` for audit clarity

## Summary of Clean Areas

The core physics rebuild IS correct:
- `PhysicsEngine.js`: No Math.random(), no jet references, no timer-driven physics, clean SPH/gravity/disruption/accretion pipeline
- `Star.js`: Clean, uses polytrope, `generateDisruptionParticles()` returns `[]`
- `MatterParticle.js`: Proper state fields (position, velocity, mass, density, pressure, internalEnergy, temperature, phase, lifecycle)
- `README.md`: Accurately describes units, pseudo-Newtonian potential, ISCO, cooling, MHD absence, performance target
- `tasks.md`: All 35 tasks (1.1-7.6) properly checked off
- UI components (`PhysicsInfo.js`, `PhaseIndicator.js`): Correctly handle matter particles and MHD absence
- `main.js`: Properly renders matter particles and includes them in trails
