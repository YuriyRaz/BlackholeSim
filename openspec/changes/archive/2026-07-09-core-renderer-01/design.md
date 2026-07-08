## Context

Greenfield project — no existing codebase. Building a 3D black hole simulation from scratch using WebGPU/WebGL 2.0. The renderer is a pure visualization layer: it reads positions, velocities, and properties from the physics engine and draws them. It has no knowledge of what is being simulated.

Key constraints:
- Browser-based, no native app or game engine
- WebGPU primary, WebGL 2.0 fallback
- Must run 30+ fps on Intel HD 620 (integrated GPU)
- Single developer, ~15 days for this proposal

## Goals / Non-Goals

**Goals:**
- Complete, runnable application after this proposal
- Gravitational lensing at 30+ fps on integrated GPUs
- Camera that feels delightful — smooth, responsive, cinematic
- UI that lets users control the experience
- Adaptive quality that adjusts to hardware
- Architecture that cleanly supports the physics engine (Proposal 2)

**Non-Goals:**
- Physics simulation — Proposal 2
- Particle systems — particles are managed by the physics engine, renderer just draws them
- Accretion disk shader — disk is particles from physics engine
- Audio — Proposal 4
- Mobile/touch controls — Proposal 4

## Decisions

### D1: WebGPU Primary, WebGL 2.0 Fallback

**Decision**: Use WebGPU as the primary rendering backend with automatic fallback to WebGL 2.0.

**Why**: WebGPU provides compute shaders (critical for future particle physics), better memory management, and modern pipeline design. WebGL 2.0 ensures universal browser support.

**Implementation**: `Renderer.js` detects `navigator.gpu`, requests adapter/device. If unavailable, creates WebGL 2.0 context. Both backends implement the same interface.

### D2: Screen-Space Ray-Marching for Lensing (Not Full GR)

**Decision**: Use post-Newtonian weak-field approximation for gravitational lensing, not exact geodesic integration.

**Why**: Exact GR requires ~20K FLOPS per pixel — impossible on integrated GPUs. Our approximation uses α = Rs/r for deflection — ~90 FLOPS/pixel, 200× cheaper and visually indistinguishable.

**Implementation**: Fragment shader loops 30 times per pixel. Each step: distance to BH, deflection angle α = Rs/r, bend ray. Early termination when far from BHs.

### D3: Half-Resolution Lensing with Bilateral Upsample

**Decision**: Render lensing at half resolution then upsample with edge-aware bilateral filter.

**Why**: Lensing is the bottleneck. Half resolution = 1/4 pixels. Bilateral filter preserves edges (shadow boundary) while smoothing smooth areas.

**Implementation**: Render lensing to half-size FBO. Bilateral upsample shader. Quality selector toggles this.

### D4: Particle-Based Disk (Not Geometric Mesh)

**Decision**: Render the accretion disk as GPU particles from the physics engine, not as a geometric ring with a shader.

**Why**: A geometric mesh with fake temperature/Doppler is a visual prop — it doesn't evolve, respond to physics, or change shape. A particle-based disk emerges from the physics: gas particles orbit the BH, form a disk through angular momentum conservation, and their distribution/temperature is computed by the physics engine. The renderer just draws the particles.

**Alternatives considered**:
- Geometric ring with shader: Simpler, but static and fake. No physics interaction.
- Volumetric ray-march through disk: Most realistic, but too expensive for real-time.

**Implementation**: The physics engine manages gas particles with position, velocity, temperature. The renderer reads these arrays and draws point sprites. Temperature maps to color. The lensing shader checks for ray-particle intersection to bend disk light.

### D5: Vite as Build Tool

**Decision**: Vite for dev server and production bundling.

**Why**: Fastest dev server, native ES module support, optimized production builds.

### D6: No Three.js Dependency

**Decision**: Custom renderer without Three.js.

**Why**: Three.js adds ~500KB and abstracts away control we need for half-resolution lensing, custom render passes, WebGPU/WebGL abstraction.

### D7: CSS-First UI

**Decision**: Vanilla HTML/CSS/JS, no framework.

**Why**: UI is simple (buttons, panels, overlays). Framework adds overhead for minimal benefit.

## Risks / Trade-offs

- **Lensing too slow on Intel HD 4000** → Half-resolution already planned. Can reduce steps to 15. Fallback: simple billboard with distortion ring.
- **WebGPU not in Safari** → WebGL 2.0 fallback works fine. Graceful degradation.
- **No Three.js means more code** → We only need ~200 lines for minimal scene graph. Trade-off worth it for control.

## Open Questions

1. Nebula texture source — NASA/Hubble public domain images
2. Shader language parity — WGSL and GLSL maintained separately, GLSL may lag
3. Canvas resolution — cap at devicePixelRatio 1.0 or support high-DPI?
