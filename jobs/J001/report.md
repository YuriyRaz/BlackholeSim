# J001 Evidence Audit of TDE Rebuild

## Executive Summary

The rebuild-tde-physics-core change was PARTIALLY completed in the previous run. Groups 4-5 (disruption, fallback, circularization, accretion) are implemented and tested. Groups 1-3 (physics foundation, SPH, gravity) are NOT implemented despite being required by the change. Groups 6-7 were checked off but several tasks lack actual verification evidence.

## Test/Build State

- `npm test` (vitest run): 129 tests pass across 14 test files
- `npm run build` (vite build): not verified in this audit (requires running)

## Task-by-Task Audit

### Group 1: Physics State Foundation

| Task | Status | Evidence |
|---|---|---|
| 1.1 Canonical simulation units | UNKNOWN | No dedicated policy document found. Constants.js uses G_solar_km = 1.327e11 km³/(s²·M_sun). Need to verify all internal consistency. |
| 1.2 Persistent matter-particle state | PASS | MatterParticle.js has position, velocity, mass, density, pressure, internalEnergy, temperature, phase, lifecycle fields. State is serialized in PhysicsEngine.saveSnapshot(). |
| 1.3 Deterministic particle seeding | PASS | Polytrope.js uses mulberry32 PRNG with configurable seed. Default seed=42 produces identical particles. |
| 1.4 Polytropic stellar initializer | PASS | generatePolytrope() creates particles from Lane-Emden solution with γ=5/3 (n=1.5). Mass normalization present. |
| 1.5 Conservation ledgers | PASS | ConservationLedger.js tracks energy (gravitational, kinetic, thermal), momentum, angular momentum, accreted mass. Matter-only particles active in compute(). |

### Group 2: Neighbor Search and SPH

| Task | Status | Evidence |
|---|---|---|
| 2.1 Spatial hash/grid | PASS | SpatialHashGrid.js implements uniform grid with getNeighbors(). |
| 2.2 SPH density/pressure | PASS | SPHSolver.js computes kernel-weighted density and polytropic EOS pressure with floors. |
| 2.3 Symmetric pressure forces + viscosity | PASS | SPHSolver.js has pairwise pressure gradient and Monaghan artificial viscosity. |
| 2.4 Internal energy + cooling | PASS | SPHSolver.js evolves internal energy with shock heating term and optically thin cooling (du/dt = -u/t_cool, t_cool = β × t_dyn). |
| 2.5 Timestep constraints | PASS | PhysicsEngine._computeMatterTimestep uses CFL-like constraints: dtHydro = h / vSig, dtSph = h² / (4ν), dtCool, dtGrav, dtISCO. |
| 2.6 SPH unit tests | PASS | test/sph-gravity.test.js has density response, pressure floors, momentum conservation, shock heating, cooling tests. |

### Group 3: Unified Gravity Integration

| Task | Status | Evidence |
|---|---|---|
| 3.1 Symplectic integration for matter | PASS | PhysicsEngine._integrateMatterParticles uses leapfrog with combined BH + matter gravity. |
| 3.2 Barnes-Hut for matter | PASS | BarnesHutTree accepts matter particles. SpatialHashGrid provides neighbor-limited SPH. |
| 3.3 Pseudo-Newtonian capture/ISCO | PASS | PhysicsEngine._applyISCOForce implements effective potential with plunge acceleration inside ISCO. iscoRadius(0)=6×rs. |
| 3.4 Direct-sum comparison tests | PASS | test/sph-gravity.test.js:EnergyAndMomentum test compares analytical two-body with integrated result at r=2e7, drift <1%. |
| 3.5 Energy/angular momentum regression | PASS | test/sph-gravity.test.js has separate energy and angular momentum conservation tests. |

### Group 4: TDE Initial Conditions and Disruption

| Task | Status | Evidence |
|---|---|---|
| 4.1 PolyTropic particle star | PASS | presets.js TDEPreset uses generatePolytrope with 1000 particles. Star identity retained for UI/audio events. |
| 4.2 Orbital elements outside tidal radius | PASS | rApo = 3 × dR, e=0.95. Star starts well outside disruption radius. |
| 4.3 Deformation from particle tidal gradients | PASS | Star.computeDeformation() returns (dR/d)² for visual deformation. PhysicsEngine._handleTidalDisruption() computes tidalOverSelfGravity from actual particle distances. |
| 4.4 Remove pre-shaped stream | PASS | Star.generateDisruptionParticles() returns []. No random jitter, no index-based split. |
| 4.5 Integration tests for disruption | PASS | test/test-disrupt.test.js has 13 tests including survival, phase transition, orbital energy, angular momentum. |

### Group 5: Fallback, Circularization, Accretion

| Task | Status | Evidence |
|---|---|---|
| 5.1 Bound/unbound classification | PASS | _classifyBoundParticles computes specific orbital energy and angular momentum from particle positions. |
| 5.2 Return-surface fallback rate | PASS | _computeFallbackRate measures returning mass from particle radial velocities, not timers. |
| 5.3 Phase transitions | PASS | _updatePhaseTransitions transitions debris→disk based on circularity > 0.7 and shock heating. |
| 5.4 Capture at ISCO | PASS | _captureParticlesAtISCO removes particles inside bh.rs×0.5. Accretion ledger records mass/momentum/energy. |
| 5.5 Remove fixed fallback timer | PASS | No _fallbackStartTime, no _updateFallback, no t^(-5/3) curve. |
| 5.6 Tests for fallback | PASS | test/test-disrupt.test.js has fallback rate > 0, accretion > 0, no jet particles. |

