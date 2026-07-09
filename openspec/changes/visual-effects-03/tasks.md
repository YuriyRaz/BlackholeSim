## 1. GW Ripple Visualization

- [ ] 1.1 Add GW ripple uniforms to lensing shader: gwSourcePosition, gwFrequency, gwStrain, time
- [ ] 1.2 Implement concentric distortion rings in lensing ray-march (sinusoidal ray deflection)
- [ ] 1.3 Implement ripple amplitude scaling with gwStrain and distance (1/r decay)
- [ ] 1.4 Implement ripple frequency matching gwFrequency from physics engine
- [ ] 1.5 Implement ripple fade after gwStrain drops to zero (propagate outward, decay over 1 second)
- [ ] 1.6 Add GW ripples toggle to display toggles UI
- [ ] 1.7 Create GLSL fallback version of GW ripple shader

## 2. Merger Flash

- [ ] 2.1 Implement bhPairs computation in PhysicsEngine: compute distance between all BH pairs each frame
- [ ] 2.2 Add bhPairs to PhysicsEngine.getState() output (format: [{ a: index, b: index, distance: float }])
- [ ] 2.3 Implement flash intensity: bloom spike when separation < 5×Rs, intensity ∝ 1/distance
- [ ] 2.4 Implement flash decay: bloom fades over 0.5 seconds after BHs merge
- [ ] 2.5 Wire flash to post-processing bloom pipeline (temporary intensity multiplier)

## 3. Particle Trails

- [ ] 3.1 Implement particle trail history buffer in PhysicsEngine: store last N positions per particle (configurable, max 50)
- [ ] 3.2 Add particleTrails to PhysicsEngine.getState() output
- [ ] 3.3 Extend TrailRenderer to handle particle trails (in addition to existing body trails)
- [ ] 3.4 Implement trail rendering: GL_LINE_STRIP with fading alpha along trail
- [ ] 3.5 Implement trail color: derive from particle temperature via temperature-to-color mapping in fragment shader
- [ ] 3.6 Add particle trails toggle to display toggles UI
- [ ] 3.7 Create GLSL fallback version of trail shader

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

## 6. Timeline Scrubber

- [ ] 6.1 Implement snapshot cache: cache physics state every 10 frames, max 600 snapshots
- [ ] 6.2 Implement snapshot storage: store positions, velocities, GW state, accretion rate per snapshot
- [ ] 6.3 Implement scrub UI: timeline slider that navigates to nearest cached snapshot
- [ ] 6.4 Implement snapshot interpolation: interpolate between two nearest snapshots for smooth scrubbing
- [ ] 6.5 Wire timeline scrubber to simulation pause/play (scrubbing pauses simulation)
- [ ] 6.6 Implement snapshot cache memory management: trim oldest snapshots when limit reached

## 7. GPU Particle Temperature Mapping

- [ ] 7.1 Add temperature attribute to particle vertex buffer (replace or supplement a_color)
- [ ] 7.2 Implement temperature-to-color mapping in particle fragment shader (blue-white → red gradient)
- [ ] 7.3 Add temperature uniform or attribute to TrailRenderer for trail color derivation

## 8. Testing & Polish

- [ ] 8.1 Test GW ripples: verify distortion rings appear when gwStrain > 0 and fade when strain = 0
- [ ] 8.2 Test merger flash: verify bloom spike when BHs are within 5×Rs
- [ ] 8.3 Test particle trails: verify fading trail rendering for any particle type
- [ ] 8.4 Test phase indicator: verify it updates based on physics state (not hardcoded)
- [ ] 8.5 Test GW ripples toggle: verify enable/disable works
- [ ] 8.6 Test particle trails toggle: verify enable/disable works
- [ ] 8.7 Test timeline scrubber: verify snapshot cache and scrubbing works
- [ ] 8.8 Test temperature-to-color: verify particles change color with temperature
- [ ] 8.9 End-to-end test: load Binary BH preset, verify GW ripples during inspiral, merger flash at merger
- [ ] 8.10 End-to-end test: load TDE preset, verify tidal disruption, disk formation, jets from accretion
- [ ] 8.11 End-to-end test: load Kerr preset, verify disk, jets from accretion + spin, frame dragging
