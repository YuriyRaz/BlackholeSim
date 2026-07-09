## Why

Proposals 1-2 deliver a renderer and a physics engine. The physics engine simulates gravity, gas dynamics, tidal forces, GW emission, accretion, and jets. But some visual effects need shader work that goes beyond basic particle rendering: gravitational wave ripples distorting the background, a bright flash when two black holes merge, particle trails showing trajectories, and the phase indicator that tells the user what's happening.

This proposal adds those visual effects. None of them are scenario-specific. GW ripples appear whenever the physics engine reports nonzero GW strain. The merger flash appears when two BHs are close. Particle trails show the history of any particle. The phase indicator reads the physics state and derives what phase the system is in. Everything is driven by the physics, not by scenario classes.

## What Changes

- **GW ripple visualization**: Concentric distortion rings in the lensing shader, driven by gwStrain from the physics engine.
- **Merger flash**: Bright bloom effect when two black holes are within 5×Rs, driven by BH proximity.
- **Particle trails**: Fading trail lines for any particle type, reading history from physics engine.
- **Phase indicator**: UI element that derives phase from physics state (separation, accretion rate, GW strain).
- **Timeline scrubber enhancement**: Full timeline control with snapshot caching.

## Dependencies

- **physics-engine-02**: Requires `bhPairs` array in `getState()` output (DESIGN.md §7.3 defines it; implementation must add it). `bhPairs` provides `[{ a: index, b: index, distance: float }]` for all black hole pairs.
- **physics-engine-02**: Requires particle trail history buffer (new array `particleTrails` storing last N positions per particle, exposed in `getState()`).
- **core-renderer-01**: Existing `LensingPass`, `PostProcessor`, `TrailRenderer`, `ParticleRenderer` are extended.

## Capabilities

### New Capabilities

- `gw-visualization`: Gravitational wave ripple distortion shader. Driven by gwStrain from physics engine.
- `merger-flash`: Bloom effect when BHs are close. Driven by BH separation distance via `bhPairs`.
- `particle-trails`: Fading trail lines for any particle type. Reads history buffer from physics engine.
- `phase-indicator`: UI element that derives phase from physics state. No hardcoded transitions.

### Modified Capabilities

- `gravitational-lensing`: Add GW ripple distortion pass to lensing shader.
- `ui-shell`: Add phase indicator, particle trails toggle, GW ripples toggle, jet rendering toggle.
- `timeline-controls`: Add snapshot cache for scrubbing through simulation history.

## Impact

- **Extends core-renderer-01 and physics-engine-02**: Visual effects read from physics state.
- **New modules**: ~5 JavaScript modules (shaders/, ui/ additions).
- **No scenario classes**: All effects emerge from physics state.
- **Performance**: GW ripple adds ~1ms per frame. Merger flash is bloom spike. Trails add ~0.5ms.
- **WebGPU**: GW ripple shader and particle trail renderer are GL-only for MVP; WebGPU paths noted as follow-up.
