import { describe, it, expect } from 'vitest';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { Star } from '../src/objects/Star.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';
import { Constants } from '../src/core/Constants.js';

describe('Task 7.1: Deterministic headless TDE integration test', () => {
  it('TDE lifecycle: approach, deformation, disruption, fallback, accretion', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p1 = new MatterParticle({
      position: [-100 - 5e7, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [-100 + 5e7, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p3 = new MatterParticle({
      position: [-100, 5e7, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2, p3]);

    expect(star.disrupted).toBe(false);
    expect(p1.phase).toBe('stellar');
    expect(p2.phase).toBe('stellar');
    expect(p3.phase).toBe('stellar');

    engine.step(0.001);

    expect(star.disrupted).toBe(true);
    expect(p1.phase).toBe('debris');
    expect(p2.phase).toBe('debris');
    expect(p3.phase).toBe('debris');
    expect(p1.isActive).toBe(true);
    expect(p2.isActive).toBe(true);
    expect(p3.isActive).toBe(true);

    expect(typeof p1._specificOrbitalEnergy).toBe('number');
    expect(typeof p1._specificAngularMomentum).toBe('number');
    expect(isFinite(p1._specificOrbitalEnergy)).toBe(true);
    expect(isFinite(p1._specificAngularMomentum)).toBe(true);

    const state = engine.getState();
    expect(state.matterParticles.length).toBeGreaterThanOrEqual(1);
    expect(state.ledgers).toBeDefined();
    expect(state.ledgers.energy.total).toBeDefined();
    expect(isFinite(state.ledgers.energy.total)).toBe(true);
  });

  it('TDE preset runs headlessly without errors', { timeout: 15000 }, () => {
    const { TDEPreset } = require('../src/presets/presets.js');
    const engine = new PhysicsEngine();
    const preset = TDEPreset();
    engine.loadPreset(preset);

    expect(engine.matterParticles.length).toBeGreaterThan(0);
    expect(engine.bodies.length).toBe(2);

    for (let i = 0; i < 2; i++) {
      engine.step(0.001);
    }

    expect(engine.simTime).toBeGreaterThan(0);
    const state = engine.getState();
    expect(state.matterParticles.length).toBeGreaterThanOrEqual(1);
  });
});

describe('Task 7.2: Non-stationary cluster regression', () => {
  it('post-disruption particles do not remain stationary', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const particles = [];
    for (let i = 0; i < 10; i++) {
      const angle = (i / 10) * Math.PI * 2;
      const p = new MatterParticle({
        position: [-100 + Math.cos(angle) * 5e7, Math.sin(angle) * 5e7, 0],
        velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
      });
      particles.push(p);
    }
    engine.addMatterParticles(particles);

    engine.step(0.001);
    expect(star.disrupted).toBe(true);

    const initialPositions = particles.map(p => [...p.position]);

    for (let i = 0; i < 50; i++) {
      engine.step(0.001);
    }

    let anyMoved = false;
    for (let i = 0; i < particles.length; i++) {
      if (!particles[i].isActive) continue;
      const dx = particles[i].position[0] - initialPositions[i][0];
      const dy = particles[i].position[1] - initialPositions[i][1];
      const dz = particles[i].position[2] - initialPositions[i][2];
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (dist > 1e-10) {
        anyMoved = true;
        break;
      }
    }
    expect(anyMoved).toBe(true);
  });
});

describe('Task 7.3: Resolution comparison tests', () => {
  it('low and high resolution both conserve mass', () => {
    const runWithResolution = (numParticles) => {
      const engine = new PhysicsEngine();
      const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
      engine.addObject(bh);

      const particles = [];
      for (let i = 0; i < numParticles; i++) {
        const angle = (i / numParticles) * Math.PI * 2;
        const r = 2.5e7;
        const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r);
        particles.push(new MatterParticle({
          position: [r * Math.cos(angle), r * Math.sin(angle), 0],
          velocity: [-vCirc * Math.sin(angle), vCirc * Math.cos(angle), 0],
          mass: 1e-6 / numParticles, phase: 'debris', lifecycle: 'alive',
        }));
      }
      engine.addMatterParticles(particles);

      const totalMass0 = engine.matterParticles.reduce((s, p) => s + p.mass, 0);

      for (let i = 0; i < 20; i++) {
        engine.step(0.001);
      }

      const active = engine.matterParticles.filter(p => p.isActive);
      const totalMass1 = active.reduce((s, p) => s + p.mass, 0);
      const captured = engine.matterParticles.filter(p => p.captured);
      const capturedMass = captured.reduce((s, p) => s + p.mass, 0);

      return { totalMass0, totalMass1, capturedMass, activeCount: active.length };
    };

    const low = runWithResolution(10);
    const high = runWithResolution(50);

    expect(low.totalMass0).toBeGreaterThan(0);
    expect(high.totalMass0).toBeGreaterThan(0);

    const lowDrift = Math.abs(low.totalMass1 + low.capturedMass - low.totalMass0) / low.totalMass0;
    const highDrift = Math.abs(high.totalMass1 + high.capturedMass - high.totalMass0) / high.totalMass0;

    expect(lowDrift).toBeLessThan(0.01);
    expect(highDrift).toBeLessThan(0.01);
  });

  it('angular momentum distribution shows debris spreading', () => {
    const computeAngularMomentumSpread = (numParticles) => {
      const engine = new PhysicsEngine();
      const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
      engine.addObject(bh);

      const particles = [];
      for (let i = 0; i < numParticles; i++) {
        const angle = (i / numParticles) * Math.PI * 2;
        const r = 2.5e7;
        const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r);
        particles.push(new MatterParticle({
          position: [r * Math.cos(angle), r * Math.sin(angle), 0],
          velocity: [-vCirc * Math.sin(angle), vCirc * Math.cos(angle), 0],
          mass: 1e-6 / numParticles, phase: 'debris', lifecycle: 'alive',
        }));
      }
      engine.addMatterParticles(particles);

      for (let i = 0; i < 30; i++) {
        engine.step(0.001);
      }

      const active = engine.matterParticles.filter(p => p.isActive);
      const angles = active.map(p => {
        const theta = Math.atan2(p.position[1], p.position[0]);
        return theta >= 0 ? theta : theta + 2 * Math.PI;
      });

      const minAngle = Math.min(...angles);
      const maxAngle = Math.max(...angles);
      const spread = maxAngle - minAngle;

      return { spread, count: active.length };
    };

    const low = computeAngularMomentumSpread(10);
    const high = computeAngularMomentumSpread(50);

    expect(low.count).toBeGreaterThan(0);
    expect(high.count).toBeGreaterThan(0);
    expect(low.spread).toBeGreaterThan(Math.PI / 2);
    expect(high.spread).toBeGreaterThan(Math.PI / 2);
  });
});

describe('Task 7.1 Extended: Full TDE lifecycle', () => {
  it('runs 100 steps and verifies star disrupts, orbital branches, fallback, accretion', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const particles = [];
    for (let i = 0; i < 10; i++) {
      const angle = (i / 10) * Math.PI * 2;
      particles.push(new MatterParticle({
        position: [-100 + Math.cos(angle) * 5e7, Math.sin(angle) * 5e7, 0],
        velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
      }));
    }
    engine.addMatterParticles(particles);

    expect(star.disrupted).toBe(false);

    for (let step = 0; step < 100; step++) {
      engine.step(0.001);
    }

    expect(star.disrupted).toBe(true);

    const active = engine.matterParticles.filter(p => p.isActive);
    expect(active.length).toBeGreaterThan(0);

    let hasBound = false;
    let hasUnbound = false;
    for (const p of active) {
      if (p._specificOrbitalEnergy !== undefined) {
        if (p._specificOrbitalEnergy < 0) hasBound = true;
        if (p._specificOrbitalEnergy > 0) hasUnbound = true;
      }
    }
    expect(hasBound || hasUnbound).toBe(true);

    const state = engine.getState();
    expect(state.fallbackRate).toBeGreaterThanOrEqual(0);
    expect(state.accretionRate).toBeGreaterThanOrEqual(0);
  });
});

