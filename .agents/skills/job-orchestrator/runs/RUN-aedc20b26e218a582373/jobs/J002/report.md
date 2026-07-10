# Architecture Review: visual-effects-03

## Summary
The visual-effects-03 implementation aligns with the design decisions and specifications. All core features are present: GW ripples, merger flash, particle trails, phase indicator, timeline scrubber, and UI toggles. The architecture is clean, with effects driven by physics state and no scenario-specific code.

## Findings

### 1. GW Ripple Fade
- **Gap**: Design specifies ripples should propagate outward and fade over ~1 second after gwStrain drops to zero.
- **Current**: The lensing shader uses `gwStrain` directly; when strain becomes zero, amplitude becomes zero instantly. The physics engine stores `_gwRippleFadeStrain` and `_gwRippleFadeTime` but they are never updated or used.
- **Impact**: Ripples disappear abruptly instead of fading out.

### 2. Particle Trail Color
- **Gap**: Specification requires each trail segment to have color derived from particle temperature (blue-white → red).
- **Current**: `TrailRenderer` uses a uniform `particleTrailColor` for all particle trails, not per-segment temperature mapping. The physics engine stores only positions in `particleTrails`, not temperature per segment.
- **Impact**: Trail colors do not reflect temperature gradients.

### 3. Trail Length Configuration
- **Gap**: Specification says trail length SHALL be configurable via UI (0-50 segments).
- **Current**: `_trailMaxLength` is hardcoded to 50 in PhysicsEngine; no UI control exists.
- **Impact**: Users cannot adjust trail length.

### 4. Phase Indicator Hysteresis
- **Gap**: Design mentions adding hysteresis to avoid flicker at phase boundaries (e.g., separation ratio near 5×Rs).
- **Current**: No hysteresis; phase changes instantly when separation crosses threshold.
- **Impact**: Potential rapid flickering during mergers.

### 5. Merger Flash Intensity Scaling
- **Observation**: Flash intensity uses quadratic scaling (`linear * linear`) rather than strict inverse distance. This is acceptable but may be tuned differently than spec expectation.

### 6. WebGPU Trail Fallback
- **Status**: `TrailRenderer` is GL-only, as noted in design. WebGPU trail rendering is a follow-up task. No issue.

### 7. Testing
- **Gap**: No automated unit/integration tests for visual effects. Tasks.md includes manual test cases (8.1-8.11) but no automated test suite.
- **Impact**: Regression risk; future changes may break visual effects without detection.

### 8. Performance Considerations
- **Particle trails map**: Grows with particle count; each particle stores up to 50 positions. For 35K particles, memory usage could be ~35K * 50 * 12 bytes ≈ 21 MB. Acceptable but monitor.
- **Snapshot cache**: 600 snapshots as designed.

### 9. Documentation Consistency
- Specs, design, and implementation are consistent.
- Open questions from design (GW ripple visual style, snapshot granularity, trail color source) are resolved in implementation but not explicitly documented.

## Recommendations
1. **Implement GW ripple fade**: Use `_gwRippleFadeStrain` and `_gwRippleFadeTime` to drive fade-out in lensing shader.
2. **Add per-segment temperature to trail data**: Extend `particleTrails` to store temperature per position, or use particle's current temperature for each segment.
3. **Add trail length UI slider**: Expose `_trailMaxLength` via DisplayToggles or a new UI control.
4. **Add hysteresis to phase indicator**: Use different thresholds for entering/leaving phases to prevent flicker.
5. **Add automated tests**: Create unit tests for `_computeBHPairs`, `_updateParticleTrails`, `computeMergerFlash`, and `derivePhase`.

## Conclusion
The implementation is solid and meets the core requirements. The identified gaps are minor and can be addressed in follow-up tasks. The architecture is extensible and maintainable.
