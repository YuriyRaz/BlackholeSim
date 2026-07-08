## 1. Physics Engine Setup

- [ ] 1.1 Create src/physics/ directory with PhysicsEngine.js orchestrator
- [ ] 1.2 Create src/core/Constants.js extensions: G, c, M_sun, R_sun, Rs in simulation units
- [ ] 1.3 Implement PhysicsEngine.js: stores bodies[], gasParticles[], runs physics steps each frame
- [ ] 1.4 Implement PhysicsEngine.reset() to clear all bodies and particles
- [ ] 1.5 Implement PhysicsEngine.getState() to expose positions/velocities for renderer

## 2. N-Body Gravity Solver

- [ ] 2.1 Implement Velocity Verlet integrator: position update x(t+dt) = x(t) + v(t)dt + 0.5a(t)dt²
- [ ] 2.2 Implement velocity update v(t+dt) = v(t) + 0.5(a(t) + a(t+dt))dt
- [ ] 2.3 Implement gravitational force computation: F = G × m1 × m2 / r² with softening parameter
- [ ] 2.4 Implement fixed body support (black holes can be fixed or dynamic)
- [ ] 2.5 Implement adaptive time stepping based on shortest orbital period
- [ ] 2.6 Implement Barnes-Hut tree for O(n log n) gravity (activate when body count > 100)
- [ ] 2.7 Implement total energy computation for verification
- [ ] 2.8 Write unit tests: two-body orbit energy conservation over 100 periods

## 3. Gas Particle Dynamics

- [ ] 3.1 Implement GasParticle data structure: position, velocity, temperature, mass, accreted flag
- [ ] 3.2 Implement gas particle integration (Velocity Verlet, gas-gas gravity disabled)
- [ ] 3.3 Implement viscous torque: angular momentum transport from inner to outer particles
- [ ] 3.4 Implement viscous timescale: proportional to orbital period × (r/H)²
- [ ] 3.5 Implement disk spreading: outer edge expands, inner edge stays at ISCO
- [ ] 3.6 Implement gas particle emission from initial conditions (circular orbits at specified radii)
- [ ] 3.7 Implement gas particle capture from infalling debris (circularization)
- [ ] 3.8 Write unit tests: gas particles form disk from random initial positions

## 4. Accretion Physics

- [ ] 4.1 Implement ISCO radius computation from BH spin: r_isco = f(a*) × Rs
- [ ] 4.2 Implement ISCO detection: particles inside ISCO → mark for removal
- [ ] 4.3 Implement particle plunge: rapid inward spiral and removal within few orbital periods
- [ ] 4.4 Implement temperature computation: T ∝ v_orbital² × (1 + α_visc × dissipation)
- [ ] 4.5 Implement accretion rate tracking: mass_accreted / dt over rolling window
- [ ] 4.6 Expose accretionRate as readable property on PhysicsEngine
- [ ] 4.7 Implement jet emission as part of ISCO accretion: P_jet = a*² × (particles_at_ISCO / total_gas)
- [ ] 4.8 Implement jet particle redirection: redirect triggered particles along BH spin axis
- [ ] 4.9 Implement jet velocity: 0.9-0.99c (scaled), with variation for knotted structure
- [ ] 4.10 Implement jet precession: wobble emission direction for tilted BH spin axis
- [ ] 4.11 Implement jet bipolar emission: emit from both poles
- [ ] 4.12 Expose jetParticles[] array on PhysicsEngine for renderer
- [ ] 4.13 Write unit tests: ISCO radius matches analytical values for a*=0 and a*=1
- [ ] 4.14 Write unit tests: jet emission only occurs with spin > 0 and gas at ISCO

## 5. Tidal Forces

- [ ] 5.1 Implement tidal force computation: a_tidal = 2 × G × M_BH × R_body / d³
- [ ] 5.2 Implement disruption detection: tidal force > self-gravity → mark body as disrupted
- [ ] 5.3 Implement star particle release on disruption (particles become free bodies)
- [ ] 5.4 Implement star deformation (prolate stretching proportional to (d_R/d)²)
- [ ] 5.5 Implement tidal stream formation (near-side particles orbit faster than far-side)
- [ ] 5.6 Implement fallback rate computation: dM/dt ∝ (t/T_fallback)^(-5/3)
- [ ] 5.7 Write unit tests: Roche limit for known star/BH combinations

## 6. Gravitational Wave Emission

