# J007 Report — visual-effects-03 Proposal Finalization

## Status: completed

## Changes Made

### proposal.md
- Added **Dependencies** section documenting required physics-engine-02 changes (bhPairs in getState(), particleTrails buffer)
- Added `timeline-controls` as a Modified Capability
- Added WebGPU note to Impact section

### design.md
- Updated **D2 (Merger Flash)**: Now references `bhPairs` from `PhysicsEngine.getState()` instead of computing distances in renderer
- Added **D5 (Particle Trails as Extended TrailRenderer)**: Clarifies architecture — extend existing TrailRenderer rather than creating new renderer; physics engine stores particleTrails buffer; trail color derived from temperature
- Added WebGPU risk to Risks section
- Added Open Question #3 about particle trail color source

### specs/merger-flash/spec.md
- Added **Requirement: bhPairs exposed in physics state** — physics engine must include bhPairs in getState() output
- Updated scenarios to reference `bhPairs[].distance`

### specs/particle-trails/spec.md
- Clarified that existing `TrailRenderer` SHALL be extended for both body and particle trails
- Added **Requirement: Particle trail history buffer** — physics engine must maintain particleTrails buffer
- Added **Requirement: WebGPU trail fallback** — GL-only for MVP, WebGPU follow-up
- Updated trail color requirement to reference temperature-to-color mapping

### specs/gpu-particles/spec.md
- Added scenario: **Color mapping in shader** — temperature-to-color mapping happens in fragment shader, not JS

### specs/gw-visualization/spec.md
- Added **Requirement: WebGW ripple implementation** — LensingPass already has both GL and WebGPU init methods; GW uniforms added to both

### tasks.md
- **Section 2 (Merger Flash)**: Split BH proximity detection into bhPairs computation (2.1) and getState() exposure (2.2)
- **Section 3 (Particle Trails)**: Added physics buffer tasks (3.1, 3.2), extended TrailRenderer task (3.3), temperature color in shader (3.5)
- **Section 5 (UI Integration)**: Removed 5.6 (moved to new section)
- **Section 6 (Timeline Scrubber)**: NEW — 6 tasks covering snapshot cache, scrub UI, interpolation, pause/play, memory management
- **Section 7 (GPU Particle Temperature Mapping)**: NEW — 3 tasks covering temperature attribute, shader mapping, trail color
- **Section 8 (Testing)**: Renumbered from 6, added timeline scrubber test (8.7), temperature-to-color test (8.8)

## Gaps Addressed

| Gap | Resolution |
|-----|-----------|
| G1: Timeline scrubber not in tasks | Added dedicated Section 6 with 6 tasks |
| G2: bhPairs not exposed in getState() | Added requirement in merger-flash spec, task in Section 2, dependency in proposal |
| G3: WebGPU path gaps | Documented as follow-up in design risks; GW ripples have WebGPU path; particle trails GL-only for MVP |
| G4: Particle trail architecture unclear | Added D5 decision extending TrailRenderer; physics stores particleTrails buffer |
| G5: Phase indicator hardcoded labels | Already addressed by existing spec (derived state); no change needed |
| G6: Particle temperature-to-color | Added shader-based mapping requirement in gpu-particles spec; added task Section 7 |
| G7: Merger flash decay timer | Addressed by bhPairs-based approach with 0.5s decay in bloom pipeline |

## Task Count

- Original: 53 line items
- Updated: 62 line items (+9 for timeline scrubber, particle trail physics buffer, bhPairs, temperature mapping)

## Artifacts Updated

- `openspec/changes/visual-effects-03/proposal.md`
- `openspec/changes/visual-effects-03/design.md`
- `openspec/changes/visual-effects-03/tasks.md`
- `openspec/changes/visual-effects-03/specs/merger-flash/spec.md`
- `openspec/changes/visual-effects-03/specs/particle-trails/spec.md`
- `openspec/changes/visual-effects-03/specs/gpu-particles/spec.md`
- `openspec/changes/visual-effects-03/specs/gw-visualization/spec.md`
