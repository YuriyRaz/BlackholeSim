# Black Hole Simulation — Design Document

## 1. Project Overview

An interactive 3D black hole simulation that visualizes gravitational phenomena in real-time on consumer hardware. The user can fly around black holes, watch stars get torn apart, observe two black holes spiral and merge, and see accretion disks form — all driven by physics equations, not scripted animations.

**Core principle**: Every visual effect emerges from the physics. There are no hardcoded scenarios, no scripted phase transitions, no special-case code for "what happens during a merger." The physics engine computes positions, the renderer draws them. Effects are consequences of the equations.

**Tech stack**: WebGPU (primary) + WebGL 2.0 (fallback), custom WGSL/GLSL shaders, Vite build tool, vanilla JS UI. No Three.js, no game engine, no physics library.

**Performance target**: 30+ fps on Intel HD 620 (2012 integrated GPU), 60fps on NVIDIA GTX. Half-resolution lensing fallback for weak GPUs.

---

## 2. Architecture

### 2.1 Separation of Concerns

The system has four layers, each with a single responsibility:

```
┌─────────────────────────────────────────────────────────────────┐
│  RENDERER (Proposal 1)                                          │
│  Reads positions, velocities, temperatures from physics engine. │
│  Draws them. Has no knowledge of what is being simulated.       │
│  No scenario code, no physics logic, no event handling.         │
├─────────────────────────────────────────────────────────────────┤
│  PHYSICS ENGINE (Proposal 2)                                    │
│  Computes gravitational forces, gas dynamics, tidal forces,     │
│  GW emission, accretion, jets. Has no concept of "scenarios"    │
│  or "phases." Just simulates physics given initial conditions.  │
├─────────────────────────────────────────────────────────────────┤
│  VISUAL EFFECTS (Proposal 3)                                    │
│  GW ripples, merger flash, particle trails, phase indicator.    │
│  All triggered by physics state, not by scenario events.        │
├─────────────────────────────────────────────────────────────────┤
│  AUDIO + POLISH (Proposal 4)                                    │
│  Reads gwFrequency, accretion rate, BH proximity from physics.  │
│  No scenario-specific audio. Touch controls, loading, post-fx.  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
Physics Engine (CPU)          Renderer (GPU)
═══════════════════          ═══════════════
bodies[]         ───────►   body-renderer (spheres, silhouettes)
gasParticles[]   ───────►   particle-renderer (point sprites)
jetParticles[]   ───────►   particle-renderer (additive blend)
bhPositions[]    ───────►   gravitational-lensing (ray-march)
gwFrequency      ───────►   gw-visualization (ripple shader)
gwStrain         ───────►   audio-engine (GW sonification)
accretionRate    ───────►   event-sounds (accretion whoosh)
body.disrupted   ───────►   event-sounds (disruption crackle)
```

### 2.3 Presets (Not Scenario Classes)

Initial conditions are **data functions**, not classes with state machines:

```javascript
// A preset is just a function that returns data
function setupBinaryBH() {
  return {
    bodies: [
      { type: 'blackhole', mass: 36, position: [...], velocity: [...], spin: 0 },
      { type: 'blackhole', mass: 29, position: [...], velocity: [...], spin: 0 }
    ],
    gas: [],
    camera: { target: [0,0,0], distance: 100 }
  };
}
```

The physics engine doesn't know about "Binary BH" or "TDE." It just receives bodies and gas, and computes forces. Mergers happen when BHs get close. Disruptions happen when stars get too close. Jets happen when gas reaches ISCO around a spinning BH. All consequences of the same equations.

---

## 3. Physics Concepts

### 3.1 Gravitational Lensing

**What the user sees**: Background stars distort around the black hole. Einstein rings form. The far side of the accretion disk wraps over/under the BH shadow. A bright photon sphere ring appears at 1.5×Rs.

**How it works**: Screen-space ray-marching through an approximated Schwarzschild metric. Each pixel traces a ray from the camera. At each step, the ray is deflected toward the black hole by angle α = Rs/r, where Rs is the Schwarzschild radius and r is the distance to the BH center.

**Key formulas**:
- Schwarzschild radius: Rs = 2GM/c²
- Deflection angle (weak field): α = Rs/r per step
- Ray update: direction += α × (toward_BH) × dt

**Why not full GR**: Exact geodesic integration requires ~20K FLOPS per pixel. Our approximation uses ~90 FLOPS per pixel — 200× cheaper, visually indistinguishable at interactive frame rates.

