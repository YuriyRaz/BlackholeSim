## 1. GW Ripple Visualization

- [ ] 1.1 Add GW ripple uniforms to lensing shader: gwSourcePosition, gwFrequency, gwStrain, time
- [ ] 1.2 Implement concentric distortion rings in lensing ray-march (sinusoidal ray deflection)
- [ ] 1.3 Implement ripple amplitude scaling with gwStrain and distance (1/r decay)
- [ ] 1.4 Implement ripple frequency matching gwFrequency from physics engine
- [ ] 1.5 Implement ripple fade after gwStrain drops to zero (propagate outward, decay over 1 second)
- [ ] 1.6 Add GW ripples toggle to display toggles UI
- [ ] 1.7 Create GLSL fallback version of GW ripple shader

## 2. Merger Flash

- [ ] 2.1 Implement BH proximity detection: compute distance between all BH pairs each frame
- [ ] 2.2 Implement flash intensity: bloom spike when separation < 5×Rs, intensity ∝ 1/distance
- [ ] 2.3 Implement flash decay: bloom fades over 0.5 seconds after BHs merge
- [ ] 2.4 Wire flash to post-processing bloom pipeline (temporary intensity multiplier)

## 3. Particle Trails

- [ ] 3.1 Implement trail history buffer: store last N positions per particle (configurable, max 50)
- [ ] 3.2 Implement trail rendering: GL_LINE_STRIP with fading alpha along trail
- [ ] 3.3 Implement trail color matching: trail segment color matches particle color
- [ ] 3.4 Add particle trails toggle to display toggles UI
- [ ] 3.5 Create GLSL fallback version of trail shader

## 4. Phase Indicator

- [ ] 4.1 Implement phase derivation from BH separation: Inspiral (>5×Rs), Merger (<5×Rs), Remnant (single BH)
- [ ] 4.2 Implement phase derivation from accretion: Active accretion (accretionRate > 0), Quiescent
- [ ] 4.3 Implement phase derivation from tidal disruption: Tidal disruption (body.disrupted = true)
- [ ] 4.4 Create src/ui/PhaseIndicator.js UI component
- [ ] 4.5 Wire phase indicator to physics state (updates every frame)

## 5. UI Integration

- [ ] 5.1 Add GW ripples toggle to display toggles
- [ ] 5.2 Add particle trails toggle to display toggles
- [ ] 5.3 Add phase indicator to UI
- [ ] 5.4 Add accretion rate display to physics info panel
- [ ] 5.5 Add GW strain/frequency display to physics info panel
- [ ] 5.6 Expand timeline scrubber to work with snapshot cache

## 6. Testing & Polish

- [ ] 6.1 Test GW ripples: verify distortion rings appear when gwStrain > 0 and fade when strain = 0
- [ ] 6.2 Test merger flash: verify bloom spike when BHs are within 5×Rs
- [ ] 6.3 Test particle trails: verify fading trail rendering for any particle type
- [ ] 6.4 Test phase indicator: verify it updates based on physics state (not hardcoded)
- [ ] 6.5 Test GW ripples toggle: verify enable/disable works
- [ ] 6.6 Test particle trails toggle: verify enable/disable works
- [ ] 6.7 End-to-end test: load Binary BH preset, verify GW ripples during inspiral, merger flash at merger
- [ ] 6.8 End-to-end test: load TDE preset, verify tidal disruption, disk formation, jets from accretion
- [ ] 6.9 End-to-end test: load Kerr preset, verify disk, jets from accretion + spin, frame dragging
