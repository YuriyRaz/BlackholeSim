## Context

Extends all previous proposals. Proposals 1-3 deliver renderer, physics engine, and visual effects. This proposal adds audio and final polish. All audio is triggered by physics state, not scenario events.

## Goals / Non-Goals

**Goals:**
- Procedural audio engine (no audio files)
- Spacetime hum that scales with proximity
- GW chirp sonification from physics state
- Event sounds triggered by physics events
- Spatial audio with HRTF
- Touch controls for mobile
- Loading screen
- Cinematic post-processing
- Error handling and accessibility

**Non-Goals:**
- Audio files — all procedural
- Scenario-specific audio — triggered by physics state
- Full Dolby Atmos — HRTF stereo is sufficient

## Decisions

### D1: Procedural Audio (No Audio Files)

**Decision**: All sounds synthesized from oscillators, noise, and filters. No audio file loading.

**Why**: Eliminates asset loading, reduces bundle size, allows real-time parameter control (pitch, volume, filter). Web Audio API is designed for this.

### D2: Audio Reads Physics State

**Decision**: Audio system subscribes to physics engine state (gwFrequency, gwStrain, accretion rate, BH proximity, body disruption). No scenario-specific audio triggers.

**Why**: Physics state is the single source of truth. If the physics says GW strain is nonzero, we play GW sound. If a body is disrupted, we play disruption sound. No special cases.

### D3: Spatial Audio with HRTF

**Decision**: Use Web Audio API's PannerNode with HRTF (Head-Related Transfer Function) for 3D spatialization.

**Why**: HRTF gives convincing 3D audio without headphones — sounds like they're coming from the BH's position in 3D space. Built into Web Audio API.

### D4: Post-Processing as Optional Passes

**Decision**: Each post-processing effect (motion blur, chromatic aberration, etc.) is a separate render pass that can be toggled independently.

**Why**: Users on weak hardware can disable expensive effects. Quality levels control which effects are active.

## Risks / Trade-offs

- **Web Audio API autoplay policy** → Require user interaction before starting audio. Show "Click to enable audio" prompt.
- **HRTF not supported everywhere** → Fallback to simple stereo panning.
- **Motion blur expensive** → Only on High quality. Disable on Medium/Low.

## Open Questions

1. **Audio volume balance**: How loud should GW chirp be relative to spacetime hum? Need user testing.
2. **Loading screen timing**: When to show loading screen? Only for texture loading, or also for shader compilation?