**Performance trick**: Render lensing at half resolution (540p), upsample with bilateral filter. Processes 1/4 the pixels. Bilateral filter preserves edges (shadow boundary) while smoothing smooth areas.

### 3.2 Schwarzschild Black Holes

Non-rotating black holes described by a single parameter: mass M.

- Event horizon radius: Rs = 2GM/c²
- Photon sphere: r_ph = 1.5 × Rs (unstable circular orbit for light)
- ISCO (innermost stable circular orbit): r_isco = 3 × Rs = 6GM/c²

Any object crossing Rs cannot escape. Objects inside r_ph have orbits that decay. Objects inside r_isco have no stable orbits — they plunge.

### 3.3 Kerr Black Holes (Spinning)

Rotating black holes described by mass M and spin parameter a* = Jc/(GM²), where J is angular momentum. a* ranges from 0 (Schwarzschild) to 1 (maximal Kerr).

**Spin effects**:
- ISCO shifts inward: r_isco = 6Rs for a*=0, down to 1Rs for a*=1 (prograde)
- Ergosphere forms: oblate region outside event horizon where spacetime is dragged
- Frame dragging: orbiting objects precess in the direction of BH spin
- Jets: Blandford-Znajek process extracts energy from spin via magnetic fields

**Ergosphere boundary**: r_ergo = Rs × (1 + √(1 - a*² × cos²θ)), where θ is the polar angle. At the equator (θ=90°), the ergosphere extends to 2Rs. At the poles (θ=0°), it meets the event horizon.

### 3.4 Accretion Disks

When gas with angular momentum falls toward a black hole, it forms a disk rather than falling directly in. The disk structure emerges from the physics:

1. **Gas particles orbit the BH** under gravity
2. **Viscous interactions** transport angular momentum outward
3. **Inner particles lose angular momentum** and migrate inward
4. **Outer particles gain angular momentum** and spread outward
5. **Particles inside ISCO plunge** into the BH (accretion)
6. **Temperature** derives from orbital velocity: T ∝ v² (inner = hot, outer = cool)

**Disk properties**:
- Inner edge: ISCO (depends on BH spin)
- Temperature profile: T(r) ∝ r^(-3/4) ( Shakura-Sunyaev thin disk)
- Luminosity: L = η × Ṁ × c², where η ≈ 0.1 (radiative efficiency)
- Accretion rate: Ṁ = dM/dt (mass accreted per unit time)

### 3.5 Tidal Disruption Events (TDEs)

When a star approaches too close to a black hole, tidal forces exceed the star's self-gravity and tear it apart.

**Roche limit**: d_R = R_star × (2 × M_BH / M_star)^(1/3)

For a Sun-like star and a 10⁶ M☉ BH: d_R ≈ 7 × R_sun × (2 × 10⁶)^(1/3) ≈ 6.2 × 10¹¹ m

**What happens**:
1. Star approaches on eccentric orbit
2. At 1.5× d_R: star deforms into prolate spheroid (2:1 aspect ratio)
3. At d_R: star disrupts into tidal stream
4. Near-side particles orbit faster, far-side slower → stream wraps BH
5. ~50% of debris is bound → circularizes into accretion disk
6. ~50% is unbound → escapes the system
7. Peak luminosity at T_fallback (orbital period of most bound debris)
8. Fallback rate decays as t^(-5/3) (power law)

### 3.6 Binary Black Hole Mergers

Two black holes spiral together, emitting gravitational waves that carry away energy and angular momentum.

**Inspiral phase**: Orbital decay from Peters formula:
da/dt = -(64/5) × G³ × m1 × m2 × (m1+m2) / (c⁵ × a³)

As separation decreases, orbital frequency increases (chirp). GW frequency = 2 × orbital frequency (quadrupole radiation).

**Merger**: When separation < few Rs, the black holes merge into a single remnant. ~5% of total mass is radiated as gravitational waves. GW150914 (first LIGO detection): 36+29 M☉ → 62 M☉ remnant, ~3 M☉ radiated.

**Ringdown**: The remnant oscillates (quasi-normal mode) with frequency:
f_QNM ≈ c³/(2π × GM) × (1 - 0.63 × (1-a*)^0.3)

Damps exponentially over ~0.2 seconds.

### 3.7 Gravitational Waves

