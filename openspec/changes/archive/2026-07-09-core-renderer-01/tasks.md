## 1. Project Setup

- [x] 1.1 Initialize Vite project with package.json and vite.config.js
- [x] 1.2 Create directory structure: src/renderer/, src/shaders/, src/camera/, src/ui/, src/utils/, assets/textures/
- [x] 1.3 Create index.html with canvas element and module script entry point
- [x] 1.4 Create src/main.js entry point with basic render loop (requestAnimationFrame, delta time)
- [x] 1.5 Create src/core/Constants.js with physical constants (G, c, M_sun, R_sun) and simulation units
- [x] 1.6 Create src/core/Clock.js with delta time calculation using performance.now()

## 2. GPU Renderer Abstraction

- [x] 2.1 Create src/renderer/Renderer.js with WebGPU/WebGL 2.0 detection and initialization
- [x] 2.2 Implement adapter/device request for WebGPU backend
- [x] 2.3 Implement WebGL 2.0 fallback context creation
- [x] 2.4 Create src/renderer/ShaderModule.js for shader compilation (WGSL and GLSL)
- [x] 2.5 Implement shader error reporting with line numbers and descriptions
- [x] 2.6 Create src/renderer/RenderPass.js for managing individual render passes
- [x] 2.7 Create src/renderer/FrameBuffer.js for offscreen framebuffer management
- [x] 2.8 Implement canvas sizing: fill container, respond to window resize within 100ms
- [x] 2.9 Create src/renderer/PostProcessor.js with bloom, ACES tonemap, FXAA, vignette stages
- [x] 2.10 Implement fullscreen quad geometry for post-processing passes

## 3. Gravitational Lensing Shader

- [x] 3.1 Create src/shaders/lensing.wgsl with vertex shader (fullscreen triangle)
- [x] 3.2 Implement ray-march loop (30 steps) with Schwarzschild deflection (α = Rs/r)
- [x] 3.3 Implement event horizon detection (ray enters r < Rs → black pixel)
- [x] 3.4 Implement photon sphere bright ring (rays near 1.5×Rs produce bright ring)
- [x] 3.5 Implement early termination for rays escaping scene bounds
- [x] 3.6 Implement dynamic black hole count (reads BH array from uniforms)
- [x] 3.7 Implement Kerr frame dragging (tangential deflection for spin > 0)
- [x] 3.8 Create src/shaders/lensing.glsl with equivalent GLSL version
- [x] 3.9 Add lensing uniforms: camera pos/dir, black hole data array, step count, resolution
- [x] 3.10 Test lensing renders correctly with single black hole and background

## 4. Particle Rendering

- [x] 4.1 Create src/shaders/particle.wgsl vertex shader (point sprite, position/velocity/color/size from buffers)
- [x] 4.2 Create src/shaders/particle.wgsl fragment shader (soft-circle texture, additive blend option)
- [x] 4.3 Implement particle buffer management (position, velocity, color, size arrays)
- [x] 4.4 Implement distance-based particle size attenuation
- [x] 4.5 Implement particle color from temperature (blue-white → white → yellow → orange → red)
- [x] 4.6 Implement additive blending mode for jet/glow particles
- [x] 4.7 Implement alpha blending mode for disk/debris particles
- [x] 4.8 Create src/renderer/ParticleRenderer.js that reads particle state from physics engine
- [x] 4.9 Create GLSL fallback versions of particle shaders
- [x] 4.10 Test: render 35K particles at 60fps on GTX

## 5. Body Rendering

- [x] 5.1 Create src/shaders/body.wgsl for solid body rendering (stars, neutron stars)
- [x] 5.2 Create src/objects/BodyRenderer.js that reads body state from physics engine
- [x] 5.3 Implement black hole silhouette rendering (dark circle + photon sphere glow ring)
- [x] 5.4 Implement star rendering (sphere with corona glow)
- [x] 5.5 Implement neutron star rendering (sphere with pulsar beams from magnetic poles)
- [x] 5.6 Implement body type dispatch (reads type enum, selects appropriate visual)
- [x] 5.7 Create GLSL fallback versions of body shaders

## 6. Celestial Background