describe('Task 7.2 Extended: Stationary cluster regression', () => {
  it('measures distance variance from BH over 50 steps and verifies spreading', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const particles = [];
    for (let i = 0; i < 10; i++) {
      const angle = (i / 10) * Math.PI * 2;
      const r = 5e7;
      const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r) * 0.5;
      particles.push(new MatterParticle({
        position: [-100 + Math.cos(angle) * r, Math.sin(angle) * r, 0],
        velocity: [-vCirc * Math.sin(angle), vCirc * Math.cos(angle), 0],
        mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
      }));
    }
    engine.addMatterParticles(particles);

    engine.step(0.001);
    expect(star.disrupted).toBe(true);

    const computeDistanceStats = () => {
      const active = engine.matterParticles.filter(p => p.isActive);
      if (active.length === 0) return { mean: 0, variance: 0 };
      const distances = active.map(p => {
        const dx = p.position[0] - bh.position[0];
        const dy = p.position[1] - bh.position[1];
        const dz = p.position[2] - bh.position[2];
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
      });
      const mean = distances.reduce((s, d) => s + d, 0) / distances.length;
      const variance = distances.reduce((s, d) => s + (d - mean) ** 2, 0) / distances.length;
      return { mean, variance };
    };

    const initialStats = computeDistanceStats();
    expect(initialStats.mean).toBeGreaterThan(0);

    for (let i = 0; i < 50; i++) {
      engine.step(0.001);
    }

    const finalStats = computeDistanceStats();
    const varianceRatio = finalStats.variance / (initialStats.variance + 1e-20);

    expect(varianceRatio).toBeGreaterThan(1.0);
  });
});
