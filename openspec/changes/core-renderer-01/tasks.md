## 1. Project Setup

- [ ] 1.1 Initialize Vite project with package.json and vite.config.js
- [ ] 1.2 Create directory structure: src/renderer/, src/shaders/, src/camera/, src/ui/, src/utils/, assets/textures/
- [ ] 1.3 Create index.html with canvas element and module script entry point
- [ ] 1.4 Create src/main.js entry point with basic render loop (requestAnimationFrame, delta time)
- [ ] 1.5 Create src/core/Constants.js with physical constants (G, c, M_sun, R_sun) and simulation units
- [ ] 1.6 Create src/core/Clock.js with delta time calculation using performance.now()

## 2. GPU Renderer Abstraction

- [ ] 2.1 Create src/renderer/Renderer.js with WebGPU/WebGL 2.0 detection and initialization
- [ ] 2.2 Implement adapter/device request for WebGPU backend
- [ ] 2.3 Implement WebGL 2.0 fallback context creation
- [ ] 2.4 Create src/renderer/ShaderModule.js for shader compilation (WGSL and GLSL)
- [ ] 2.5 Implement shader error reporting with line numbers and descriptions
- [ ] 2.6 Create src/renderer/RenderPass.js for managing individual render passes
- [ ] 2.7 Create src/renderer/FrameBuffer.js for offscreen framebuffer management
- [ ] 2.8 Implement canvas sizing: fill container, respond to window resize within 100ms
- [ ] 2.9 Create src/renderer/PostProcessor.js with bloom, ACES tonemap, FXAA, vignette stages
- [ ] 2.10 Implement fullscreen quad geometry for post-processing passes

## 3. Gravitational Lensing Shader

- [ ] 3.1 Create src/shaders/lensing.wgsl with vertex shader (fullscreen triangle)
- [ ] 3.2 Implement ray-march loop (30 steps) with Schwarzschild deflection (α = Rs/r)
- [ ] 3.3 Implement event horizon detection (ray enters r < Rs → black pixel)
- [ ] 3.4 Implement photon sphere bright ring (rays near 1.5×Rs produce bright ring)
- [ ] 3.5 Implement early termination for rays escaping scene bounds
- [ ] 3.6 Implement dynamic black hole count (reads BH array from uniforms)
- [ ] 3.7 Implement Kerr frame dragging (tangential deflection for spin > 0)
- [ ] 3.8 Create src/shaders/lensing.glsl with equivalent GLSL version
- [ ] 3.9 Add lensing uniforms: camera pos/dir, black hole data array, step count, resolution
- [ ] 3.10 Test lensing renders correctly with single black hole and background

## 4. Particle Rendering

- [ ] 4.1 Create src/shaders/particle.wgsl vertex shader (point sprite, position/velocity/color/size from buffers)
- [ ] 4.2 Create src/shaders/particle.wgsl fragment shader (soft-circle texture, additive blend option)
- [ ] 4.3 Implement particle buffer management (position, velocity, color, size arrays)
- [ ] 4.4 Implement distance-based particle size attenuation
- [ ] 4.5 Implement particle color from temperature (blue-white → white → yellow → orange → red)
- [ ] 4.6 Implement additive blending mode for jet/glow particles
- [ ] 4.7 Implement alpha blending mode for disk/debris particles
- [ ] 4.8 Create src/renderer/ParticleRenderer.js that reads particle state from physics engine
- [ ] 4.9 Create GLSL fallback versions of particle shaders
- [ ] 4.10 Test: render 35K particles at 60fps on GTX

## 5. Body Rendering

- [ ] 5.1 Create src/shaders/body.wgsl for solid body rendering (stars, neutron stars)
- [ ] 5.2 Create src/objects/BodyRenderer.js that reads body state from physics engine
- [ ] 5.3 Implement black hole silhouette rendering (dark circle + photon sphere glow ring)
- [ ] 5.4 Implement star rendering (sphere with corona glow)
- [ ] 5.5 Implement neutron star rendering (sphere with pulsar beams from magnetic poles)
- [ ] 5.6 Implement body type dispatch (reads type enum, selects appropriate visual)
- [ ] 5.7 Create GLSL fallback versions of body shaders

## 6. Celestial Background