- [x] 6.1 Obtain 1K equirectangular nebula HDR texture (NASA/Hubble public domain)
- [x] 6.2 Create src/shaders/starfield.wgsl with procedural star generation
- [x] 6.3 Implement deterministic star positioning via direction hash
- [x] 6.4 Implement star color temperature (blue-white, white, orange)
- [x] 6.5 Implement star twinkling (sinusoidal brightness variation)
- [x] 6.6 Implement parallax star layers (2 depth layers)
- [x] 6.7 Add star count uniform (configurable 1000-5000)
- [x] 6.8 Create src/shaders/starfield.glsl GLSL fallback version
- [x] 6.9 Integrate skybox sampling into lensing shader (background fallback when ray escapes)

## 7. Camera System

- [x] 7.1 Create src/camera/FreeCamera.js with spherical coordinates (theta, phi, distance)
- [x] 7.2 Implement left-drag orbit control with mouse event listeners
- [x] 7.3 Implement right-drag pan control
- [x] 7.4 Implement scroll wheel zoom with min/max distance constraints
- [x] 7.5 Implement critically-damped interpolation for smooth camera movement
- [x] 7.6 Implement camera constraints (elevation ±85°, min distance 2×Rs)
- [x] 7.7 Create src/camera/CinematicCamera.js with auto-orbit (configurable RPM)
- [x] 7.8 Implement 5 camera presets (cinematic, top-down, edge-on, close-up, system view)
- [x] 7.9 Implement smooth transition system (cubic ease-in-out, 1.5s duration)
- [x] 7.10 Create src/camera/CameraManager.js to switch between free/cinematic modes
- [x] 7.11 Implement WASD/QE keyboard movement controls
- [x] 7.12 Implement R key camera reset
- [x] 7.13 Implement click-to-focus with smooth transition

## 8. Adaptive Quality System

- [x] 8.1 Create src/utils/Profiler.js with rolling 60-frame FPS tracker
- [x] 8.2 Define 4 quality levels (Low/Medium/High/Auto) with settings for each
- [x] 8.3 Implement quality application: lensing resolution, step count, star count, post-processing
- [x] 8.4 Implement auto-adjustment: downgrade when FPS < 28 for 120 frames, upgrade when FPS > 55
- [x] 8.5 Add debounce: 120-frame cooldown between quality changes

## 9. UI Shell

- [x] 9.1 Create src/ui/UIManager.js orchestrator
- [x] 9.2 Create src/ui/PresetSelector.js with preset buttons (loads initial conditions into physics engine)
- [x] 9.3 Create src/ui/PhysicsInfo.js panel (mass, spin, Rs, FPS, particle count)
- [x] 9.4 Create src/ui/DisplayToggles.js (lensing, particles, stars, post-processing toggles)
- [x] 9.5 Create src/ui/QualitySelector.js (Low/Medium/High/Auto buttons)
- [x] 9.6 Create src/ui/KeyboardShortcuts.js overlay (appears 5s, fades, H to toggle)
- [x] 9.7 Style all UI components with CSS (semi-transparent panels over viewport)
- [x] 9.8 Implement responsive layout (desktop full labels, tablet icon-only)
- [x] 9.9 Add mute toggle button (visual only, placeholder for audio)
- [x] 9.10 Wire UI toggles to renderer settings

## 10. Scene Integration

- [x] 10.1 Create placeholder physics engine interface (getPosition, getVelocity, getParticleCount)
- [x] 10.2 Wire renderer to read BH positions from physics interface
- [x] 10.3 Wire renderer to read particle positions from physics interface
- [x] 10.4 Wire renderer to read body positions from physics interface
- [x] 10.5 Create placeholder preset loader (loads hardcoded initial state for testing)
- [x] 10.6 Test end-to-end: open browser, see black hole with particle disk, fly around, toggle UI

## 11. Polish & Testing

- [x] 11.1 Test on Chrome with WebGPU — verify lensing at 30+ fps
- [x] 11.2 Test on Chrome with WebGL 2.0 fallback — verify rendering works
- [x] 11.3 Test adaptive quality: verify auto-downgrade triggers on slow hardware
- [x] 11.4 Test camera presets: verify smooth transitions between all 5 presets
- [x] 11.5 Test UI toggles: verify each toggle correctly shows/hides its element
- [x] 11.6 Test window resize: verify canvas updates correctly
- [x] 11.7 Test tab visibility: verify rendering pauses and resumes correctly
- [x] 11.8 Optimize: profile with Chrome DevTools, identify bottlenecks
- [x] 11.9 Add vignette and final color grading to post-processing
- [x] 11.10 Verify total bundle size is under 500KB gzipped (excluding textures)
