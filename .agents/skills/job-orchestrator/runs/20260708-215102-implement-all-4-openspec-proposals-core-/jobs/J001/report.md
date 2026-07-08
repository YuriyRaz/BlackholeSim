# J001 Report

## Status: completed

## Summary

Completed the "create-proposal" step for core-renderer-01. Applied all Architect (J013) recommendations: created particle-renderer and body-renderer specs, resolved the star count conflict, added ray casting to gpu-renderer, added Minimum quality level with frame skip to adaptive-quality, and merged the orphaned accretion-disk spec into particle-renderer.

## Changes Made

### New Spec Files Created

1. **`specs/particle-renderer/spec.md`** — New spec covering:
   - Generic point-sprite rendering for all particle types (gas, jet, debris, test)
   - Particle color from temperature (blackbody-inspired gradient)
   - Soft-circle fragment shader with alpha falloff
   - Perspective point size scaling
   - Particle count budgets per quality level (6K/12K/20K/35K)
   - Accretion disk rendering requirements (merged from accretion-disk spec)
   - Disk light bending (back-of-disk visible above BH shadow)

2. **`specs/body-renderer/spec.md`** — New spec covering:
   - Body type dispatch (blackhole/star/neutronstar)
   - Star sphere rendering with color from temperature and corona glow
   - Black hole silhouette rendering (black disk at event horizon + photon sphere glow ring)
   - Neutron star pulsar beam rendering (bipolar cones, lighthouse effect)
   - Quality-level-dependent body rendering (simplified at Minimum quality)

### Modified Spec Files

3. **`specs/adaptive-quality/spec.md`** — Updated:
   - Removed star count from all quality levels (star count is user-only in celestial-background)
   - Added "Minimum" quality level (half-res, 10 ray steps, 6K particles, no post-processing)
   - Added frame skip behavior: when Minimum quality + FPS < 20, skip every other frame
   - Added frame skip deactivation: resumes when FPS > 25
   - Physics continues at full rate during frame skip
   - Updated quality selector UI to include Minimum option
   - Updated auto-adjustment range: High→Medium→Low→Minimum

4. **`specs/gpu-renderer/spec.md`** — Updated:
   - Added `screenToWorldRay(screenX, screenY)` requirement (world-space ray from screen coordinates)
   - Added `pickObject(ray, bodies)` requirement (closest intersected body or null)
   - Added ray-sphere intersection testing requirement
   - Defined sphere sizes per body type (Rs for BH, body.radius for stars/neutron stars)
   - Updated capability description to include ray casting and object picking

### Removed Spec Files

5. **`specs/accretion-disk/`** — Removed (merged into particle-renderer)
   - Disk-as-particles requirement → particle-renderer generic rendering
   - Temperature-to-color requirement → particle-renderer color from temperature
   - Disk light bending → particle-renderer disk light bending

### Updated Proposal

6. **`proposal.md`** — Updated:
   - Added "Minimum quality level with frame skip fallback" to adaptive quality description
   - Updated gpu-renderer capability to include "screen-to-world ray casting, object picking"
   - Updated particle-renderer capability to note accretion-disk requirements incorporated
   - Updated celestial-background capability to note user-controlled star count
   - Updated adaptive-quality capability to note minimum quality fallback
   - Updated accretion disk impact note to reference merge into particle-renderer

## Concerns

None — all Architect recommendations have been applied.

## Questions

None — all blocking questions from J001 have been resolved by the Architect.

## Checkpoint Summary

**Completed work**:
- Read all 8 existing specs (7 + accretion-disk), proposal.md, DESIGN.md, config.yaml
- Applied all 5 Architect recommendations from J013 report
- Created 2 new spec files (particle-renderer, body-renderer)
- Modified 2 existing spec files (adaptive-quality, gpu-renderer)
- Removed 1 orphaned spec (accretion-disk), merged into particle-renderer
- Updated proposal.md to reflect all changes
- Updated J001 report

**Accepted decisions**:
- particle-renderer and body-renderer are separate capabilities with dedicated specs
- Star count is user-only (removed from adaptive quality levels)
- Ray casting and object picking belong in gpu-renderer spec
- Minimum quality level with frame skip is the fallback for very weak GPUs
- accretion-disk spec is merged into particle-renderer (disk is just particles)

**Resolution of original concerns**:
- C001 (missing specs): RESOLVED — particle-renderer and body-renderer specs created
- C002 (star count conflict): RESOLVED — removed star count from adaptive-quality
- C003 (ray casting gap): RESOLVED — added to gpu-renderer spec
- C004 (no minimum quality): RESOLVED — added Minimum level + frame skip
- C005 (orphaned accretion-disk): RESOLVED — merged into particle-renderer, directory removed

**Relevant artifact paths**:
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\proposal.md`
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\particle-renderer\spec.md` (NEW)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\body-renderer\spec.md` (NEW)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\adaptive-quality\spec.md` (MODIFIED)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\gpu-renderer\spec.md` (MODIFIED)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\gravitational-lensing\spec.md` (unchanged)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\celestial-background\spec.md` (unchanged)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\camera-system\spec.md` (unchanged)
- `C:\Projects\BlackholeSim\openspec\changes\core-renderer-01\specs\ui-shell\spec.md` (unchanged)
- `C:\Projects\BlackholeSim\docs\DESIGN.md`

**Next permitted action**: Ready for implementation tasks or proposal review.
