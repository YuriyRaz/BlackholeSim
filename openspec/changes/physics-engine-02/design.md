## Context

Extends core-renderer-01. The renderer reads positions and draws them. The physics engine computes those positions. This proposal builds the physics engine that drives the entire simulation.

Key constraint: The physics engine has no concept of "scenarios" or "phases." It just simulates physics given initial conditions. All effects (mergers, disruptions, jets, GW chirps) emerge from the equations.

## Goals / Non-Goals

**Goals:**
- N-body gravity solver that handles 500+ particles at 5ms per step
- Gas particle dynamics with viscous accretion disk evolution
- Tidal forces on any body, disruption detection
- GW emission from any accelerating mass pair
- BH spin effects (frame dragging, ISCO, ergosphere)
- Jet emission from inner disk + spin (Blandford-Znajek)
- Presets as data functions (not scenario classes)
- Time controls and object interaction

**Non-Goals:**
- SPH (smoothed particle hydrodynamics) — overkill for web, gas-gas gravity disabled
- Full GR metric — post-Newtonian approximation sufficient
- Magnetohydrodynamics — jet physics simplified to probability-based redirection
- Scenario state machines — presets are data, not classes

## Decisions

### D1: Velocity Verlet Integrator

**Decision**: Use Velocity Verlet (symplectic) for N-body integration.

**Why**: Symplectic property preserves phase space volume — no artificial energy drift. Time-reversible. Standard for orbital mechanics.

**Alternatives considered**:
- Runge-Kutta 4: More accurate per step, but not symplectic — energy drifts over long simulations.
- Leapfrog: Equivalent to Velocity Verlet, but Verlet formulation is cleaner for variable time steps.

### D2: Gas Particles as Passive Tracers

**Decision**: Gas particles respond to black hole gravity only, not to each other.

**Why**: Gas-gas self-gravity requires SPH or grid-based hydrodynamics — too expensive for web. Passive tracers capture the essential disk physics (orbital dynamics, viscous transport, accretion) at a fraction of the cost.

**Alternatives considered**:
- SPH: Most physically accurate, but O(n²) per step without tree, and web GPUs can't run compute shaders fast enough.
- Grid-based hydro: Accurate for fluid dynamics, but complex to implement and expensive.

### D3: Viscous Torque as Simple Angular Momentum Transport

**Decision**: Implement viscosity as a simple torque that transfers angular momentum from inner to outer particles.

**Why**: Full viscous stress tensor is complex and expensive. A simple torque captures the essential behavior: inner particles lose angular momentum and migrate inward, outer particles gain angular momentum and spread outward. The Shakura-Sunyaev α-parameter controls the efficiency.

### D4: Presets as Data Functions (Not Scenario Classes)

**Decision**: Initial conditions are functions returning `{bodies, gas, camera}`, not classes with state machines.

**Why**: Scenario classes with phase transitions are hardcoded narratives. Physics should just run — mergers happen when BHs get close, disruptions happen when stars get too close. No special-case code needed.

**Alternatives considered**:
- Scenario classes with state machines: More testable for narrative, but hardcoded and not extensible.
- Configuration objects: Similar to functions, but functions are more flexible (can compute derived values).

### D5: Jet Emission as Probability-Based Redirection

**Decision**: When gas reaches ISCO around a spinning BH, a fraction (proportional to a²) is redirected along the spin axis.

**Why**: Full MHD jet launching requires magnetic field simulation — too expensive. Probability-based redirection captures the essential Blandford-Znajek proportionality (P ∝ a² × Ṁ) without simulating magnetic fields.

## Risks / Trade-offs

- **Gas particle count limits disk resolution** → 500 gas particles gives a sparse disk. Acceptable for interactive simulation — visual density comes from point sprite rendering with glow.
- **Viscous timescale may be too slow or too fast** → Tune α_visc parameter. Expose in UI for user adjustment.
- **Jet probability may produce noisy results** → Smooth jet emission over multiple frames. Use rolling average of accretion rate.

## Open Questions

1. **Gas particle count**: How many gas particles for a visually convincing disk? 100? 500? 1000?
2. **Viscous α parameter**: What value gives realistic disk spreading timescale? Need to tune.
3. **ISCO plunge timescale**: How fast do particles inside ISCO spiral in? 2 orbits? 10?
