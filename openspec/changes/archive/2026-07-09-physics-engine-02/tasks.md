## 1. Physics Engine Setup

- [x] 1.1 Create src/physics/ directory with PhysicsEngine.js orchestrator
- [x] 1.2 Create src/core/Constants.js extensions: G, c, M_sun, R_sun, Rs in SI units (meters, kilograms, seconds)
- [x] 1.3 Implement PhysicsEngine.js: stores bodies[], gasParticles[], runs physics steps each frame
- [x] 1.4 Implement PhysicsEngine.reset() to clear all bodies and particles
- [x] 1.5 Implement PhysicsEngine.getState() to expose positions/velocities for renderer in the data contract format (bodies[], gasParticles[], jetParticles[], gw, accretionRate, simTime)

## 2. N-Body Gravity Solver

- [x] 2.1 Implement Velocity Verlet integrator: position update x(t+dt) = x(t) + v(t)dt + 0.5a(t)dt²
- [x] 2.2 Implement velocity update v(t+dt) = v(t) + 0.5(a(t) + a(t+dt))dt
- [x] 2.3 Implement gravitational force computation: F = G × m1 × m2 / r² with softening parameter
- [x] 2.4 Implement fixed body support (black holes can be fixed or dynamic)
- [x] 2.5 Implement adaptive time stepping based on shortest orbital period
- [x] 2.6 Implement Barnes-Hut tree for O(n log n) gravity (activate when body count > 100)
- [x] 2.7 Implement total energy computation for verification
- [x] 2.8 Write unit tests: two-body orbit energy conservation over 100 periods

## 3. Gas Particle Dynamics

- [x] 3.1 Implement GasParticle data structure: position, velocity, temperature, mass, accreted flag
- [x] 3.2 Implement gas particle integration (Velocity Verlet, gas-gas gravity disabled)
- [x] 3.3 Implement viscous torque: angular momentum transport from inner to outer particles
- [x] 3.4 Implement viscous timescale: proportional to orbital period × (r/H)²
- [x] 3.5 Implement disk spreading: outer edge expands, inner edge stays at ISCO
- [x] 3.6 Implement gas particle emission from initial conditions (circular orbits at specified radii)
- [x] 3.7 Implement gas particle capture from infalling debris (circularization)
- [x] 3.8 Write unit tests: gas particles form disk from random initial positions

## 4. Accretion Physics

- [x] 4.1 Implement ISCO radius computation from BH spin: r_isco = f(a*) × Rs
- [x] 4.2 Implement ISCO detection: particles inside ISCO → mark for removal
- [x] 4.3 Implement particle plunge: rapid inward spiral and removal within few orbital periods
- [x] 4.4 Implement temperature computation: T ∝ v_orbital² × (1 + α_visc × dissipation)
- [x] 4.5 Implement accretion rate tracking: mass_accreted / dt over rolling window
- [x] 4.6 Expose accretionRate as readable property on PhysicsEngine
- [x] 4.7 Implement jet emission as part of ISCO accretion: P_jet = a*² × (particles_at_ISCO / total_gas)
- [x] 4.8 Implement jet particle redirection: redirect triggered particles along BH spin axis
- [x] 4.9 Implement jet velocity: 0.9-0.99c (scaled), with variation for knotted structure
- [x] 4.10 Implement jet precession: wobble emission direction for tilted BH spin axis
- [x] 4.11 Implement jet bipolar emission: emit from both poles
- [x] 4.12 Implement jet particle lifecycle: remove particles beyond 200×Rs, cap at 2,000 particles (FIFO eviction)
- [x] 4.13 Implement jet particle non-interaction: jet particles do not exert gravity or collide
- [x] 4.14 Expose jetParticles[] array on PhysicsEngine for renderer
- [x] 4.15 Write unit tests: ISCO radius matches analytical values for a*=0 and a*=1
- [x] 4.16 Write unit tests: jet emission only occurs with spin > 0 and gas at ISCO

## 5. Tidal Forces

- [x] 5.1 Implement tidal force computation: a_tidal = 2 × G × M_BH × R_body / d³
- [x] 5.2 Implement disruption detection: tidal force > self-gravity → mark body as disrupted
- [x] 5.3 Implement star particle count generation: N = clamp(floor(mass / 0.1×M_sun), 50, 500) with uniform spherical distribution
- [x] 5.4 Implement star deformation (prolate stretching proportional to (d_R/d)²)
- [x] 5.5 Implement tidal stream formation (near-side particles orbit faster than far-side)
- [x] 5.6 Implement fallback rate computation: dM/dt ∝ (t/T_fallback)^(-5/3)
- [x] 5.7 Write unit tests: Roche limit for known star/BH combinations

## 6. Gravitational Wave Emission

