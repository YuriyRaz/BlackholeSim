# J013 Investigation Report

## Status: completed_with_concerns

## Summary

Investigated the four concerns from J001 (C001–C004): missing particle-renderer and body-renderer specs, star count coordination, click-to-focus ray casting gap, and minimum quality fallback. All four are valid. particle-renderer and body-renderer need their own spec files — they are NOT covered by existing specs. The star count conflict is real and needs a precedence rule. Click-to-focus requires a ray casting capability that no spec defines. The minimum quality fallback is a genuine gap in the adaptive quality spec.

## Investigation Results

### 1. particle-renderer and body-renderer: Need Separate Specs

**Current state**: The proposal lists 8 capabilities but only 7 spec directories exist. An 8th spec (`accretion-disk/`) exists but is NOT one of the listed capabilities — it was added separately and is scoped narrowly to the disk.

**Analysis**:
- `accretion-disk/spec.md` describes particle rendering for the accretion disk specifically. It is NOT a generic particle renderer spec.
- `gpu-renderer/spec.md` covers the render pipeline, shader compilation, framebuffers, and post-processing — but has no requirements for how particles or bodies are rendered.
- `DESIGN.md` section 5.2 defines a generic `particle.wgsl` shader for point sprites, and section 7.1 defines the body data model — but no spec captures these as requirements.

**particle-renderer** needs its own spec covering:
- Generic point-sprite rendering for any particle type (gas, jet, debris, test)
- Reading position, velocity, color/temperature, size from physics state
- Size scaling by distance (perspective point size)
- Soft-circle fragment shader (alpha falloff at edges)
- Additive blending for jet particles
- Point size limits and particle count budgets per quality level

**body-renderer** needs its own spec covering:
- Star rendering as colored spheres with radius from physics state
- Black hole silhouettes: black disk at event horizon radius
- Photon sphere glow ring at 1.5×Rs
- Neutron star rendering with pulsar beam cones
- Body type dispatch (different rendering path per `body.type`)
- Corona/surface glow effects

**Recommendation**: Create `specs/particle-renderer/spec.md` and `specs/body-renderer/spec.md` before implementation begins. These are core rendering components with no formal requirements — implementation would be ambiguous without them.

### 2. Star Count Coordination: Real Conflict

**Conflict**:
- `adaptive-quality/spec.md` line 15: Low → 1000 stars, Medium → 2000 stars, High → 3000 stars
- `celestial-background/spec.md` line 55: UI dropdown with 1000, 2000, 3000, 5000 stars

**Two possible resolutions**:

| Approach | Behavior | Tradeoff |
|----------|----------|----------|
| **Adaptive overrides UI** | When quality=Auto, star count follows quality level. UI star selector is disabled or ignored. | Simple, but user loses fine-grained control |
| **UI overrides adaptive** | Star count is always user-controlled. Adaptive quality only adjusts lensing resolution and ray steps. | More flexible, but adaptive can't optimize star rendering |

**Recommendation**: The cleaner approach is **UI overrides adaptive**. Remove star count from the adaptive quality levels entirely. Adaptive quality should control only GPU-heavy settings (lensing resolution, ray-march steps, post-processing). Star count is a visual preference, not a performance bottleneck — procedural stars are cheap to render (just a hash in the fragment shader). This avoids the conflict and keeps the user in control.

**Action needed**: Update `adaptive-quality/spec.md` to remove star count from quality levels. Star count stays in `celestial-background/spec.md` as a user-only control.

### 3. Click-to-Focus Ray Casting: Missing Capability

**Gap**: `camera-system/spec.md` line 73–78 requires click-to-focus:
> "The system SHALL allow clicking on an object in the 3D viewport to focus the camera on it with a smooth transition."

This requires:
1. **Ray casting**: Convert screen (x, y) → world-space ray
2. **Object picking**: Test ray against all visible bodies and particles
3. **Distance sorting**: Find the closest intersected object
4. **Camera transition**: Smoothly move focus to the selected object

No existing spec defines ray casting or object picking. `gpu-renderer/spec.md` covers render passes and framebuffers but not reverse-projection or hit testing.

**Options**:
- **Add ray casting to gpu-renderer spec**: Reasonable since it's a GPU infrastructure concern. Add requirements for screen-to-world ray generation and object intersection testing.
- **Add ray casting to camera-system spec**: Put the picking logic where it's consumed. The camera system already knows about focus points.
- **Create a separate picking spec**: Overkill for a single feature.

**Recommendation**: Add a ray casting / object picking requirement to `gpu-renderer/spec.md`. It's a rendering infrastructure capability that the camera system consumes. The gpu-renderer already manages the projection matrix and viewport — it's the natural place to expose `screenToWorldRay()` and `pickObject(ray)`.

**Suggested requirements**:
- `screenToWorldRay(screenX, screenY)` → returns world-space ray origin + direction
- `pickObject(ray, bodies[])` → returns closest intersected body or null
- Intersection test: ray-sphere for stars/neutron stars, ray-sphere for BH event horizon

### 4. Minimum Quality Fallback: Real Gap

