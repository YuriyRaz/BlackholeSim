## 1. Audio Engine

- [ ] 1.1 Create src/audio/ directory with AudioEngine.js, SpacetimeHum.js, GWSound.js, EventSounds.js, SpatialAudio.js
- [ ] 1.2 Implement AudioEngine: Web Audio API context, master compressor, gain staging
- [ ] 1.3 Implement autoplay policy handling: require user interaction before audio starts
- [ ] 1.4 Implement layer system: independent gain nodes for hum, GW, events
- [ ] 1.5 Implement master volume control and mute toggle

## 2. Spacetime Hum

- [ ] 2.1 Implement base oscillator: 40 Hz sine wave
- [ ] 2.2 Implement octave harmonics: 80, 120, 160 Hz with decreasing amplitude
- [ ] 2.3 Implement LFO modulation: slow amplitude oscillation for breathing effect
- [ ] 2.4 Implement proximity-based volume: scales with 1/distance to nearest BH
- [ ] 2.5 Wire to physics engine: read BH positions each frame

## 3. GW Chirp Sonification

- [ ] 3.1 Implement frequency mapping: gwFrequency from physics → audible range (20-500 Hz)
- [ ] 3.2 Implement dual oscillators: h+ and h× polarizations as two detuned oscillators
- [ ] 3.3 Implement chirp sweep: frequency increases during inspiral (reads gwFrequency)
- [ ] 3.4 Implement ringdown damping: frequency and amplitude decay after merger
- [ ] 3.5 Wire to physics engine: read gwFrequency, gwStrain each frame

## 4. Event Sounds

- [ ] 4.1 Implement disruption crackle: filtered noise burst triggered when body.disrupted = true
- [ ] 4.2 Implement merger impact: noise + reverb triggered when BH separation < 5×Rs
- [ ] 4.3 Implement accretion whoosh: low-pass filtered noise scaled by accretionRate
- [ ] 4.4 Wire all events to physics engine state (no scenario-specific triggers)

## 5. Spatial Audio

- [ ] 5.1 Implement HRTF panner nodes for each black hole
- [ ] 5.2 Implement distance attenuation: volume scales with 1/distance
- [ ] 5.3 Implement Doppler pitch shift: frequency shifts based on relative velocity
- [ ] 5.4 Update panner positions each frame from physics state

## 6. Touch Controls

- [ ] 6.1 Implement 1-finger orbit: touch drag rotates camera
- [ ] 6.2 Implement 2-finger pan: two-finger drag pans camera
- [ ] 6.3 Implement pinch zoom: two-finger pinch adjusts camera distance
- [ ] 6.4 Implement double-tap to focus: double tap on object triggers camera transition
- [ ] 6.5 Add touch event listeners to canvas element

## 7. Loading Screen

- [ ] 7.1 Create src/ui/LoadingScreen.js component with progress bar
- [ ] 7.2 Track asset loading progress (textures, shaders)
- [ ] 7.3 Implement fade-out transition when loading completes
- [ ] 7.4 Wire to asset loader in main.js

## 8. Cinematic Post-Processing

- [ ] 8.1 Implement motion blur pass (high quality only)
- [ ] 8.2 Implement chromatic aberration pass (subtle)
- [ ] 8.3 Implement lens flare pass (bright sources)
- [ ] 8.4 Implement depth of field pass (optional)
- [ ] 8.5 Implement color grading (cinematic blue-orange)
- [ ] 8.6 Wire post-processing toggles to quality levels

## 9. Error Handling

- [ ] 9.1 Implement WebGL context loss recovery
- [ ] 9.2 Implement shader compilation error display (overlay with line numbers)
- [ ] 9.3 Implement graceful degradation on unsupported hardware
- [ ] 9.4 Add error display UI component

## 10. Accessibility

- [ ] 10.1 Add keyboard navigation to all UI elements
- [ ] 10.2 Add ARIA labels to interactive elements
- [ ] 10.3 Add focus indicators
- [ ] 10.4 Implement reduced motion support (disable camera auto-orbit, reduce particle count)

## 11. Testing & Polish

- [ ] 11.1 Test audio engine: verify Web Audio context creates and plays
- [ ] 11.2 Test spacetime hum: verify volume scales with proximity
- [ ] 11.3 Test GW chirp: verify frequency follows gwFrequency from physics
- [ ] 11.4 Test event sounds: verify disruption/merger/accretion sounds trigger correctly
- [ ] 11.5 Test spatial audio: verify HRTF panning follows BH positions
- [ ] 11.6 Test touch controls: verify orbit/pan/zoom on touch device
- [ ] 11.7 Test loading screen: verify progress bar and fade-out
- [ ] 11.8 Test error handling: verify context loss recovery
- [ ] 11.9 Test accessibility: verify keyboard navigation and ARIA labels
- [ ] 11.10 End-to-end test: full simulation with audio, touch, loading, post-processing