Ripples in spacetime caused by accelerating masses. Any accelerating mass pair emits GWs.

**Key formulas**:
- Chirp mass: M_chirp = (m1 × m2)^(3/5) / (m1 + m2)^(1/5)
- GW frequency: f_GW = 2 × f_orbital (for circular orbits)
- Strain: h = (4/d) × (GM_chirp/c²)^(5/3) × (πf_GW/c)^(2/3)
- Luminosity: L_GW = (32/5) × G⁴ × m1² × m2² × (m1+m2) / (c⁵ × a⁵)

**Energy loss drives orbital decay**: The binary loses energy to GWs, causing the orbit to shrink, which increases the GW frequency — the characteristic "chirp."

### 3.8 Relativistic Jets

Collimated beams of plasma ejected along the spin axis of a black hole. Powered by the Blandford-Znajek process: magnetic fields anchored in the accretion disk extract rotational energy from the spinning BH.

**Simplified model**: When gas reaches ISCO around a spinning BH, a fraction (proportional to a*²) is redirected along the spin axis.

- Jet power: P_jet ∝ a*² × Ṁ (Blandford-Znajek proportionality)
- Jet velocity: 0.9-0.99c (relativistic)
- Opening angle: 5-10° (collimated)
- Color: blue-white core (hot, fast), redder sheath (cooler, slower)
- Precession: wobbles for tilted BH spin axis (frame dragging)

**Visual**: Bipolar cones of particles emitted from inner disk edge, using additive blending for glow effect.

### 3.9 Frame Dragging

A spinning black hole drags spacetime around with it. Orbiting objects precess in the direction of the BH spin.

- Inner particles precess faster (stronger frame dragging)
- Outer particles precess slower (weaker frame dragging)
- Precession rate: Ω_drag ∝ a* × (Rs/r)³

### 3.10 ISCO (Innermost Stable Circular Orbit)

The innermost orbit where a test particle can maintain a stable circular orbit. Inside ISCO, orbits are unstable — particles spiral inward (plunge).

- Schwarzschild (a*=0): r_isco = 6 × Rs = 12GM/c²
- Maximal Kerr (a*=1): r_isco = 1 × Rs = 2GM/c² (prograde)

This defines the inner edge of the accretion disk.

---

## 4. Visual Effects Design

### 4.1 Gravitational Lensing

The lensing shader ray-marches from the camera through warped spacetime. At each pixel:

1. Cast ray from camera through pixel
2. Loop 30 times:
   a. Compute distance to each BH
   b. Compute deflection: α = Rs/r
   c. Bend ray toward BH
   d. If ray enters Rs → black pixel (event horizon)
   e. If ray is near 1.5×Rs → bright pixel (photon sphere)
3. If ray escapes → sample background (nebula/stars)

### 4.2 Accretion Disk Rendering

The accretion disk is NOT a geometric mesh. It is a collection of gas particles rendered as point sprites.

- Each particle: position, velocity, temperature, size
- Color from temperature: blue-white (hot) → red (cool)
- Lensing shader bends light from disk particles (ray-particle intersection)
- Disk shape emerges from particle distribution

### 4.3 Gravitational Wave Ripples

Concentric distortion rings in the lensing shader, driven by gwStrain from physics.

- Add sinusoidal deflection to ray direction during ray-march
- Amplitude ∝ gwStrain × (1/r) (distance decay)
- Frequency = gwFrequency from physics engine
- Fade after gwStrain drops to zero

### 4.4 Merger Flash

Bloom intensity spike when two BHs are within 5×Rs.

- Compute BH pair distances each frame
- Flash intensity ∝ 1/distance (when distance < 5×Rs)
- Decay over 0.5 seconds after merge
- Implemented as temporary bloom multiplier in post-processing

### 4.5 Relativistic Jets

Bipolar particle streams along BH spin axis, emitted from inner disk.

- Jet particles are emitted by physics engine (inner disk gas + spin)
- Renderer draws them as point sprites with additive blending
- Blue-white on-axis, redder off-axis
- Precesses for tilted BH spin axis

### 4.6 Particle Trails

Fading line segments showing particle trajectory history.

- Store last N positions per particle (configurable, max 50)
- Render as GL_LINE_STRIP with fading alpha
- Color matches particle color
- Toggleable via UI

---

## 5. Shader Design

### 5.1 Lensing Shader (lensing.wgsl)

