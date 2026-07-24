import { describe, it, expect } from 'vitest';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';
import { SpatialHashGrid } from '../src/physics/SpatialHashGrid.js';
import { SPHSolver } from '../src/physics/SPHSolver.js';
import { Constants } from '../src/core/Constants.js';

function createParticleRing(count, radius, velocityScale) {
  const particles = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const r = radius * (0.8 + 0.4 * Math.random());
    const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r) * velocityScale;
    particles.push(new MatterParticle({
      position: [r * Math.cos(angle), r * Math.sin(angle), (Math.random() - 0.5) * radius * 0.1],
      velocity: [-vCirc * Math.sin(angle), vCirc * Math.cos(angle), 0],
      mass: 1e-6 / count,
      phase: 'debris',
      lifecycle: 'alive',
    }));
  }
  return particles;
}

describe('Benchmarks', () => {
  const ITERATIONS = 10;
  const PARTICLE_COUNT = 1000;

  it('neighbor search throughput', { timeout: 120000 }, () => {
    const grid = new SpatialHashGrid(100);
    const particles = createParticleRing(PARTICLE_COUNT, 2.5e7, 1.0);
    const smoothingLength = 500;

    for (const p of particles) {
      grid.insert(p);
    }

    const start = performance.now();
    for (let i = 0; i < ITERATIONS; i++) {
      for (const p of particles) {
        grid.query(p.position, smoothingLength);
      }
    }
    const elapsed = performance.now() - start;
    const opsPerSec = (ITERATIONS * PARTICLE_COUNT) / (elapsed / 1000);

    console.log(`Neighbor search: ${elapsed.toFixed(2)}ms for ${ITERATIONS} iterations, ${opsPerSec.toFixed(0)} queries/sec`);
    expect(opsPerSec).toBeGreaterThan(0);
  });

  it('SPH forces throughput', { timeout: 120000 }, () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const particles = createParticleRing(PARTICLE_COUNT, 2.5e7, 1.0);
    engine.addMatterParticles(particles);
    engine._computeSmoothingLength();
    const h = engine._smoothingLength;

    const sph = new SPHSolver();
    const active = engine.matterParticles.filter(p => p.isActive);

    const start = performance.now();
    for (let i = 0; i < ITERATIONS; i++) {
      sph.computeDensity(active, h);
      sph.computePressure(active);
      sph.computeHydroForces(active, 0.001, h);
    }
    const elapsed = performance.now() - start;
    const opsPerSec = ITERATIONS / (elapsed / 1000);

    console.log(`SPH forces: ${elapsed.toFixed(2)}ms for ${ITERATIONS} iterations, ${opsPerSec.toFixed(0)} steps/sec`);
    expect(opsPerSec).toBeGreaterThan(0);
  });

  it('gravity integration throughput', { timeout: 120000 }, () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const particles = createParticleRing(PARTICLE_COUNT, 2.5e7, 1.0);
    engine.addMatterParticles(particles);

    const start = performance.now();
    for (let i = 0; i < ITERATIONS; i++) {
      engine._integrateMatterGravity(0.001);
    }
    const elapsed = performance.now() - start;
    const opsPerSec = ITERATIONS / (elapsed / 1000);

    console.log(`Gravity integration: ${elapsed.toFixed(2)}ms for ${ITERATIONS} iterations, ${opsPerSec.toFixed(0)} steps/sec`);
    expect(opsPerSec).toBeGreaterThan(0);
  });

  it('particle rendering throughput', { timeout: 120000 }, () => {
    const particles = createParticleRing(PARTICLE_COUNT, 2.5e7, 1.0);

    const start = performance.now();
    for (let i = 0; i < ITERATIONS; i++) {
      const state = particles.map(p => ({
        position: [...p.position],
        velocity: [...p.velocity],
        mass: p.mass,
        temperature: p.temperature,
      }));
    }
    const elapsed = performance.now() - start;
    const fps = 1000 / (elapsed / ITERATIONS);

    console.log(`Particle state prep: ${elapsed.toFixed(2)}ms for ${ITERATIONS} iterations, ${fps.toFixed(0)} FPS equivalent`);
    expect(fps).toBeGreaterThan(0);
  });
});