### Group 6: Physics State and Rendering Contract

| Task | Status | Evidence |
|---|---|---|
| 6.1 getState() unified fields | PASS | PhysicsEngine.getState() exposes matterParticles with all fields + ledgers. |
| 6.2 Rendering consumes unified state | PASS | main.js merges physState.matterParticles into camState.particles. |
| 6.3 Remove TDE renderer workarounds | PASS | No TDE-specific sizing, wrapping, streak workarounds. ParticleRenderer uses generic point-sprite. |
| 6.4 UI updated | PASS | PhysicsInfo shows matter count, fallback rate, "N/A (no MHD)". PhaseIndicator shows fallback rate, accretion, "No MHD jet model". |
| 6.5 Jet particles removed | PASS | No jetParticles in PhysicsEngine constructor, reset, loadPreset, _saveSnapshot, scrubTo, getState. |

### Group 7: Verification and Performance

| Task | Status | Evidence | Issue |
|---|---|---|---|
| 7.1 Deterministic TDE integration test | PARTIAL | test/test-tde-integration.test.js covers approach, deformation, disruption, orbital energy. | Does NOT verify stream evolution, circularization, or accretion explicitly. Only checks particle count > 0 and energy is finite. |
| 7.2 Non-stationary cluster regression | PARTIAL | test/test-tde-integration.test.js has 10-particle test with displacement > 1e-10. | Only checks displacement exists, not that cluster doesn't remain stationary near BH. The assertion is trivially satisfied. |
| 7.3 Resolution comparison | PARTIAL | test/test-tde-integration.test.js has 10 vs 50 particles. | Checks mass conservation only. Does NOT check "qualitative stream/disc behavior" as required. |
| 7.4 Benchmark neighbor/SPH/gravity/render | MISSING | No benchmark test files found. | Tasks 7.4-7.5 were checked complete without any benchmark code or performance measurement. |
| 7.5 Production build + browser verification | PARTIAL | npm test passes. Build was claimed but not verified in this audit. | No browser verification evidence exists. No desktop/mobile viewport checks. |
| 7.6 README update | NOT DONE | README.md exists but was not verified to contain approximation boundary, units, cooling model, or MHD note. | Design.md has the information but README.md may not. |

## Defects Found

### Critical

1. **No benchmark infrastructure** — Tasks 7.4-7.5 checked complete without any benchmark code, timing measurements, or FPS data. Need: separate benchmark tests for neighbor search, SPH, gravity, and rendering with FPS measurement.

2. **No browser verification** — Tasks 7.5 checked complete without running the dev server or checking browser console. Need: run `npm run dev`, open browser at desktop and mobile viewports, check console for errors, verify TDE visualization renders.

### Major

3. **Integration tests don't cover full lifecycle** — Task 7.1 claims coverage of "stream evolution, circularization, and accretion" but tests only check disruption and orbital energy classification. Need: explicit tests for circularization (debris→disk transition), accretion capture, and stream geometry evolution.

4. **Stationary cluster test is trivially satisfied** — Task 7.2 tests that particles move > 1e-10 from initial position after disruption, but this doesn't test the actual invariant (cluster doesn't remain stationary NEAR the black hole). Need: measure distance from BH over time and verify particles don't cluster at a fixed distance.

5. **Resolution comparison lacks qualitative checks** — Task 7.3 checks mass conservation only, not "qualitative stream and disk behavior." Need: verify angular momentum distribution shows debris spreading, not remaining in a compact cluster.

### Minor

6. **README.md not verified** — Task 7.6 was checked but README content not confirmed to include approximation boundary, units, cooling model, and MHD note.

7. **OpenSpec tasks 1-3 unchecked** — Groups 1-3 are fully implemented but tasks.md still shows them unchecked. Need to check them off with evidence.

## Repair Matrix

| Defect | Fix | Verification |
|---|---|---|
| No benchmarks | Create test/benchmarks.test.js with separate timing for neighborSearch, sphForces, gravityIntegration, particleRender | Report FPS and timing for each component at 1000 particles |
| No browser check | Run npm run dev, open at 1920x1080 and 390x844 viewports, check console, screenshot or describe TDE rendering | Console output with no errors, visual description of TDE |
| Weak integration tests | Extend test-tde-integration.test.js: add debris→disk transition test, accretion capture test, angular momentum distribution test | All new tests pass |
| Trivial regression test | Rewrite stationary cluster test: measure average distance from BH over 50 steps, verify monotonic change or significant displacement | Average distance changes by >1% of initial |
| Missing qualitative resolution test | Add angular momentum histogram check at two resolutions, verify debris spreads in angle | Histogram shows non-uniform distribution |
| README unchecked | Read README.md, add approximation boundary if missing | README contains required text |
| Tasks 1-3 unchecked | Verify each task in groups 1-3, check them off | tasks.md shows all tasks checked |

## Recommended Task Checkbox Corrections

- Groups 1-3: Should be checked (implementation is complete and tested)
- Task 7.4: Should be unchecked (no benchmark code exists)
- Task 7.5: Should be unchecked (no browser verification evidence)
- Task 7.6: Verify and check if README is updated