**Gap**: The adaptive quality spec defines 3 levels (Low, Medium, High) with auto-adjustment. But:
- Low quality = half-res lensing + 15 ray steps + 1000 stars + FXAA disabled
- If Low quality still can't maintain 30fps on very weak hardware, there's no further fallback
- No frame skip, no simulation slowdown, no reduced particle count

**Current Low quality settings**:
- Half resolution (540p) — already aggressive
- 15 ray steps — already minimal
- FXAA off — minimal savings

**Options**:
| Fallback | Savings | Visual Impact |
|----------|---------|---------------|
| Reduce particle count | Moderate | Disk looks sparse |
| Disable lensing entirely | High | Loses core feature |
| Skip frames (render every 2nd) | High | Janky motion |
| Slow simulation (reduce physics rate) | Moderate | Physics looks slow |
| Add "Minimum" quality level | Varies | Depends on what it disables |

**Recommendation**: Add a "Minimum" quality level that reduces particle count (from budget) and disables FXAA and vignette. If Minimum still can't hold 30fps, skip frames (render every other frame). This is better than disabling lensing, which is the project's core feature.

**Suggested Minimum quality**:
- Half resolution lensing
- 10 ray-march steps
- 500 stars
- Particle count halved
- No post-processing
- Frame skip if still below 20fps

**Action needed**: Add "Minimum" level to `adaptive-quality/spec.md` and define frame skip behavior.

## Additional Finding: accretion-disk spec is orphaned

The `accretion-disk/` spec directory exists but is NOT listed in the proposal's capabilities. The proposal lists 8 capabilities (gpu-renderer, gravitational-lensing, particle-renderer, body-renderer, celestial-background, camera-system, adaptive-quality, ui-shell). Accretion disk rendering is covered by the particle-renderer — the disk is just particles.

**Recommendation**: Either remove `accretion-disk/spec.md` and fold its requirements into the new particle-renderer spec, or add accretion-disk as a 9th capability in the proposal. The former is cleaner — the disk spec's requirements (particle color from temperature, disk shape from distribution) are particle rendering concerns.

## Concerns

### C001: Missing particle-renderer and body-renderer specs (confirmed HIGH)
- **Impact**: Core rendering components have no formal requirements. Implementation will be ambiguous and inconsistent.
- **Recommendation**: Create both spec files before any implementation work begins.

### C002: Star count coordination conflict (confirmed MEDIUM)
- **Impact**: Adaptive quality and celestial-background specs define conflicting star count controls.
- **Recommendation**: Remove star count from adaptive-quality levels. Star count is a user-only control in celestial-background.

### C003: Click-to-focus requires undefined ray casting (confirmed MEDIUM)
- **Impact**: Camera-system requires a capability that no spec defines.
- **Recommendation**: Add screen-to-world ray casting and object picking requirements to gpu-renderer spec.

### C004: No minimum quality or frame skip fallback (confirmed MEDIUM)
- **Impact**: Very weak GPUs may not maintain 30fps even at Low quality.
- **Recommendation**: Add "Minimum" quality level and frame skip behavior to adaptive-quality spec.

### C005: Orphaned accretion-disk spec (NEW, LOW)
- **Impact**: Confusing — spec exists for a capability not listed in the proposal.
- **Recommendation**: Remove accretion-disk spec and merge its requirements into particle-renderer spec.

## Proposed Jobs

1. **Create particle-renderer spec** — New spec file covering generic point-sprite rendering for all particle types (gas, jet, debris, test). Should incorporate accretion-disk spec requirements.
2. **Create body-renderer spec** — New spec file covering star spheres, BH silhouettes, photon sphere glow, neutron star pulsar beams.
3. **Fix star count coordination** — Update adaptive-quality/spec.md to remove star count from quality levels.
4. **Add ray casting to gpu-renderer** — Add screen-to-world ray and object picking requirements.
5. **Add minimum quality level** — Update adaptive-quality/spec.md with Minimum level and frame skip.
6. **Remove or merge accretion-disk spec** — Fold its requirements into particle-renderer.

## Checkpoint Summary

**Completed work**:
- Read all 7 existing specs, proposal.md, DESIGN.md, J001 report
- Confirmed all 4 original concerns (C001–C004) are valid
- Discovered additional concern (C005: orphaned accretion-disk spec)
- Provided specific recommendations for each concern
- Proposed 6 follow-up jobs

**Accepted decisions**:
- particle-renderer and body-renderer need their own spec files
- Star count should be user-only (remove from adaptive quality)
- Ray casting belongs in gpu-renderer spec
- Minimum quality level should exist with frame skip fallback
- accretion-disk spec should be merged into particle-renderer

**Active concerns**:
- C001: Missing particle-renderer and body-renderer specs (HIGH)
- C002: Star count conflict (MEDIUM)
- C003: Ray casting gap (MEDIUM)
- C004: Minimum quality fallback (MEDIUM)
- C005: Orphaned accretion-disk spec (LOW)

**Relevant artifact paths**:
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\proposal.md`
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\` (7 directories)
- `C:\Projects\BlackholeSim\docs\DESIGN.md`
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\accretion-disk\spec.md`

**Next permitted action**: Wait for orchestrator to create spec files or dispatch implementation jobs.
