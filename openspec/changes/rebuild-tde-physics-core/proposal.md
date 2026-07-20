## Why

The current TDE mode does not simulate a star being disrupted. It creates a pre-shaped stream, assigns most points to passive gas by index, and emits jets through a random redirect rule. This produces a plausible screenshot in isolated cases, but it violates the project's core promise that visible phenomena emerge from shared physical equations.

The TDE core must be rebuilt around persistent matter particles so that tidal deformation, stream formation, fallback, circularization, and accretion are consequences of gravity and hydrodynamics. This change is needed now because renderer tuning cannot fix the underlying non-physical state transitions.

## What Changes

- **BREAKING** Replace the one-body star plus post-disruption visual particle generator with a persistent particle representation of stellar matter.
- Add a smoothed-particle hydrodynamics (SPH) layer for density, pressure, internal energy, shocks, and hydrodynamic viscosity.
- Apply a consistent gravity pipeline to the black hole, stellar matter, and bound debris, including matter self-gravity where the selected resolution supports it.
- Start the TDE encounter outside the tidal radius on a physically defined eccentric trajectory; disruption must occur when the evolving state crosses the disruption condition.
- Derive the tidal stream from particle positions and velocities. Remove pre-shaped stream arcs, deterministic gas/debris splitting, and renderer-driven stream geometry.
- Derive fallback, circularization, disk formation, and accretion from particle energy, angular momentum, collisions, and capture events rather than fixed timers or injected rates.
- Remove probability-based jet particle creation from the TDE core. A jet must not be displayed as a fake effect when magnetic-field physics is absent; physical jet launching is a follow-up MHD capability.
- Keep the renderer generic: it consumes particle state and must not know whether a point belongs to a stream, disk, or special effect.
- Add conservation and resolution checks for mass, energy, angular momentum, disruption timing, and the absence of stationary artificial clusters.

## Capabilities

### New Capabilities

- `smoothed-particle-hydrodynamics`: Particle density, pressure, internal energy, shock handling, and hydrodynamic transport for stellar matter and gas.

### Modified Capabilities

- `tidal-disruption`: Stars are persistent particle systems; deformation and disruption release particles into free evolution under the common force model.
- `gravity-solver`: Massive stellar and debris particles participate in the same gravitational integration as other bodies.
- `gas-dynamics`: Gas is no longer a passive tracer population; disk structure must emerge from hydrodynamic interactions, shocks, angular momentum, and cooling.
- `accretion-physics`: Fallback and accretion are measured from evolving particle trajectories and mass capture; fixed fallback formulas and random jet redirection are removed.
- `initial-presets`: The TDE preset begins before disruption and contains no pre-created stream or accretion disk.
- `relativistic-jet`: The current probability-based jet behavior is removed from the physical core; real jet launching is explicitly deferred to an MHD implementation.

## Impact

The change affects `PhysicsEngine`, `Star`, `GasParticle`, `BlackHole`, the TDE preset, physics state serialization, and the related unit and integration tests. Existing particle and body renderers should remain data-driven and require no scenario-specific rendering logic.

The implementation must fit the current WebGPU/WebGL application and remain usable on consumer hardware. A first milestone may use a bounded CPU SPH solver with spatial neighbor lookup; higher particle counts can later move to WebGPU compute or a worker without changing the physics state contract. No external physics engine is assumed for the first milestone.
