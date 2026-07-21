import { describe, it, expect } from 'vitest';
import { SPHSolver } from '../src/physics/SPHSolver.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';

describe('SPHSolver', () => {
  it('should compute density for close particles', () => {
    const solver = new SPHSolver();
    const particles = [
      new MatterParticle({ position: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
      new MatterParticle({ position: [0.5, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
    ];
    particles.forEach(p => { p.lifecycle = 'alive'; p.captured = false; p.escaped = false; });
    solver.computeDensity(particles, 2.0);
    expect(particles[0].density).toBeGreaterThan(0);
    expect(particles[1].density).toBeGreaterThan(0);
  });

  it('should increase density when particles are closer', () => {
    const solver = new SPHSolver();
    const far = [
      new MatterParticle({ position: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
      new MatterParticle({ position: [2.0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
    ];
    const close = [
      new MatterParticle({ position: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
      new MatterParticle({ position: [0.5, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
    ];
    far.forEach(p => { p.lifecycle = 'alive'; p.captured = false; p.escaped = false; });
    close.forEach(p => { p.lifecycle = 'alive'; p.captured = false; p.escaped = false; });
    solver.computeDensity(far, 3.0);
    solver.computeDensity(close, 3.0);
    expect(close[0].density).toBeGreaterThan(far[0].density);
  });

  it('should compute finite density and pressure for isolated particle', () => {
    const solver = new SPHSolver();
    const particles = [
      new MatterParticle({ position: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
    ];
    particles[0].lifecycle = 'alive';
    particles[0].captured = false;
    particles[0].escaped = false;
    solver.computeDensity(particles, 2.0);
    expect(particles[0].density).toBeGreaterThanOrEqual(0);
    expect(isFinite(particles[0].density)).toBe(true);

    solver.computePressure(particles);
    expect(particles[0].pressure).toBeGreaterThanOrEqual(0);
    expect(isFinite(particles[0].pressure)).toBe(true);
  });

  it('should compute pressure from density and internal energy', () => {
    const solver = new SPHSolver();
    const p = new MatterParticle({ mass: 1e-6, internalEnergy: 5e8 });
    p.lifecycle = 'alive';
    p.captured = false;
    p.escaped = false;
    p.density = 1e-7;
    solver.computePressure([p]);
    const expected = (5 / 3 - 1) * 1e-7 * 5e8;
    expect(p.pressure).toBeCloseTo(expected, 5);
  });

  it('should conserve pair momentum in SPH forces', () => {
    const solver = new SPHSolver();
    const dt = 0.001;
    const particles = [
      new MatterParticle({ position: [0, 0, 0], velocity: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
      new MatterParticle({ position: [1.5, 0, 0], velocity: [0, 0, 0], mass: 1e-6, internalEnergy: 1e8 }),
    ];
    particles.forEach(p => { p.lifecycle = 'alive'; p.captured = false; p.escaped = false; });

    const h = 2.5;
    solver.computeDensity(particles, h);
    solver.computePressure(particles);
    solver.computeHydroForces(particles, dt, h);

    const totalMomentumBefore = [0, 0, 0];
    for (const p of particles) {
      totalMomentumBefore[0] += p.mass * p.velocity[0];
      totalMomentumBefore[1] += p.mass * p.velocity[1];
      totalMomentumBefore[2] += p.mass * p.velocity[2];
    }

    for (const p of particles) {
      const acc = p._sphAcceleration || [0, 0, 0];
      p.velocity[0] += acc[0] * dt;
      p.velocity[1] += acc[1] * dt;
      p.velocity[2] += acc[2] * dt;
    }

    const totalMomentumAfter = [0, 0, 0];
    for (const p of particles) {
      totalMomentumAfter[0] += p.mass * p.velocity[0];
      totalMomentumAfter[1] += p.mass * p.velocity[1];
      totalMomentumAfter[2] += p.mass * p.velocity[2];
    }

    expect(totalMomentumAfter[0]).toBeCloseTo(totalMomentumBefore[0], 10);
    expect(totalMomentumAfter[1]).toBeCloseTo(totalMomentumBefore[1], 10);
    expect(totalMomentumAfter[2]).toBeCloseTo(totalMomentumBefore[2], 10);
  });

  it('should not produce NaN for zero-mass particles', () => {
    const solver = new SPHSolver();
    const particles = [
      new MatterParticle({ position: [0, 0, 0], mass: 0, internalEnergy: 1e8 }),
      new MatterParticle({ position: [0.5, 0, 0], mass: 0, internalEnergy: 1e8 }),
    ];
    particles.forEach(p => { p.lifecycle = 'alive'; p.captured = false; p.escaped = false; });
    solver.computeDensity(particles, 2.0);
    solver.computePressure(particles);
    expect(isFinite(particles[0].density)).toBe(true);
    expect(isFinite(particles[0].pressure)).toBe(true);
  });

  it('should integrate internal energy with cooling', () => {
    const solver = new SPHSolver();
    const dt = 0.01;
    const p = new MatterParticle({
      position: [0, 0, 0],
      mass: 1e-6,
      internalEnergy: 1e9,
      density: 1e-7,
    });
    p.lifecycle = 'alive';
    p.captured = false;
    p.escaped = false;
    p._duDtHydro = 0;

    solver.integrateInternalEnergy([p], dt, 10);
    expect(p.internalEnergy).toBeLessThan(1e9);
    expect(p.internalEnergy).toBeGreaterThan(0);
    expect(isFinite(p.internalEnergy)).toBe(true);
  });

  it('should report neighbor statistics', () => {
    const solver = new SPHSolver();
    const particles = [];
    for (let i = 0; i < 10; i++) {
      const p = new MatterParticle({
        position: [i * 0.5, 0, 0],
        mass: 1e-6,
        internalEnergy: 1e8,
      });
      p.lifecycle = 'alive';
      p.captured = false;
      p.escaped = false;
      particles.push(p);
    }
    solver.computeDensity(particles, 2.0);
    const stats = solver.getNeighborStats();
    expect(stats.avg).toBeGreaterThan(0);
    expect(stats.max).toBeGreaterThanOrEqual(stats.avg);
    expect(stats.min).toBeGreaterThanOrEqual(0);
  });
});
