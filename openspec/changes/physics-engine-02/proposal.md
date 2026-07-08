## Why

The renderer (Proposal 1) draws whatever it's told. But nothing moves yet. The physics engine is the brain — it computes gravitational forces, evolves gas dynamics, handles tidal interactions, emits gravitational waves, and produces jets. It doesn't know about "scenarios" or "phases." It just simulates physics given initial conditions.

Every visual effect in the simulation — mergers, tidal disruptions, accretion disks, jets, gravitational wave chirps — emerges from the physics equations. There is no special-case code for "what happens during a merger." Two black holes get close, gravity pulls them together, they merge. A star gets too close, tidal forces tear it apart. Gas orbits a spinning BH, a disk forms, jets appear. All consequences of the same physics engine.

## What Changes

- **N-body gravitational solver**: Velocity Verlet symplectic integrator. Handles all massive bodies with adaptive time stepping and Barnes-Hut tree optimization.
- **Gas particle dynamics**: Gas particles orbit black holes under gravity, with viscous interactions that transport angular momentum. The accretion disk structure emerges from the particle dynamics.
- **Accretion physics**: Gas particles inside ISCO plunge into the black hole. Accretion rate tracked and exposed for jet emission and UI.
- **Tidal forces**: Tidal force computation on any body near any black hole. Stars deform and disrupt when tidal force exceeds self-gravity.
- **Gravitational wave emission**: Any accelerating mass pair emits GWs. Frequency, strain, luminosity from orbital parameters. GW energy loss drives orbital decay.
- **Black hole spin effects**: Frame dragging, ISCO shift, ergosphere region.
- **Jet emission**: Inner disk gas particles near ISCO around a spinning BH are redirected along the spin axis. Jet intensity ∝ a² × accretion_rate.
- **Initial condition presets**: Functions returning arrays of bodies and gas particles. Binary BH, TDE, Kerr presets. These are data, not classes.
- **Time controls**: Play/pause, speed adjustment, timeline scrubber.
- **Object interaction**: Click-to-focus, orbital path visualization, object list.

## Capabilities

### New Capabilities

- `gravity-solver`: N-body gravitational integrator (Velocity Verlet, adaptive time stepping, Barnes-Hut tree).
- `gas-dynamics`: Gas particle orbital evolution with viscous angular momentum transport. Disk structure emerges from particle dynamics.
- `accretion-physics`: ISCO detection, particle accretion, accretion rate tracking, temperature derivation from orbital velocity. Jet emission as part of accretion (inner disk gas + BH spin → Blandford-Znajek).
- `tidal-forces`: Tidal force computation on any body. Star deformation and disruption when tidal force exceeds self-gravity.
- `gravitational-waves`: GW frequency, strain, luminosity from orbital parameters. GW energy loss drives orbital decay.
- `bh-spin-effects`: Frame dragging, ISCO shift, ergosphere computation for spinning black holes.
- `initial-presets`: Functions returning body/gas initial conditions. Binary BH, TDE, Kerr presets.
- `time-controls`: Play/pause, speed multiplier, timeline scrubber.
- `object-interaction`: Click-to-focus, orbital path rendering, object list panel.

### Modified Capabilities

- `ui-shell`: Expand physics info panel with orbital data, accretion rate, GW strain. Add time control bar. Add object list panel. Add preset selector.

## Impact

- **Extends core-renderer-01**: Physics engine drives all object positions. Renderer reads from physics state.
- **New modules**: ~15 JavaScript modules (physics/, objects/, ui/ additions).
- **No scenario classes**: Physics engine has no concept of "scenarios" or "phases." Presets are data functions.
- **All effects emerge from physics**: Mergers, tidal disruptions, accretion disks, jets, GW chirps — all consequences of the equations.
- **Performance**: N-body solver on CPU. With Barnes-Hut, 500 gas particles + 10 bodies at ~5ms per step.