- [ ] 6.1 Implement GW frequency from orbital parameters: f_GW = 2 × f_orbital
- [ ] 6.2 Implement GW strain: h = (4/d) × (GM/c²)^(5/3) × (πf/c)^(2/3)
- [ ] 6.3 Implement GW luminosity: L_GW = (32/5) × G⁴ × m1² × m2² × (m1+m2) / (c⁵ × a⁵)
- [ ] 6.4 Implement GW energy loss → orbital decay (da/dt from Peters formula)
- [ ] 6.5 Implement chirp mass computation: M_chirp = (m1 × m2)^(3/5) / (m1 + m2)^(1/5)
- [ ] 6.6 Implement quasi-normal mode for ringdown: f_QNM from remnant mass and spin
- [ ] 6.7 Expose gwFrequency, gwStrain, gwPhase as readable properties on PhysicsEngine
- [ ] 6.8 Write unit tests: GW150914-like parameters produce expected values

## 7. Black Hole Spin Effects

- [ ] 7.1 Implement frame dragging: tangential velocity perturbation for orbiting particles
- [ ] 7.2 Implement ISCO shift from spin: r_isco decreases with increasing a*
- [ ] 7.3 Implement ergosphere computation: r_ergo = Rs × (1 + √(1 - a*² × cos²θ))
- [ ] 7.4 Implement ergosphere particle interaction: force co-rotation
- [ ] 7.5 Implement Kerr metric parameters for lensing shader uniforms

## 8. Initial Condition Presets

- [ ] 9.1 Create src/presets/ directory with preset functions
- [ ] 9.2 Implement BinaryBH preset: 2 BHs (36+29 Msun) at 20×Rs separation, circular orbit
- [ ] 9.3 Implement TDE preset: 10^6 Msun BH + 1 Msun star on e=0.9 orbit
- [ ] 9.4 Implement Kerr preset: 10 Msun BH with spin=0.998 + 100 gas particles (10-50×Rs)
- [ ] 9.5 Implement Custom preset: user places objects via UI controls
- [ ] 9.6 Implement preset loading: PhysicsEngine.reset() + load preset data
- [ ] 9.7 Write unit tests: each preset returns valid body and gas arrays

## 9. Celestial Object Entities

- [ ] 10.1 Create src/objects/Body.js base class (pos, vel, mass, type, fixed, disrupted)
- [ ] 10.2 Create src/objects/BlackHole.js (extends Body: spin, Rs, ergosphere computed)
- [ ] 10.3 Create src/objects/Star.js (extends Body: radius, temperature, disruption particles)
- [ ] 10.4 Create src/objects/NeutronStar.js (extends Star: magneticField, rotationRate)
- [ ] 10.5 Implement object registry: addObject(), removeObject(), getObjectsByType()

## 10. Time Controls

- [ ] 11.1 Implement play/pause state management (toggle on Space or button click)
- [ ] 11.2 Implement speed multiplier (0.1× to 10×, default 1×)
- [ ] 11.3 Implement simulation time tracking (dt × speedMultiplier per frame)
- [ ] 11.4 Implement reset function (restore all objects to t=0 state)
- [ ] 11.5 Create src/ui/TimeControl.js UI component (play/pause, speed buttons, time display)
- [ ] 11.6 Create timeline scrubber component (drag to any point, recompute physics from start)
- [ ] 11.7 Wire time controls to PhysicsEngine
- [ ] 11.8 Wire keyboard shortcuts: Space = play/pause, [ / ] = speed up/down

## 11. Object Interaction

- [ ] 12.1 Implement ray-sphere intersection for click detection
- [ ] 12.2 Implement click-to-focus: on click, find closest hit object, trigger camera transition
- [ ] 12.3 Implement object selection highlighting (subtle glow/outline)
- [ ] 12.4 Create src/ui/ObjectList.js panel (list all objects with type icon, name, mass)
- [ ] 12.5 Wire object list clicks to camera focus
- [ ] 12.6 Implement orbital trail rendering (GL_LINE_STRIP with fading opacity, 200 points)
- [ ] 12.7 Implement hover tooltip (show name, type, mass after 500ms hover)
- [ ] 12.8 Expand PhysicsInfo panel (orbital frequency, velocity, GW strain, accretion rate)

## 12. Testing & Polish

- [ ] 13.1 Test gravity solver: two-body orbit closes after 100 periods
- [ ] 13.2 Test gas dynamics: particles form disk from random initial conditions
- [ ] 13.3 Test accretion: particles inside ISCO are removed, accretion rate tracked
- [ ] 13.4 Test tidal disruption: star disrupts at correct tidal radius
- [ ] 13.5 Test GW emission: frequency and strain match expected values
- [ ] 13.6 Test BH spin: frame dragging precesses orbits, ISCO shifts with spin
- [ ] 13.7 Test jet emission: jets appear only with spin > 0 and gas at ISCO
- [ ] 13.8 Test presets: each preset loads valid initial conditions
- [ ] 13.9 Test time controls: play/pause/speed work correctly
- [ ] 13.10 Profile physics engine: verify <5ms per step with 500 gas particles + 10 bodies
- [ ] 13.11 End-to-end test: load preset, see physics-driven evolution, click to focus, scrub time