- [x] 6.1 Implement GW frequency from orbital parameters: f_GW = 2 × f_orbital
- [x] 6.2 Implement GW strain: h = (4/d) × (GM/c²)^(5/3) × (πf/c)^(2/3)
- [x] 6.3 Implement GW luminosity: L_GW = (32/5) × G⁴ × m1² × m2² × (m1+m2) / (c⁵ × a⁵)
- [x] 6.4 Implement GW energy loss → orbital decay (da/dt from Peters formula)
- [x] 6.5 Implement chirp mass computation: M_chirp = (m1 × m2)^(3/5) / (m1 + m2)^(1/5)
- [x] 6.6 Implement quasi-normal mode for ringdown: f_QNM from remnant mass and spin
- [x] 6.7 Expose gwFrequency, gwStrain, gwPhase as readable properties on PhysicsEngine
- [x] 6.8 Write unit tests: GW150914-like parameters produce expected values

## 7. Black Hole Spin Effects

- [x] 7.1 Implement frame dragging: tangential velocity perturbation for orbiting particles
- [x] 7.2 Implement ISCO shift from spin: r_isco decreases with increasing a*
- [x] 7.3 Implement ergosphere computation: r_ergo = Rs × (1 + √(1 - a*² × cos²θ))
- [x] 7.4 Implement ergosphere particle interaction: force co-rotation
- [x] 7.5 Implement Kerr metric parameters for lensing shader uniforms

## 8. Initial Condition Presets

- [x] 9.1 Create src/presets/ directory with preset functions
- [x] 9.2 Implement BinaryBH preset: 2 BHs (36+29 Msun) at 20×Rs separation, circular orbit
- [x] 9.3 Implement TDE preset: 10^6 Msun BH + 1 Msun star on e=0.9 orbit
- [x] 9.4 Implement Kerr preset: 10 Msun BH with spin=0.998 + 100 gas particles (10-50×Rs)
- [x] 9.5 Implement Custom preset: user places objects via UI controls
- [x] 9.6 Implement preset loading: PhysicsEngine.reset() + load preset data
- [x] 9.7 Write unit tests: each preset returns valid body and gas arrays

## 9. Celestial Object Entities

- [x] 10.1 Create src/objects/Body.js base class (pos, vel, mass, type, fixed, disrupted)
- [x] 10.2 Create src/objects/BlackHole.js (extends Body: spin, Rs, ergosphere computed)
- [x] 10.3 Create src/objects/Star.js (extends Body: radius, temperature, disruption particles)
- [x] 10.4 Create src/objects/NeutronStar.js (extends Star: magneticField, rotationRate)
- [x] 10.5 Implement object registry: addObject(), removeObject(), getObjectsByType()

## 10. Time Controls

- [x] 11.1 Implement play/pause state management (toggle on Space or button click)
- [x] 11.2 Implement speed multiplier (0.1× to 10×, default 1×)
- [x] 11.3 Implement simulation time tracking (dt × speedMultiplier per frame)
- [x] 11.4 Implement reset function (restore all objects to t=0 state)
- [x] 11.5 Implement state snapshots: save full physics state every 100 steps, cap at 100 snapshots (FIFO)
- [x] 11.6 Create src/ui/TimeControl.js UI component (play/pause, speed buttons, time display)
- [x] 11.7 Create timeline scrubber component (drag to any point, recompute from nearest snapshot, max 100 steps)
- [x] 11.8 Wire time controls to PhysicsEngine
- [x] 11.9 Wire keyboard shortcuts: Space = play/pause, [ / ] = speed up/down

## 11. Object Interaction

- [x] 12.1 Implement ray-sphere intersection for click detection
- [x] 12.2 Implement click-to-focus: on click, find closest hit object, trigger camera transition
- [x] 12.3 Implement object selection highlighting (subtle glow/outline)
- [x] 12.4 Create src/ui/ObjectList.js panel (list all objects with type icon, name, mass)
- [x] 12.5 Wire object list clicks to camera focus
- [x] 12.6 Implement orbital trail rendering (GL_LINE_STRIP with fading opacity, 200 points)
- [x] 12.7 Implement hover tooltip (show name, type, mass after 500ms hover)
- [x] 12.8 Expand PhysicsInfo panel (orbital frequency, velocity, GW strain, accretion rate)

## 12. Testing & Polish

- [x] 13.1 Test gravity solver: two-body orbit closes after 100 periods
- [x] 13.2 Test gas dynamics: particles form disk from random initial conditions
- [x] 13.3 Test accretion: particles inside ISCO are removed, accretion rate tracked
- [x] 13.4 Test tidal disruption: star disrupts at correct tidal radius
- [x] 13.5 Test GW emission: frequency and strain match expected values
- [x] 13.6 Test BH spin: frame dragging precesses orbits, ISCO shifts with spin
- [x] 13.7 Test jet emission: jets appear only with spin > 0 and gas at ISCO
- [x] 13.8 Test presets: each preset loads valid initial conditions
- [x] 13.9 Test time controls: play/pause/speed work correctly
- [x] 13.10 Profile physics engine: verify <5ms per step with 500 gas particles + 10 bodies
- [x] 13.11 End-to-end test: load preset, see physics-driven evolution, click to focus, scrub time