```
Input: camera position/direction, BH positions/masses/spins, time
Output: color for each pixel

Algorithm:
  ray = camera_ray_through_pixel(pixel)
  color = background_sample(ray)
  
  for each BH:
    for step in 0..30:
      dist = distance(ray.origin, BH.position)
      if dist < Rs: return black
      if dist < 1.5*Rs: return photon_sphere_glow
      deflection = Rs/dist
      ray.direction += deflection * normalize(BH.position - ray.origin)
      ray.origin += ray.direction * step_size
  
  return color
```

### 5.2 Particle Shader (particle.wgsl)

```
Input: position buffer, velocity buffer, color buffer, size buffer
Output: rendered point sprites

Vertex shader:
  gl_Position = mvp * vec4(position, 1.0)
  gl_PointSize = size / distance(position, camera)

Fragment shader:
  dist = length(gl_PointCoord - 0.5)
  if dist > 0.5: discard
  alpha = 1.0 - smoothstep(0.3, 0.5, dist)
  gl_FragColor = vec4(color, alpha)
```

### 5.3 GW Ripple Extension

```
// Added to lensing shader
if gwStrain > 0.0:
  dist_to_source = distance(ray.origin, gwSourcePosition)
  ripple = sin(2.0 * PI * gwFrequency * time - dist_to_source * 0.1)
  ripple_amplitude = gwStrain * 0.01 / max(dist_to_source, 1.0)
  ray.direction += normalize(ripple_perpendicular) * ripple * ripple_amplitude
```

---

## 6. Performance Design

### 6.1 Adaptive Quality

Monitors FPS over rolling 60-frame window. Auto-adjusts:

| Quality | Lensing Res | Ray Steps | Max Particles | Post-FX |
|---------|------------|-----------|---------------|---------|
| Low     | Half (540p)| 15        | 12,000        | Bloom only |
| Medium  | Half (540p)| 20        | 20,000        | Bloom + FXAA |
| High    | Full (1080p)| 30       | 35,000        | All effects |
| Auto    | Adjusts based on FPS | | | |

### 6.2 Particle Budget

- Gas particles (accretion disk): ~200-500
- Jet particles: ~500-2000 per jet
- Tidal stream particles: ~1000-5000
- Merger debris: ~5000-10000
- Test particles: ~50-200
- Total budget: 12K-35K (quality dependent)

### 6.3 Physics Performance

- N-body gravity: O(n log n) with Barnes-Hut tree (activated >100 bodies)
- Gas particle integration: same Velocity Verlet, gas-gas gravity disabled
- Viscous torque: O(n) per frame
- Accretion detection: O(n) per frame
- Total: <5ms per physics step with 500 gas + 10 bodies

### 6.4 Lensing Performance

- Full resolution (1080p) × 30 steps × 4 BHs = ~129M operations/frame
- Half resolution (540p) × 20 steps × 4 BHs = ~17M operations/frame
- Early termination when ray is far from BHs: ~30% reduction
- WebGPU compute: ~2× faster than WebGL 2.0 fragment shader

---

## 7. Data Model

### 7.1 Bodies

```javascript
{
  type: 'blackhole' | 'star' | 'neutronstar',
  mass: float,           // solar masses
  position: [x, y, z],   // simulation units
  velocity: [x, y, z],   // simulation units
  spin: float,            // a* (0 to 1), only for black holes
  radius: float,          // for rendering and tidal calculations
  fixed: boolean,         // true = doesn't move (massive BH)
  disrupted: boolean,     // true = tidal disruption occurred
  temperature: float,     // for stars
  disruptedParticles: []  // particles after disruption
}
```

### 7.2 Gas Particles

```javascript
{
  position: [x, y, z],
  velocity: [x, y, z],
  temperature: float,     // derived from orbital velocity
  mass: float,            // particle mass
  accreted: boolean,      // true = removed (plunged into BH)
  jet: boolean            // true = redirected as jet particle
}
```

### 7.3 Physics State Exposed to Renderer

```javascript
{
  bodies: [...],
  gasParticles: [...],
  jetParticles: [...],
  gwFrequency: float,
  gwStrain: float,
  gwPhase: float,
  accretionRate: float,
  bhPairs: [{ a: index, b: index, distance: float }]
}
```

---

## 8. Initial Condition Presets

### 8.1 Binary Black Hole (GW150914-inspired)

