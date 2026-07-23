# J002 Report: Physics Foundation + SPH + Gravity

## Summary

All tasks 1.1-1.5 (Physics State Foundation), 2.1-2.6 (Neighbor Search and SPH), and 3.1-3.5 (Unified Gravity Integration) are implemented and tested.

## Completed Files

### Task Group 1 — Physics State Foundation
- `src/core/SimUnits.js` — canonical simulation units (km, M_sun, s, K), G constant, pseudo-Newtonian flag
- `src/core/RNG.js` — deterministic seeding with configurable seed (default 42)
- `src/core/Constants.js` — all physical constants, SPH parameters, resolution defaults
- `src/objects/MatterParticle.js` — persistent matter particle state with position, velocity, mass, density, pressure, internal energy, temperature, phase, lifecycle, smoothing length
- `src/physics/Polytrope.js` — Lane-Emden polytropic stellar initializer with γ=5/3, 1000 particle default (clamped 200-2000), configurable mass and radius
- `src/physics/ConservationLedger.js` — mass, momentum, angular momentum, KE, thermal, gravitational potential energy, shock heating, cooling, accretion/escape accounting

### Task Group 2 — Neighbor Search and SPH
- `src/physics/SpatialHashGrid.js` — spatial hash/grid with cell-based neighbor queries, rebuild from active particles
- `src/physics/SPHSolver.js` — cubic spline kernel, density estimation, (γ-1)ρu pressure, symmetric pressure forces with artificial viscosity, internal energy evolution with optically thin cooling (du/dt = -u / (β×t_dyn)), shock heating tracking

### Task Group 3 — Unified Gravity Integration
- `src/physics/BarnesHut.js` — octree with bodies + matter particles, center-of-mass aggregation, theta criterion opening
- `src/physics/PhysicsEngine.js` — symplectic leapfrog for matter particles with BH + self-gravity through same acceleration path, SPH force integration, CFL-like timestep constraints, pseudo-Newtonian support

### Tests
- `test/matter-particle.test.js` — 7 tests
- `test/polytrope.test.js` — 10 tests (density profile, mass conservation, determinism, gamma, internal energy, clamping)
- `test/spatial-hash.test.js` — 7 tests (insert, query, rebuild, cell boundary, empty, clear, active-only)
- `test/sph-solver.test.js` — 9 tests (density, pressure, momentum conservation, NaN safety, cooling, neighbor stats)
- `test/barnes-hut.test.js` — 11 tests (build, COM, acceleration, theta, NaN safety, rebuild, many bodies)
- `test/sph-gravity.test.js` — 6 tests (BH+matter tree, direct sum comparison, energy/AM conservation regression)
- `test/conservation-ledger.test.js` — 9 tests (mass, energy, accretion, escape, shock, cooling, counts, reset)

## Test Results

All 49 tests pass.

## Remaining Work for J003
- Task groups 4-5: TDE initial conditions, disruption, fallback, circularization, accretion
- Remove faked stream, gas/debris split, timer-based fallback, synthetic jet
