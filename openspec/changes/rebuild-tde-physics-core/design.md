## Context

The current physics engine represents a star as one `Body` until a distance check fires. It then creates a hand-shaped stream, converts most points into passive gas tracers, applies an arbitrary viscous impulse, and can redirect particles into a jet using a random probability. The renderer is already close to the desired boundary: it can draw generic particle state, but the physics state supplied to it is not physically generated.

This change establishes a physics-first TDE core for the existing vanilla JavaScript WebGPU/WebGL application. The first milestone targets an interactive, educationally useful approximation: Newtonian or pseudo-Newtonian gravity plus SPH hydrodynamics. Full general-relativistic magnetohydrodynamics and radiation transport remain outside this change.

## Goals / Non-Goals

**Goals:**

- Represent the star as persistent matter particles before, during, and after disruption.
- Make tidal deformation, stream formation, fallback, circularization, and disk formation emerge from particle state.
- Apply one gravity pipeline to the black hole, stellar matter, and debris, including matter self-gravity within the selected resolution.
- Model gas density, pressure, shock heating, and viscous transport with a bounded SPH solver.
- Preserve mass, momentum, and angular-momentum accounting well enough for automated invariants and visual diagnosis.
- Keep the renderer scenario-agnostic and preserve a serializable physics state contract.
- Maintain an interactive performance target through a spatial neighbor structure and bounded particle counts.

**Non-Goals:**

- Full Kerr geodesic integration or research-grade general relativity.
- General-relativistic magnetohydrodynamics, magnetic-field evolution, or physically launched relativistic jets.
- Radiation transport, detailed stellar evolution, nuclear reactions, or observational light curves.
- A scenario state machine or scripted phase transitions.
- A pre-created accretion disk or any renderer-only TDE effect.

## Decisions

### D1: Use one persistent matter-particle collection

All stellar material and gas will be represented by one particle state containing position, velocity, mass, density, pressure, internal energy, temperature, and lifecycle flags. A phase label such as `stellar`, `debris`, or `disk` is metadata for equations and diagnostics, not a separate force model.

**Why:** The current split between `bodies`, passive `gasParticles`, and non-interacting `jetParticles` makes it easy to create visual states that do not follow the same physics. A unified collection makes gravity, mass accounting, and serialization explicit.

**Alternatives considered:** Keeping `GasParticle` and `debris` as separate classes was rejected because it preserves divergent integration paths. A full grid solver was rejected for this milestone because it requires a larger mesh and boundary-condition system than the current application can support interactively.

### D2: Use SPH with a spatial neighbor grid

Each particle will estimate local density from nearby particles using a compact smoothing kernel. Pressure forces, artificial viscosity for shocks, and internal-energy evolution will use the same neighbor set. A uniform spatial hash or grid will limit each particle to a bounded neighborhood instead of comparing every pair.

**Why:** SPH naturally follows a deforming star and produces shocks when returning streams intersect. It fits the existing particle renderer and can start on the CPU while leaving a path to WebGPU compute.

**Alternatives considered:** Passive tracers cannot form a disk through shocks. A regular grid is more suitable for fluid volumes but is harder to couple to a moving sparse stellar stream and would require a new rendering/state model. Full N-body particle self-gravity without hydrodynamics cannot circularize gas.

### D3: Initialize a stable polytropic star

The TDE preset will construct a deterministic, approximately hydrostatic stellar particle distribution from a bounded polytropic density profile. Particles receive a common center-of-mass orbit plus the internal state required by the SPH equation of state. The encounter starts outside the tidal radius with orbital elements that determine the pericenter.

**Why:** Uniform random points with random velocity noise are not a star. A stable initial configuration is required so that later deformation can be attributed to the black hole rather than initial numerical explosion.

**Alternatives considered:** Starting from a sphere and relaxing it dynamically is more general but adds a long pre-simulation and another convergence problem. A precomputed stellar snapshot is useful later, but a deterministic local initializer is easier to test in this milestone.

### D4: Use a fixed pseudo-Newtonian black-hole potential for the first TDE milestone

The black hole remains an analytic massive source, fixed in the TDE preset, with a documented pseudo-Newtonian capture/ISCO approximation. Matter particles are integrated with the same time integrator and can also contribute self-gravity. The choice of potential is explicit in the state/configuration and is not presented as full GR.

**Why:** A fixed central source keeps the first SPH implementation stable and affordable while preserving the essential tidal and orbital behavior. It also avoids silently mixing SI, kilometre, and renderer units.

**Alternatives considered:** Full GR would be more accurate but would require geodesic integration and a new metric-aware timestepper. Pure Newtonian gravity is simpler, but it gives a poor inner-boundary model near the horizon. Moving the black hole and enforcing recoil is a later conservation milestone.

### D5: Derive fallback, disk formation, and accretion from events in the particle state

Fallback rate will be measured from bound particles returning through a selected pericenter region. Circularization will result from resolved stream intersections, shock heating, and energy loss. Accretion will remove particles only when the capture condition is met, recording their mass, momentum, and energy in an accretion ledger.

**Why:** A fixed `t^(-5/3)` curve can be a diagnostic comparison, but it must not drive positions or the UI. The simulation must be able to disagree with the ideal curve when resolution or initial conditions change.

**Alternatives considered:** Injecting gas into a disk is visually reliable but is exactly the behavior this change removes. Imposing a viscous radial drift can be retained only as a calibrated SPH transport term, not as a positional shortcut.

### D6: Do not synthesize jets in this change

Accretion of a spinning black hole will not create `jetParticles` unless a future MHD subsystem provides a magnetic state and an energy/momentum transfer event. The renderer may retain support for externally supplied jet data, but it must render no jet for the new TDE core.