- [ ] 6.1 Obtain 1K equirectangular nebula HDR texture (NASA/Hubble public domain)
- [ ] 6.2 Create src/shaders/starfield.wgsl with procedural star generation
- [ ] 6.3 Implement deterministic star positioning via direction hash
- [ ] 6.4 Implement star color temperature (blue-white, white, orange)
- [ ] 6.5 Implement star twinkling (sinusoidal brightness variation)
- [ ] 6.6 Implement parallax star layers (2 depth layers)
- [ ] 6.7 Add star count uniform (configurable 1000-5000)
- [ ] 6.8 Create src/shaders/starfield.glsl GLSL fallback version
- [ ] 6.9 Integrate skybox sampling into lensing shader (background fallback when ray escapes)

## 7. Camera System

- [ ] 7.1 Create src/camera/FreeCamera.js with spherical coordinates (theta, phi, distance)
- [ ] 7.2 Implement left-drag orbit control with mouse event listeners
- [ ] 7.3 Implement right-drag pan control
- [ ] 7.4 Implement scroll wheel zoom with min/max distance constraints
- [ ] 7.5 Implement critically-damped interpolation for smooth camera movement
- [ ] 7.6 Implement camera constraints (elevation ±85°, min distance 2×Rs)
- [ ] 7.7 Create src/camera/CinematicCamera.js with auto-orbit (configurable RPM)
- [ ] 7.8 Implement 5 camera presets (cinematic, top-down, edge-on, close-up, system view)
- [ ] 7.9 Implement smooth transition system (cubic ease-in-out, 1.5s duration)
- [ ] 7.10 Create src/camera/CameraManager.js to switch between free/cinematic modes
- [ ] 7.11 Implement WASD/QE keyboard movement controls
- [ ] 7.12 Implement R key camera reset
- [ ] 7.13 Implement click-to-focus with smooth transition

## 8. Adaptive Quality System

- [ ] 8.1 Create src/utils/Profiler.js with rolling 60-frame FPS tracker
- [ ] 8.2 Define 4 quality levels (Low/Medium/High/Auto) with settings for each
- [ ] 8.3 Implement quality application: lensing resolution, step count, star count, post-processing
- [ ] 8.4 Implement auto-adjustment: downgrade when FPS < 28 for 120 frames, upgrade when FPS > 55
- [ ] 8.5 Add debounce: 120-frame cooldown between quality changes

## 9. UI Shell

- [ ] 9.1 Create src/ui/UIManager.js orchestrator
- [ ] 9.2 Create src/ui/PresetSelector.js with preset buttons (loads initial conditions into physics engine)
- [ ] 9.3 Create src/ui/PhysicsInfo.js panel (mass, spin, Rs, FPS, particle count)
- [ ] 9.4 Create src/ui/DisplayToggles.js (lensing, particles, stars, post-processing toggles)
- [ ] 9.5 Create src/ui/QualitySelector.js (Low/Medium/High/Auto buttons)
- [ ] 9.6 Create src/ui/KeyboardShortcuts.js overlay (appears 5s, fades, H to toggle)
- [ ] 9.7 Style all UI components with CSS (semi-transparent panels over viewport)
- [ ] 9.8 Implement responsive layout (desktop full labels, tablet icon-only)
- [ ] 9.9 Add mute toggle button (visual only, placeholder for audio)
- [ ] 9.10 Wire UI toggles to renderer settings

## 10. Scene Integration

- [ ] 10.1 Create placeholder physics engine interface (getPosition, getVelocity, getParticleCount)
- [ ] 10.2 Wire renderer to read BH positions from physics interface
- [ ] 10.3 Wire renderer to read particle positions from physics interface
- [ ] 10.4 Wire renderer to read body positions from physics interface
- [ ] 10.5 Create placeholder preset loader (loads hardcoded initial state for testing)
- [ ] 10.6 Test end-to-end: open browser, see black hole with particle disk, fly around, toggle UI

## 11. Polish & Testing

- [ ] 11.1 Test on Chrome with WebGPU — verify lensing at 30+ fps
- [ ] 11.2 Test on Chrome with WebGL 2.0 fallback — verify rendering works
- [ ] 11.3 Test adaptive quality: verify auto-downgrade triggers on slow hardware
- [ ] 11.4 Test camera presets: verify smooth transitions between all 5 presets
- [ ] 11.5 Test UI toggles: verify each toggle correctly shows/hides its element
- [ ] 11.6 Test window resize: verify canvas updates correctly
- [ ] 11.7 Test tab visibility: verify rendering pauses and resumes correctly
- [ ] 11.8 Optimize: profile with Chrome DevTools, identify bottlenecks
- [ ] 11.9 Add vignette and final color grading to post-processing
- [ ] 11.10 Verify total bundle size is under 500KB gzipped (excluding textures)