- Primary: 36 M☉ BH at (-10×Rs, 0, 0) with circular orbit velocity
- Secondary: 29 M☉ BH at (10×Rs, 0, 0) with circular orbit velocity
- Separation: 20×Rs of total mass
- No gas particles
- Expected evolution: inspiral → merger → ringdown (emerges from GW energy loss)

### 8.2 Tidal Disruption Event

- BH: 10⁶ M☉ at origin, fixed
- Star: 1 M☉, 1 R☉ on eccentric orbit (e=0.9)
- Periapsis: inside Roche limit
- Expected evolution: approach → disruption → tidal stream → disk formation → jet (emerges from tidal forces + gas dynamics)

### 8.3 Kerr Black Hole

- BH: 10 M☉ with spin a*=0.998 at origin, fixed
- Gas: 100 particles on circular orbits between 10-50×Rs
- Expected evolution: frame dragging, ISCO plunge, disk spreading, jet emission (emerges from spin + gas dynamics)

### 8.4 Custom

- User places arbitrary bodies and gas via UI controls
- Physics engine handles everything

---

## 9. Design Decisions Summary

| Decision | Choice | Why |
|----------|--------|-----|
| Rendering API | WebGPU primary, WebGL 2.0 fallback | Compute shaders for particles, universal fallback |
| Lensing | Screen-space ray-march, weak-field approx | 200× cheaper than full GR, visually indistinguishable |
| Lensing resolution | Half-res + bilateral upsample | 1/4 pixel count, preserves edges |
| Accretion disk | Gas particles, not geometric mesh | Emerges from physics, evolves over time |
| Gravity solver | Velocity Verlet (symplectic) | Energy conservation, no artificial drift |
| Gas dynamics | Passive tracers (no gas-gas gravity) | Captures essential disk physics at web-feasible cost |
| Viscosity | Simple angular momentum transport | Captures disk spreading without full MHD |
| Jet emission | Probability-based redirection | Captures Blandford-Znajek proportionality without MHD |
| Scenarios | Presets as data functions | Physics just runs, effects emerge naturally |
| Phase indicator | Derived from physics state | No hardcoded transitions |
| Audio | Procedural (no files) | Real-time parameter control, no loading |
| UI | Vanilla HTML/CSS/JS | Simple UI doesn't need framework overhead |
| Build tool | Vite | Fastest dev server, native ES modules |

---

## 10. Open Questions and Future Work

### 10.1 Open Questions

1. **Gas particle count**: How many for visually convincing disk? 100? 500? 1000?
2. **Viscous α parameter**: What value gives realistic disk spreading? Need to tune.
3. **ISCO plunge timescale**: How fast do particles spiral in? 2 orbits? 10?
4. **Jet visual fidelity**: Are point sprites sufficient, or do we need volumetric cones?
5. **Audio balance**: How loud should GW chirp be relative to spacetime hum?

### 10.2 Future Expansion (v2)

- NS+NS merger (kilonova) — radioactive decay produces r-process nucleosynthesis
- BH+NS merger — NS tidal disruption before plunge
- EMRI (extreme mass ratio inspiral) — stellar-mass object spiraling into supermassive BH
- Magnetohydrodynamics — magnetic fields, jet launching, disk winds
- Relativistic beaming — Doppler boosting of jet emission
- Shock diamonds — standing shocks in relativistic jets
- Quasi-periodic oscillations — X-ray timing features from inner disk

### 10.3 Deferred Features

- Hawking radiation — negligible for stellar-mass BHs, invisible at any scale
- Full GR metric — post-Newtonian approximation sufficient for visual fidelity
- SPH (smoothed particle hydrodynamics) — too expensive for web, passive tracers capture essential physics
- Grid-based hydrodynamics — complex to implement, expensive for real-time

---

## 11. References

- Misner, Thorne, Wheeler — Gravitation (the GR bible)
- Shapiro & Teukolsky — Black Holes, White Dwarfs, and Neutron Stars
- Blandford & Znajek — Energy extraction from rotating black holes (1977)
- Peters — Gravitational radiation from point masses (1964)
- Shakura & Sunyaev — Black holes in binary systems (1973)
- LIGO Scientific Collaboration — GW150914 detection paper (2016)
- Gammie — The Event Horizon Telescope Collaboration (2019)
- INTERSTELLAR (2014) — Visual reference for black hole rendering
- NASA/Hubble — Public domain nebula textures