**Why:** Gravity, pressure, and hydrodynamic viscosity do not determine a relativistic jet. The current probability-based redirect is an effect generator, not a consequence of the simulated state. Removing it makes the boundary honest.

**Alternatives considered:** A Blandford-Znajek scaling rule can be a later reduced MHD model, but using it now would repeat the same unsupported shortcut under a more scientific name. Precomputed jet geometry is unsuitable because the requirement is emergent behavior.

### D7: Keep physics and rendering independently testable

The physics engine will expose particle positions, velocities, thermodynamic fields, phase, and event counters. Rendering will consume this state without creating, deleting, or reshaping matter. Tests will validate numerical invariants and a headless visual check will validate that the expected stream and disk are visible.

**Why:** The previous failure was diagnosed visually but originated in state generation. Separating the contracts lets tests catch a stationary cluster without relying on a screenshot.

### D8: TDE orbital parameters — start outside tidal radius, e=0.95

The TDE preset places the star at `3 × dR` from the black hole on an elliptical orbit with eccentricity `e = 0.95` and periapsis inside `dR`. The orbit defines the center-of-mass trajectory; the resolved star particles follow this trajectory with internal SPH state.

**Why:** Starting outside the tidal radius lets students see the approach phase and the gradual increase of tidal force (`a_tidal ∝ 1/d³`) before disruption. Eccentricity 0.95 produces a clearly bound orbit with a fast periapsis passage, appropriate for a single encounter in a teaching simulation.

**Alternatives considered:** Starting at `2 × dR` (too little approach time for visual/educational clarity). e=0.99 (periapsis passage too fast, disrupts numerical stability). A parabolic orbit (unbound, no fallback phase).

### D9: Polytropic star — γ = 5/3, 1000 particles

The star is initialized as a polytropic sphere with index `γ = 5/3` (adiabatic ideal gas, appropriate for a sun-like main-sequence star). The density profile follows the Lane-Emden solution for `n = 1.5` (γ = 1 + 1/n). Default resolution: 1000 particles per star.

**Why:** γ = 5/3 is the standard adiabatic index for a non-relativistic ideal gas and is what physics students learn. 1000 particles provides sufficient density sampling for SPH stability while keeping the simulation interactive on a laptop CPU (the neighbor search remains bounded).

**Particle count formula:** `N_star = clamp(M_star / M_sun × 1000, 200, 2000)`. A solar-mass star gets 1000 particles; lower-mass stars may go down to 200, more massive stars up to 2000.

### D10: Cooling — optically thin placeholder for first milestone

The first milestone uses a simple optically thin cooling law:
```
du/dt = -u / t_cool
t_cool = β × t_dyn(ρ)
t_dyn = 1 / sqrt(Gρ)
```
where `β` is a dimensionless parameter (default 10). This is NOT a crutch — optically thin cooling is a standard SPH approximation and is physically motivated (real gas in the TDE stream radiates energy). The cooling timescale is tied to the local dynamical time, which is the shortest physical timescale in the problem.

**Why:** Without any cooling, shocked debris retains its thermal energy and forms a hot, puffy torus that does not circularize into a thin disk within the simulation window. A simple cooling law lets students observe: "with cooling → stream intersections lose energy → debris circularizes → disk forms." The `β` parameter serves as calibration, not as a magic value.

**Teaching note:** Students can experiment with β → Infinity (no cooling → thick torus) vs. β → 1 (rapid cooling → thin disk) and observe the difference.

## Risks / Trade-offs

- [SPH instability or particle clumping] → Use kernel/support bounds, CFL-like timestep limits, density floors, artificial viscosity, and small deterministic test scenes before TDE runs.
- [Insufficient browser performance] → Start with a bounded particle count and spatial hashing; benchmark CPU work separately from WebGL/WebGPU rendering; move neighbor and force kernels to a worker or WebGPU only after the equations are validated.
- [Numerical energy loss hides physical circularization] → Track gravitational, kinetic, thermal, and shock-energy terms separately and report conservation error in tests and diagnostics.
- [Pseudo-Newtonian inner boundary is mistaken for GR] → Label the potential and capture model in the UI/state metadata and keep full GR outside the acceptance criteria.
- [A disk does not form at low resolution] → Validate angular-momentum distribution and stream self-intersection before increasing visual density; do not inject a disk to satisfy a screenshot.
- [Removing jets disappoints the current preset expectation] → Make the absence explicit in the phase/info state and create a separate MHD proposal before reintroducing jets.

## Migration Plan

1. Add the unified particle state, SPH neighbor/density/pressure calculations, and conservation diagnostics behind the new TDE physics path.
2. Replace the TDE initializer with a stable star and an encounter starting outside the tidal radius.
3. Update the physics-to-renderer state contract and make the generic particle renderer consume the new particle collection.
4. Replace disruption, fallback, circularization, and capture code with event-driven particle accounting.
5. Remove the pre-shaped stream, index-based gas/debris split, fixed fallback driver, and probability-based jet emitter after the new tests pass.
6. Run unit, integration, build, and headless visual checks; retain Binary BH and non-TDE regression coverage.

Rollback during development is a source-control revert to the pre-change physics path. No data migration is required because snapshots are local runtime state and the new serialized particle schema is versioned.

## Open Questions

- What particle count gives acceptable SPH stability and 30 FPS on the project's weakest supported GPU/CPU combination? (Default 1000 per star; may need tuning)
- Should the first implementation use a fixed smoothing length or adapt it from local density?
- Should the MHD/jet change use a reduced magnetic-flux model or target a GPU-capable GRMHD research path?
- Should the black hole become dynamic in the same change, or remain fixed until the matter solver has passed conservation tests?
