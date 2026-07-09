## 1. Audio Engine

- [x] 1.1 Create src/audio/ directory with AudioEngine.js, SpacetimeHum.js, GWSound.js, EventSounds.js, SpatialAudio.js
- [x] 1.2 Implement AudioEngine: Web Audio API context, master compressor, gain staging
- [x] 1.3 Implement autoplay policy handling: require user interaction before audio starts
- [x] 1.4 Implement layer system: independent gain nodes for hum, GW, events
- [x] 1.5 Implement master volume control and mute toggle

## 2. Spacetime Hum

- [x] 2.1 Implement base oscillator: 40 Hz sine wave
- [x] 2.2 Implement octave harmonics: 80, 120, 160 Hz with decreasing amplitude
- [x] 2.3 Implement LFO modulation: slow amplitude oscillation for breathing effect
- [x] 2.4 Implement proximity-based volume: scales with 1/distance to nearest BH
- [x] 2.5 Wire to physics engine: read BH positions each frame

## 3. GW Chirp Sonification

- [x] 3.1 Implement frequency mapping: gwFrequency from physics → audible range (20-500 Hz)
- [x] 3.2 Implement dual oscillators: h+ and h× polarizations as two detuned oscillators
- [x] 3.3 Implement chirp sweep: frequency increases during inspiral (reads gwFrequency)
- [x] 3.4 Implement ringdown damping: frequency and amplitude decay after merger
- [x] 3.5 Wire to physics engine: read gwFrequency, gwStrain each frame

## 4. Event Sounds

- [x] 4.1 Implement disruption crackle: filtered noise burst triggered when body.disrupted = true
- [x] 4.2 Implement merger impact: noise + reverb triggered when BH separation < 5×Rs
- [x] 4.3 Implement accretion whoosh: low-pass filtered noise scaled by accretionRate
- [x] 4.4 Wire all events to physics engine state (no scenario-specific triggers)

## 5. Spatial Audio

- [x] 5.1 Implement HRTF panner nodes for each black hole
- [x] 5.2 Implement distance attenuation: volume scales with 1/distance
- [x] 5.3 Implement Doppler pitch shift: frequency shifts based on relative velocity
- [x] 5.4 Update panner positions each frame from physics state

## 6. Touch Controls

- [x] 6.1 Implement 1-finger orbit: touch drag rotates camera
- [x] 6.2 Implement 2-finger pan: two-finger drag pans camera
- [x] 6.3 Implement pinch zoom: two-finger pinch adjusts camera distance
- [x] 6.4 Implement double-tap to focus: double tap on object triggers camera transition
- [x] 6.5 Add touch event listeners to canvas element

## 7. Loading Screen

- [x] 7.1 Create src/ui/LoadingScreen.js component with progress bar
- [x] 7.2 Track asset loading progress (textures, shaders)
- [x] 7.3 Implement fade-out transition when loading completes
- [x] 7.4 Wire to asset loader in main.js

## 8. Cinematic Post-Processing

- [x] 8.1 Implement motion blur pass (high quality only)
- [x] 8.2 Implement chromatic aberration pass (subtle)
- [x] 8.3 Implement lens flare pass (bright sources)
- [x] 8.4 Implement depth of field pass (optional)
- [x] 8.5 Implement color grading (cinematic blue-orange)
- [x] 8.6 Wire post-processing toggles to quality levels

## 9. Error Handling

- [x] 9.1 Implement WebGL context loss recovery
- [x] 9.2 Implement shader compilation error display (overlay with line numbers)
- [x] 9.3 Implement graceful degradation on unsupported hardware
- [x] 9.4 Add error display UI component

## 10. Accessibility

- [x] 10.1 Add keyboard navigation to all UI elements
- [x] 10.2 Add ARIA labels to interactive elements
- [x] 10.3 Add focus indicators
- [x] 10.4 Implement reduced motion support (disable camera auto-orbit, reduce particle count)

## 11. Testing & Polish

- [x] 11.1 Test audio engine: verify Web Audio context creates and plays
- [x] 11.2 Test spacetime hum: verify volume scales with proximity
- [x] 11.3 Test GW chirp: verify frequency follows gwFrequency from physics
- [x] 11.4 Test event sounds: verify disruption/merger/accretion sounds trigger correctly
- [x] 11.5 Test spatial audio: verify HRTF panning follows BH positions
- [x] 11.6 Test touch controls: verify orbit/pan/zoom on touch device
- [x] 11.7 Test loading screen: verify progress bar and fade-out
- [x] 11.8 Test error handling: verify context loss recovery
- [x] 11.9 Test accessibility: verify keyboard navigation and ARIA labels
- [x] 11.10 End-to-end test: full simulation with audio, touch, loading, post-processing