## Why

We are building an interactive 3D black hole simulation. The renderer is the foundation — it takes positions, velocities, and physical properties from the physics engine and draws them. It has no opinions about what is simulating. It doesn't know about "scenarios" or "phases." It just reads state and renders it.

The gravitational lensing shader is the most technically risky component — it must run at 30+ fps on integrated GPUs. Proving this early de-risks the entire project.

## What Changes

- **WebGPU/WebGL 2.0 rendering abstraction**: Cross-platform GPU backend with automatic fallback.
- **Gravitational lensing shader**: Screen-space ray-march through approximated Schwarzschild metric. Handles any number of black holes — reads BH positions from physics state.
- **Particle rendering**: Point-sprite rendering for any particle type (gas, debris, jet, test). Reads position, temperature/color, size from physics state. No knowledge of particle type.
- **Body rendering**: Spheres for stars, black hole silhouettes with photon sphere glow, neutron star pulsar beams. Reads body type and properties from physics state.
- **Procedural starfield + nebula skybox**: Equirectangular nebula texture with layered procedural star shader.
- **Post-processing pipeline**: Selective bloom, ACES filmic tone mapping, FXAA, vignette.
- **Free camera with smooth damping**: Orbit, pan, zoom with critically-damped interpolation.
- **Cinematic camera presets**: Auto-orbit with preset angles and smooth transitions.
- **Adaptive quality system**: Monitors FPS, auto-downgrades lensing resolution and ray-march steps.
- **Minimal UI**: Preset selector (loads initial conditions into physics engine), physics info panel, display toggles, quality selector, camera controls.

## Capabilities

### New Capabilities

- `gpu-renderer`: WebGPU/WebGL 2.0 abstraction, render pipeline, shader compilation, framebuffer management, post-processing.
- `gravitational-lensing`: Screen-space ray-marching shader. Reads BH positions/count from physics state. Handles any number of BHs dynamically.
- `particle-renderer`: Point-sprite rendering for arbitrary particles. Reads position, color, size from physics state. No knowledge of particle type.
- `body-renderer`: Renders celestial bodies (stars, BHs, neutron stars) from physics state. Handles silhouettes, coronas, pulsar beams.
- `celestial-background`: Procedural starfield over nebula skybox.
- `camera-system`: Free orbit/pan/zoom with damping, cinematic auto-orbit, preset angles.
- `adaptive-quality`: Performance monitoring and automatic quality adjustment.
- `ui-shell`: Preset selector, physics info panel, display toggles, quality selector, camera controls.

### Modified Capabilities

<!-- None — this is a greenfield project. -->

## Impact

- **New project**: All code is greenfield.
- **Technology stack**: Vite, WebGPU + WGSL, WebGL 2.0 + GLSL, Web Audio API (placeholder).
- **Asset dependencies**: 1K nebula texture, star corona sprite, particle soft-circle sprite.
- **Performance target**: 30+ fps on Intel HD 620, 60fps on NVIDIA GTX.
- **No accretion disk shader**: Disk is rendered as particles from the physics engine.
- **No scenario-specific code**: Renderer is a general visualization layer.
