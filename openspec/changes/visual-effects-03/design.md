## Context

Extends core-renderer-01 and physics-engine-02. The renderer draws particles, the physics engine computes positions. This proposal adds visual effects that emerge from the physics state — GW ripples, merger flash, particle trails, and phase indicator.

Key constraint: No scenario-specific code. All effects are triggered by physics state (gwStrain, BH separation, accretion rate, body disruption status).

## Goals / Non-Goals

**Goals:**
- GW ripple distortion driven by gwStrain from physics
- Merger flash driven by BH proximity
- Particle trails for any particle type
- Phase indicator derived from physics state
- Timeline scrubber with snapshot caching

**Non-Goals:**
- Scenario classes or state machines — presets are in Proposal 2
- Particle physics — managed by physics engine
- Audio — Proposal 4

## Decisions

### D1: GW Ripples as Lensing Shader Extension

**Decision**: Add GW ripple distortion as a pass in the existing lensing shader, not as a separate post-process.

**Why**: The lensing shader already ray-marches through spacetime. Adding GW distortion to the ray direction is natural and efficient — no extra render pass needed.

**Implementation**: Add uniforms for gwSourcePosition, gwFrequency, gwStrain. During ray-march, add sinusoidal deflection proportional to strain and inversely proportional to distance from source.

### D2: Merger Flash as Bloom Spike

**Decision**: Implement merger flash as a temporary bloom intensity increase, not as additional geometry or particles.

**Why**: A bloom spike is the simplest and most visually effective way to represent the energy release. No new geometry needed — just modulate the existing bloom pass.

**Implementation**: Compute BH pair distances each frame. When distance < 5×Rs, increase bloom intensity proportional to 1/distance. Decay over 0.5s after merge.

### D3: Phase as Derived State (Not Hardcoded)

**Decision**: Phase indicator reads physics state each frame and derives the current phase. No phase transitions, no phase timers, no phase callbacks.

**Why**: Phase is a function of the current physics state, not a state machine. "Inspiral" means separation > 5×Rs. "Merger" means separation < 5×Rs. The phase changes when the physics changes, not when a timer fires.

### D4: Timeline Scrub via Snapshot Cache

**Decision**: Cache physics state every 10 frames, max 600 snapshots. Scrub finds nearest snapshot and interpolates.

**Why**: Recomputing physics from t=0 on every scrub drag is too slow for complex simulations. Caching gives smooth scrubbing with 10-frame recomputation max.

## Risks / Trade-offs

- **GW ripple amplitude may be too subtle or too loud** → Tune amplitude scaling factor. Expose in UI.
- **Snapshot cache memory usage** → 600 snapshots × (positions + velocities) for 500 particles = ~24MB. Acceptable for web.
- **Phase indicator may flicker at boundaries** → Add hysteresis (different thresholds for entering/leaving a phase).

## Open Questions

1. **GW ripple visual style**: Concentric rings? Spiral patterns? Need to match visual expectations.
2. **Snapshot cache granularity**: Every 10 frames? Every 5? Trade-off between memory and scrub smoothness.
