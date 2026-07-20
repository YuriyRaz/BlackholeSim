## 1. Physics State Foundation

- [ ] 1.1 Define one canonical simulation-unit policy for positions, velocities, mass, time, and thermodynamic quantities, and expose the selected black-hole potential in diagnostics.
- [ ] 1.2 Add the persistent matter-particle state with position, velocity, mass, density, pressure, internal energy, temperature, phase, and lifecycle fields.
- [ ] 1.3 Add deterministic particle seeding so identical preset parameters produce identical initial matter states and reproducible tests.
- [ ] 1.4 Implement a stable polytropic stellar initializer with configurable particle resolution and mass normalization.
- [ ] 1.5 Add mass, momentum, angular-momentum, kinetic-energy, thermal-energy, and accretion/escape ledgers to the physics diagnostics.

## 2. Neighbor Search And SPH

- [ ] 2.1 Implement a spatial hash/grid that returns bounded neighboring matter particles for a configured smoothing length.
- [ ] 2.2 Implement SPH density estimation and the equation-of-state pressure calculation with finite-value floors.
- [ ] 2.3 Implement symmetric pressure forces and artificial viscosity for converging particle pairs.
- [ ] 2.4 Implement internal-energy evolution, shock heating, and an explicit configurable cooling term.
- [ ] 2.5 Add timestep constraints for hydrodynamic signal speed, smoothing length, and close black-hole encounters.
- [ ] 2.6 Add unit tests for density response, finite sparse-particle state, pairwise momentum conservation, shock heating, and cooling accounting.

## 3. Unified Gravity Integration

- [ ] 3.1 Extend the symplectic integration pipeline so matter particles receive black-hole and configured matter self-gravity through the same acceleration path.
- [ ] 3.2 Update the Barnes-Hut or equivalent hierarchy to include massive matter particles and exclude only true self-force contributions.
- [ ] 3.3 Implement and document the first-milepost pseudo-Newtonian capture/ISCO potential without presenting it as full general relativity.
- [ ] 3.4 Add direct-sum comparison tests that bound hierarchical gravity error for supported TDE particle counts.
- [ ] 3.5 Add energy and angular-momentum regression tests for two-body and resolved matter scenes.

## 4. TDE Initial Conditions And Disruption

- [ ] 4.1 Replace the one-body TDE star initialization with the persistent polytropic particle state while retaining the star's public identity for UI and audio events.
- [ ] 4.2 Rebuild TDE orbital elements so the encounter starts outside the tidal radius and its derived periapsis is inside the disruption condition.
- [ ] 4.3 Compute deformation and disruption from resolved particle binding, tidal gradients, and hydrodynamic state.
- [ ] 4.4 Remove post-disruption stream generation, pre-shaped arcs, random velocity jitter, and index-based gas/debris splitting.
- [ ] 4.5 Add integration tests proving that existing particles survive the disruption transition and develop bound/unbound orbital branches.

## 5. Fallback, Circularization, And Accretion

- [ ] 5.1 Implement bound/unbound classification from particle orbital energy and angular momentum relative to the selected black-hole potential.
- [ ] 5.2 Implement return-surface crossing events and calculate fallback rate from measured returning mass.
- [ ] 5.3 Implement phase transitions from stellar matter to debris and disk matter using resolved density, shock, and circularization conditions.
- [ ] 5.4 Implement capture at the configured ISCO/horizon boundary with mass, momentum, energy, and accretion-rate accounting.
- [ ] 5.5 Remove the fixed fallback timer, injected fallback curve, arbitrary viscous impulse, and synthetic jet emitter from the TDE path.
- [ ] 5.6 Add tests for fallback response to changed orbital parameters, disk mass accounting, capture timing, and absence of jet particles without MHD state.

## 6. Physics State And Rendering Contract

- [ ] 6.1 Update serialized snapshots and `getState()` to expose the unified matter-particle thermodynamic and phase fields plus conservation diagnostics.
- [ ] 6.2 Update particle rendering to consume the unified state without generating stream, disk, or jet geometry.
- [ ] 6.3 Remove TDE-specific renderer sizing, wrapping, streak, and cluster workarounds that encode physical behavior.
- [ ] 6.4 Update phase and physics-info UI to report measured disruption, fallback, circularization, accretion, and the explicit absence of an MHD jet model.
- [ ] 6.5 Keep future jet rendering data-compatible while ensuring the new TDE core emits no synthetic jet particles.

## 7. Verification And Performance

- [ ] 7.1 Add a deterministic headless TDE integration test covering pre-disruption approach, deformation, disruption, stream evolution, circularization, and accretion.
- [ ] 7.2 Add a regression assertion that no post-disruption particle cluster remains stationary near the black hole for the supported observation window.
- [ ] 7.3 Add resolution comparison tests for mass conservation and qualitative stream/disc behavior at two supported particle counts.
- [ ] 7.4 Benchmark neighbor search, SPH, gravity, and rendering separately against the 30 FPS consumer-hardware target and expose overload diagnostics.
- [ ] 7.5 Run the complete unit suite, production build, and browser visual verification at desktop and mobile viewports.
- [ ] 7.6 Update README and physics documentation to state the approximation boundary and that jets require a future MHD change.
