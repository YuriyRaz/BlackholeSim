# J004 Report: Create Proposal for physics-engine-02

## Status: completed

## Summary

The physics-engine-02 proposal has been updated to address all 7 concerns from the exploration phase. The proposal now includes simulation unit specification, timeline scrubber state snapshots, jet particle lifecycle rules, star particle count algorithm, explicit physics-to-renderer data contract, WebGPU status clarification, and ui-shell modification scope boundaries.

## Changes Made

### 1. Proposal Updated (proposal.md)
- Added **Simulation Units** section defining SI units (meters, kilograms, seconds) with Constants.js values
- Added **Coordinate mapping** explanation: camera auto-scales based on scene bounding box
- Added **Physical values in formulas** clarification: display values show physical units with conversions
- Clarified **Timeline scrubber**: state snapshots approach, O(N/100) recomputation
- Clarified **Performance**: WebGPU compute shaders not implemented, physics runs on CPU

### 2. Accretion-Physics Spec Updated
- Added **Jet particle lifecycle** requirement:
  - Removal at 200×Rs distance
  - Maximum 2,000 simultaneous jet particles
  - FIFO eviction when limit reached
  - Non-interacting (no gravity, no collisions)

### 3. Tidal-Disruption Spec Updated
- Added **Star particle count algorithm** requirement:
  - N = clamp(floor(mass / 0.1×M_sun), 50, 500)
  - Uniform spherical distribution via rejection sampling
  - Velocity perturbation on disruption (±10% orbital velocity)

### 4. Time-Controls Spec Updated
- Updated **Timeline scrubber** requirement:
  - Snapshots every 100 steps
  - Maximum 100 snapshots (FIFO)
  - Scrub recomputes from nearest prior snapshot (max 100 steps)
  - Forward scrub beyond last snapshot runs physics forward

### 5. Design Doc Updated
- Added **D6: Physics-to-Renderer Data Contract** decision
  - Explicit format: bodies[], gasParticles[], jetParticles[], gw, accretionRate, simTime
  - Maps to existing ParticleRenderer/BodyRenderer expectations
- Added **D7: UI-Shell Modifications Scope** decision
  - Time controls, object list, expanded info panel are physics-engine-02 scope
  - Base ui-shell (preset selector, toggles, quality) is core-renderer-01 scope

### 6. Tasks Updated
- Added task 1.5: getState() returns data contract format
- Added tasks 4.12-4.13: jet particle lifecycle and non-interaction
- Added task 5.3: star particle count generation algorithm
- Added task 11.5: state snapshot mechanism
- Updated task 11.7: scrubber uses nearest snapshot

## Concerns Resolved

| ID | Concern | Resolution |
|----|---------|------------|
| C1 | Unit normalization | SI units defined, coordinate mapping explained |
| C2 | Timeline scrubber performance | State snapshots (100 steps), max 100 snapshots |
| C3 | Jet particle lifecycle | Removal at 200×Rs, max 2,000 particles, FIFO |
| C4 | Star particle count | Algorithm: N = clamp(floor(mass/0.1Msun), 50, 500) |
| C5 | Physics-to-renderer data contract | Explicit format in design.md |
| C6 | WebGPU backend | Noted CPU-only, no compute shaders |
| C7 | ui-shell scope | Clear boundaries defined |

## Artifacts Modified
- `openspec/changes/physics-engine-02/proposal.md`
- `openspec/changes/physics-engine-02/design.md`
- `openspec/changes/physics-engine-02/tasks.md`
- `openspec/changes/physics-engine-02/specs/accretion-physics/spec.md`
- `openspec/changes/physics-engine-02/specs/tidal-disruption/spec.md`
- `openspec/changes/physics-engine-02/specs/time-controls/spec.md`

## Checkpoint Summary

The physics-engine-02 proposal is now complete with all concerns addressed. The proposal is ready for implementation. Dependencies on core-renderer-01 are satisfied. All 11 spec files have been reviewed and updated where needed. The task breakdown is complete with 129 tasks across 12 sections.
