# J005 Report: Cross-cutting Architecture Review + Iteration 2 Plan

## GREAT_GOAL Compliance Audit

### Faked Mechanics Removal — CONFIRMED COMPLETE

| Category | Status | Evidence |
|---|---|---|
| Pre-shaped stream | ✅ Removed | `Star.generateDisruptionParticles()` returns `[]`; no stream geometry code |
| Index-based gas/debris split | ✅ Removed | Phase transitions based on orbital energy, circularity, and shock heating |
| Random jet emission | ✅ Removed | `jetParticles` infrastructure deleted from PhysicsEngine; `_emitJetParticles` deleted |
| Fallback timer | ✅ Removed | `_computeFallbackRate()` derives rate from particle radial velocities |
| Scripted phase transitions | ✅ Removed | Transitions driven by circularity ratio and shock heating, not timers |
| Math.random() in physics | ✅ Clean | Only `presets.js` uses it for initial condition sampling (standard practice) |

### Dead Code Cleanup (found and fixed during review)

1. **Star.js** — Removed `pulsationFreq`, `pulsationPhase` (`Math.random()` init) and unused `updatePulsation()` method
2. **Constants.js** — Removed 7 dead constants: `jetMaxParticles`, `jetMaxDistance`, `gasMinRadius`, `minStarParticles`, `maxStarParticles`, `starParticleMassFraction`, `pseudoNewtonian`
3. **PhysicsEngine._updateParticleTrails()** — Fixed: now iterates over `matterParticles` in addition to `gasParticles`

## Compatibility Verification

### visual-effects-03 — COMPATIBLE (with fixes applied)

| Feature | Status | Notes |
|---|---|---|
| Phase indicator | ✅ Works | Shows disruption, fallback rate, accretion; "No MHD jet model" note added |
| Particle trails | ⚠️ Fixed | `_updateParticleTrails()` now includes matter particles |
| Gravitational waves | ✅ Works | `getState().gw` still exposed correctly |
| GW ripples rendering | ✅ Works | `main.js` passes `physState.gw` to `camState.gw` |

### audio-polish-04 — COMPATIBLE

| Feature | Status | Notes |
|---|---|---|
| Event sounds | ✅ Works | Triggers on `body.disrupted`, `accretionRate` — both still in `getState()` |
| Spatial audio | ✅ Works | HRTF panner per body, uses `bhPairs` distance — still in `getState()` |
| Spacetime hum | ✅ Works | Uses BH mass, no TDE-specific dependencies |
| GW sound | ✅ Works | Uses `gw.frequency`, `gw.strain` — still in `getState()` |
| Jet audio | N/A | No jet-specific audio code exists in `src/audio/` |

## Remaining Non-Physical Behaviors

**None active.** All issues found were dead code, now cleaned up.

## Iteration 2 Plan

### Priority 1: TDE Fallback Rate Diagnostic Validation
The fallback rate is computed from particle radial velocities. Run a TDE simulation and compare the measured `fallbackRate` against the theoretical `t^(-5/3)` power law. If the measured rate doesn't approach the theoretical curve, investigate whether the fallback detection radius or time accounting needs adjustment.

### Priority 2: Accretion Physics Enhancement
Currently `_captureParticlesAtISCO` removes particles below `bh.rs * 0.5`. This is a coarse capture condition. For educational value, consider:
- Adding energy dissipation before capture (particles spiral in rather than teleport)
- Tracking accretion luminosity from the accretion ledger
- Making the capture radius configurable and labeled in the UI

### Priority 3: Disk Formation Visibility
The `debris → disk` phase transition based on circularity > 0.7 may happen too slowly at 1000 particles. Consider:
- Tuning the SPH viscosity to allow faster circularization
- Adding a diagnostic that tracks the fraction of debris in circular orbits
- Visualizing the accretion disk as a distinct particle color when disk phase is reached

### Priority 4: Star Self-Gravity
Currently only BH gravity acts on matter particles. For educational completeness, consider:
- Adding self-gravity between matter particles (within SPH neighbor set)
- This would show tidal deformation before disruption more clearly
- Trade-off: O(N^2) within neighbor set, bounded by spatial hashing

### Priority 5: Snapshot/Replay for TDE
The existing snapshot system captures `bodies` and `gasParticles`. It should be extended to capture `matterParticles` state for TDE replay and time-scrubbing.

### Deferred
- Full GR geodesics (not needed for educational milestone)
- MHD jet model (requires separate proposal)
- Radiation transport (out of scope)
- Moving BH with recoil (conservation milestone)
