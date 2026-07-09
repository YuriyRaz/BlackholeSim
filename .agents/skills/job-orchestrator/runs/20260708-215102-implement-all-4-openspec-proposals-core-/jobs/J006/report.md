# J006 Correction Report: Physics Engine Architecture Review

## Status: completed

## Scope

Correction pass for all issues identified in the architecture review of the `physics-engine-02` implementation.

## Issues Fixed

### Critical Issues (3/3 fixed)

#### C1: GW Energy Loss Dimensional Error — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 514-582)

**Before**: Position displacement with arbitrary `0.0001` factor:
```js
const decayAccel = daDt * 0.0001;
bi.position[0] += rVec[0] * decayAccel;
```

**After**: Velocity kick derived from luminosity:
```js
const dvDt = luminosity / (MKg * v_bi);
bi.velocity[0] += (dx / r) * dvDt * subDt;
```

Energy loss is now applied as a velocity perturbation scaled by the luminosity, orbital mass, velocity, and timestep. The `daDt` variable was removed entirely — luminosity is used directly.

---

#### C2: GW Phase Hardcoded Timestep — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 111, 514, 572)

**Before**: `this.gwPhase += maxFreq * 0.016;`

**After**: `_computeGravitationalWaves(subDt)` now accepts `subDt` parameter; phase uses `this.gwPhase += maxFreq * subDt;`

Phase accumulation is now frame-rate independent.

---

#### C3: Fallback Rate Double-Counting — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 129-143)

**Before**: `this.accretionRate += this._fallbackRate;`

**After**: Removed. The `_fallbackRate` is still computed for display purposes, but no longer added to `accretionRate`. The accretion window in `_computeAccretion()` naturally captures fallback mass accretion.

---

### Moderate Issues (5/5 fixed)

#### M1: Viscous Transport Tangential Vector — FIXED
**File**: `src/physics/PhysicsEngine.js` (line 368)

**Before**: `const tangential = [-dy / r, dx / r, 0];`

**After**: Normalized tangential vector computed from radial direction:
```js
const rVec = [dx / r, dy / r, dz / r];
const tangential = [-rVec[1], rVec[0], 0];
const tLen = Math.sqrt(tangential[0] ** 2 + tangential[1] ** 2 + tangential[2] ** 2);
if (tLen > 0.001) { tangential[0] /= tLen; tangential[1] /= tLen; tangential[2] /= tLen; }
```

The tangential vector is now properly normalized.

---

#### M2: Ergosphere Velocity Override — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 275-289)

**Before**: Direct velocity overwrite `gp.velocity = [perp/speed * speed]`

**After**: Perturbative acceleration correction:
```js
ax += ergoStrength * (targetVel[0] - gp.velocity[0]) / dt;
```

The ergosphere now applies a continuous force that steers velocity toward the frame-dragging direction, preserving symplectic integration.

---

#### M4: BlackHoles Filter Repeatedly Allocated — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 107, 247, 356, 379, 453, 467)

**Before**: Five separate `this.bodies.filter(b => b.type === 'blackhole')` calls per substep.

**After**: Cached once per step in `step()`: `this._blackHoles = this.bodies.filter(b => b.type === 'blackhole');`. All five methods now reference `this._blackHoles`. Also added to `scrubTo()`.

---

#### M5: Snapshot Scrubbing Missing Jet/GW State — FIXED
**File**: `src/physics/PhysicsEngine.js` (lines 584-650)

**Before**: `_saveSnapshot()` only saved bodies and gas. `scrubTo()` only restored bodies and re-ran gas integration.

**After**: 
- `_saveSnapshot()` now includes `jets`, `gw`, `accretionRate`, `fallbackRate`, `fallbackStartTime`, `fallbackMass`
- `scrubTo()` now restores jet particles, GW state (frequency, strain, phase, luminosity), and accretion/fallback state from the snapshot before re-running integration

---

#### M6: No Barnes-Hut Tests — FIXED
**File**: `test/barnes-hut.test.js` (new file, 12 tests)

Added comprehensive unit tests covering:
- Empty body handling
- Single and multi-body tree construction
- Center-of-mass computation (equal and unequal masses)
- Gravitational acceleration correctness
- Theta-criterion opening
- Tree rebuild after position changes
- Large body count handling

---

## Verification

- **Build**: `npm run build` passes (vite build, 38 modules, 514ms)
- **Tests**: All 51 tests pass (4 test files: physics, objects, constants, barnes-hut)
- **Test count**: 12 new Barnes-Hut tests added

## Remaining Minor Issues (not fixed, low severity)

- **m1**: Gas temperature heuristic (cosmetic, `v2 * 1e4`)
- **m2**: Jet particle wobble uses unseeded `Math.random()`
- **m4**: Tidal disruption pushes to `this.bodies` during iteration (benign)
- **m5**: Body ID counter is module-level global

## Positive Observations (unchanged from review)

1. Velocity Verlet integrator correctly structured for position-dependent forces
2. Softening parameter consistently applied
3. Barnes-Hut tree correctly implements 3D octree with theta-criterion
4. ISCO and ergosphere follow standard Kerr metric formulas
5. Snapshot system provides timeline scrubbing with FIFO eviction

---

## Artifacts
- `src/physics/PhysicsEngine.js` — primary file corrected (720 lines)
- `src/physics/BarnesHut.js` — unchanged (141 lines)
- `test/barnes-hut.test.js` — new test file (12 tests)
- `test/physics.test.js` — existing tests (10 tests)
