# Review: rebuild-tde-physics-core Proposal

## Current TDE State (Faked Mechanics)

### PhysicsEngine.js
| Method | Lines | Problem |
|---|---|---|
| `_handleTidalDisruption()` | 658-707 | One-body `d < dR` check; calls `Star.generateDisruptionParticles()` which fakes a pre-shaped stream; splits 80% gas / 20% debris by `i % 5` index; sets a fixed `_fallbackStartTime` |
| `_computeFallbackRate()` | 143-155 | Hardcoded `T_fallback = 10.0` with `t^(-5/3)`, not derived from particles |
| `_computeAccretion()` | 570-604 | ISCO check for gas, then `_emitJetParticles()` with spin² probability — synthetic jet |
| `_integrateGas()` | 424-535 | Gas responds to BH gravity only (no self-gravity, no SPH); `T = v² × 1e4` |
| `_applyViscousTransport()` | 537-568 | Ad-hoc viscous model, not physical SPH transport |

### Star.js
- `generateDisruptionParticles()` (L38-99): Constructs a hand-shaped stream with radial/tangent/normal coordinates, wraps particles around BH in a crafted arc, applies random jitter. No physical basis.
- `computeDeformation()` (L126-135): Returns scalar `(dR/d)²` — a visual value, not actual particle deformation.

### presets.js — TDEPreset()
- Line 30: `startDistance = dR * 0.82` — **star starts inside the tidal radius**. The encounter is already past disruption from frame zero.

### Constants.js
- `tidalDisruptionRadius()` (L40-42): Correct formula (`R_star * R_sun_km * (M_bh / M_star)^(1/3)`).

## Proposal Assessment

### ✅ What the proposal gets right

1. **Correctly identifies the core problem**: TDE is a pre-scripted visual effect, not emergent from physics. This violates GREAT_GOAL.md rule #2.
2. **D1 (unified particle state)** cleanly replaces the three-way split (bodies/gasParticles/jetParticles) that enables non-physical state transitions.
3. **D2 (SPH)** is the correct method for a deforming, shocking, circularizing fluid in a sparse particle representation.
4. **D3 (polytropic star)** correctly identifies that uniform random points + random noise is not a star.
5. **D5 (event-driven fallback/disk/accretion)** correctly removes the fixed `t^(-5/3)` driver and synthetic disk injection.
6. **D6 (no synthetic jets)** is honest — probability-based jet emission has no physical basis.
7. **D7 (independent testability)** fixes the root cause of the previous failure (state generation diagnosed visually).
8. **Delta specs** (all 7 files under `specs/`) correctly modify the problematic main specs and remove the non-physical accretion-jet requirements.

### ⚠️ Issues found

#### Issue 1: TDEPreset starts inside the tidal radius — blocks initial conditions
- Preset line 30: `startDistance = dR * 0.82`
- Proposal D3 and delta `initial-presets` require: star outside tidal radius, eccentric orbit with periapsis inside dR.
- **Severity**: Implementation-blocking. The first physical particle star would immediately be "inside" the disruption check.
- **Fix**: The preset must place the star at ≥ 2–3 × dR with orbital elements that yield periapsis < dR.

#### Issue 2: Polytropic star parameters are underspecified
- Design D3 says "bounded polytropic density profile" but doesn't specify index (γ = 5/3? 4/3?), central density, or the equation of state for the SPH solver.
- **Severity**: Medium. Without this, implementers cannot build the star initializer (task 1.4). Risk: star "explodes" numerically before reaching the BH.
- **Fix**: Specify the polytropic index and reference the analytic density profile. Add a relaxation or acceptance criterion for hydrostatic equilibrium.

#### Issue 3: Cooling is an open question but circularization depends on it
- Design line 107: "Which cooling approximation is sufficient to let debris circularize without artificially destroying energy conservation?" — listed as open question.
- SPH without cooling will thermalize orbital energy; shocked debris stays hot and puffy and will not form a thin disk.
- **Severity**: Medium. The proposal needs to decide: first milestone targets a thick torus (no cooling required), or a simple optically thin cooling law (e.g., `du/dt = -u / t_cool`) must be specified.
- **Fix**: Declare the first-milestone cooling approach explicitly, even if it's a simple placeholder.

#### Issue 4: GasParticle.js has no SPH fields — breaking change
- Current `GasParticle` has: position, velocity, mass, temperature, accreted, age.
- Proposal requires: density, pressure, internal energy, phase, lifecycle fields.
- **Severity**: Information (covered by tasks 1.1–1.2). Noted for migration: Kerr preset also uses `GasParticle` and must be migrated to the new unified particle.

#### Issue 5: Renderer TDE workarounds not yet inventoried
- Task 6.3 says "Remove TDE-specific renderer sizing, wrapping, streak, and cluster workarounds" but the current renderer code hasn't been audited.
- **Severity**: Low (task exists), but the implementation should inventory these before phase 4.

#### Issue 6: Headless visual test infrastructure unclear
- Task 7.1: "Add a deterministic headless TDE integration test" in a WebGL/WebGPU JS app.
- **Severity**: Low (project may use headless-gl or puppeteer; not blocking).

### ✅ Verdict

**The proposal is ready for implementation** with the following prerequisites:

1. Resolve Issue 1 (TDEPreset start distance — MUST fix before task 4.1 can work)
2. Resolve Issue 2 (polytropic star parameters — MUST specify before tasks 1.3–1.4)
3. Resolve Issue 3 (cooling approach — SHOULD decide before task 2.4)
4. Issues 4–6 are normal implementation details for the task list.

The delta specs are consistent with the proposal. No architectural contradiction with GREAT_GOAL.md. The change does not introduce new faked behavior.

### Recommended follow-up before implementation

- Architect should specify the polytropic star parameters (γ, central density, mass resolution formula) and the first-milestone cooling model.
- Architect or implementer should adjust TDEPreset orbital elements to start outside dR.

## Files Examined

| File | Role |
|---|---|
| `src/physics/PhysicsEngine.js` | Main engine: TDE + gas + accretion + jets |
| `src/objects/Star.js` | Star body: generates fake stream on disruption |
| `src/objects/GasParticle.js` | Passive gas tracer (no SPH fields) |
| `src/core/Constants.js` | Physical constants and TDE radius formula |
| `src/presets/presets.js` | TDEPreset: starts inside tidal radius |
| `openspec/specs/tidal-disruption/spec.md` | Main spec (has old non-physical requirements) |
| `openspec/specs/gravity-solver/spec.md` | Main gravity spec |
| `openspec/specs/gas-dynamics/spec.md` | Main gas spec (passive tracers) |
| `openspec/specs/accretion-physics/spec.md` | Main accretion spec (has jet emission) |
| `openspec/changes/rebuild-tde-physics-core/proposal.md` | Reviewed proposal |
| `openspec/changes/rebuild-tde-physics-core/design.md` | Design decisions D1–D7 |
| `openspec/changes/rebuild-tde-physics-core/tasks.md` | Implementation tasks (7 groups) |
| `openspec/changes/rebuild-tde-physics-core/specs/*.md` | 7 delta specs (added/modified/removed) |
