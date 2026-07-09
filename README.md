# BlackholeSim

An interactive real-time black hole simulation built with vanilla JavaScript,
WebGPU, and a WebGL 2.0 fallback. The simulation models gravitational
interactions and renders effects such as accretion, tidal disruption, and
gravitational lensing.

## Requirements

- Node.js 20 or newer
- A modern browser with WebGPU or WebGL 2.0 support

## Getting started

```sh
npm install
npm run dev
```

The development server runs at <http://localhost:3000>.

## Commands

```sh
npm run dev        # Start the development server
npm run build      # Create a production build
npm run preview    # Preview the production build
npm test           # Run the test suite once
npm run test:watch # Run tests in watch mode
```

## Project structure

- `src/core` — simulation clock and shared constants
- `src/physics` — gravity and physics calculations
- `src/objects` — simulated celestial objects
- `src/renderer` — WebGPU/WebGL rendering pipeline
- `src/shaders` — WGSL and GLSL shaders
- `src/ui` — simulation controls and status displays
- `test` — automated tests
- `docs` — architecture and design documentation
- `openspec` — feature specifications and change proposals

See [docs/DESIGN.md](docs/DESIGN.md) for the architecture and design goals.

