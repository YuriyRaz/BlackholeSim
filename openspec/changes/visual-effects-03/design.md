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

**Implementation**: Read `bhPairs` from `PhysicsEngine.getState()`. When any pair distance < 5×Rs, increase bloom intensity proportional to 1/distance. Decay over 0.5s after merge. The `bhPairs` array is computed by the physics engine each frame (avoids duplicating distance calculations in the renderer).

### D3: Phase as Derived State (Not Hardcoded)

**Decision**: Phase indicator reads physics state each frame and derives the current phase. No phase transitions, no phase timers, no phase callbacks.

**Why**: Phase is a function of the current physics state, not a state machine. "Inspiral" means separation > 5×Rs. "Merger" means separation < 5×Rs. The phase changes when the physics changes, not when a timer fires.

### D4: Timeline Scrub via Snapshot Cache

**Decision**: Cache physics state every 10 frames, max 600 snapshots. Scrub finds nearest snapshot and interpolates.

**Why**: Recomputing physics from t=0 on every scrub drag is too slow for complex simulations. Caching gives smooth scrubbing with 10-frame recomputation max.

### D5: Particle Trails as Extended TrailRenderer

**Decision**: Extend the existing `TrailRenderer` to handle both body trails and particle trails, rather than creating a separate renderer.

**Why**: The existing `TrailRenderer` already handles line-strip rendering with fading alpha for body trails. Particle trails use the same rendering approach — only the data source differs (particle history buffer vs. body trail array). A single renderer avoids code duplication and keeps the render pipeline unified.

**Implementation**: 
- Physics engine stores a `particleTrails` buffer: `Map<particleId, Array<[x,y,z]>>` storing last N positions (configurable, default 50).
- `TrailRenderer.render()` accepts both `bodies[].trail` (existing) and `particleTrails` (new) in `camState`.
- Particle trail segments use per-particle color from the particle's temperature-derived color.
- Trail length is configurable via UI (0-50 segments).

**WebGPU note**: The current `TrailRenderer` is GL-only (`_initGL()` only). WebGPU path will be added as a follow-up. For MVP, particle trails are available in WebGL 2.0 mode.

## Risks / Trade-offs

- **GW ripple amplitude may be too subtle or too loud** → Tune amplitude scaling factor. Expose in UI.
- **Snapshot cache memory usage** → 600 snapshots × (positions + velocities) for 500 particles = ~24MB. Acceptable for web.
- **Phase indicator may flicker at boundaries** → Add hysteresis (different thresholds for entering/leaving a phase).
- **WebGPU path gaps** → `TrailRenderer` and `ParticleRenderer` are GL-only for MVP. `LensingPass` has WebGPU init but needs GW uniforms added. WebGPU users will see GW ripples and merger flash (via LensingPass/PostProcessor) but not particle trails. WebGPU trail renderer is a follow-up task.

## Open Questions

1. **GW ripple visual style**: Concentric rings? Spiral patterns? Need to match visual expectations.
2. **Snapshot cache granularity**: Every 10 frames? Every 5? Trade-off between memory and scrub smoothness.
3. **Particle trail color source**: Use temperature-derived color from the particle's `temperature` property (blue-white → red mapping), or use the particle's existing `color` attribute? Temperature-derived is more physically accurate but requires the color mapping to happen per-segment.
