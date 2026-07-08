## Why

Proposals 1-3 deliver a visually stunning, physically driven black hole simulation. But something is missing: sound. The deep rumble of spacetime curvature, the rising pitch of a gravitational wave chirp, the crackle of a star being torn apart — these audio elements transform a visual demo into an immersive experience.

The audio system reads from the physics engine, not from scenario classes. GW sonification reads gwFrequency and gwStrain. Event sounds trigger when the physics engine reports tidal disruption or BH proximity. The spacetime hum scales with proximity to the nearest BH. Everything is driven by the physics state.

## What Changes

- **Audio engine**: Web Audio API with procedural sound generation. No audio files — all sounds synthesized.
- **Spacetime hum**: 40 Hz base frequency with octave harmonics, LFO modulation. Volume scales with camera distance to nearest BH.
- **GW chirp sonification**: gwFrequency mapped to audible range (20-500 Hz). Frequency sweeps up during inspiral, peaks at merger, damps during ringdown.
- **Event sounds**: Procedural disruption crackle, merger impact, accretion whoosh — triggered by physics state.
- **Spatial audio**: HRTF panners on each BH. Sound follows 3D position, louder when closer, Doppler shift.
- **Layer muting**: Independent volume control for hum, GW sound, event sounds.
- **Touch controls**: 1-finger orbit, 2-finger pan, pinch zoom, double-tap to focus.
- **Loading screen**: Progress bar during asset loading.
- **Cinematic post-processing**: Motion blur, chromatic aberration, lens flare, DoF, color grading.
- **Error handling**: WebGL context loss recovery, shader compilation error display.
- **Accessibility**: Keyboard navigation, ARIA labels, reduced motion support.

## Capabilities

### New Capabilities

- `audio-engine`: Web Audio API setup, master compressor, gain staging.
- `spacetime-hum`: Procedural 40 Hz hum with harmonics, proximity-based volume.
- `gw-sound`: GW sonification from gwFrequency/gwStrain from physics engine.
- `event-sounds`: Disruption crackle, merger impact, accretion whoosh — triggered by physics state.
- `spatial-audio`: HRTF 3D panning, distance attenuation, Doppler shift per BH.
- `touch-controls`: Mobile touch gestures for camera control.
- `loading-screen`: Asset loading progress display.
- `cinematic-postprocess`: Motion blur, chromatic aberration, lens flare, DoF, color grading, vignette.

### Modified Capabilities

- `ui-shell`: Mute toggle functional. Volume slider. Per-layer muting. Touch controls. Loading screen. Accessibility.
- `adaptive-quality`: Quality levels include post-processing toggles.

## Impact

- **Extends all previous proposals**: Audio hooks into physics state (Prop 2), visual effects (Prop 3). Post-processing extends renderer (Prop 1).
- **No scenario-specific audio code**: All sounds triggered by physics state.
- **No new dependencies**: Web Audio API is built into browsers.
- **Performance**: Audio ~1-2% CPU. Post-processing ~2ms GPU per effect.
