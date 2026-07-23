import { describe, it, expect, beforeEach } from 'vitest';
import { BarnesHut } from '../src/physics/BarnesHut.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { Body } from '../src/objects/Body.js';
import { Constants } from '../src/core/Constants.js';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';

describe('BarnesHut with matter particles', () => {
  let tree;

  beforeEach(() => {
    tree = new BarnesHut();
  });

  it('should build tree with bodies and matter particles', () => {
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0] });
    const p = new MatterParticle({ position: [100, 0, 0], mass: 1e-6 });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    tree.build([bh], [p]);

    expect(tree.root).not.toBeNull();
    expect(tree.root.mass).toBeCloseTo(1e6 + 1e-6, 5);
  });

  it('should compute acceleration on particle from BH', () => {
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0] });
    const p = new MatterParticle({ position: [100, 0, 0], mass: 1e-6 });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    tree.build([bh], [p]);

    const acc = tree.computeAcceleration(p);
    expect(acc[0]).toBeLessThan(0);
    expect(Math.abs(acc[1])).toBeLessThan(1e-10);
    expect(Math.abs(acc[2])).toBeLessThan(1e-10);
  });

  it('should compute correct gravitational force on matter particle', () => {
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0] });
    const p = new MatterParticle({ position: [100, 0, 0], mass: 1e-6 });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    tree.build([bh], [p]);

    const acc = tree.computeAcceleration(p);
    const r = 100;
    const r2 = r * r + Constants.softening * Constants.softening;
    const expected = -Constants.G_solar_km * 1e6 * r / (r2 * Math.sqrt(r2));
    expect(acc[0]).toBeCloseTo(expected, 5);
  });

  it('should exclude self-force for matter particle', () => {
    const p1 = new MatterParticle({ position: [0, 0, 0], mass: 1 });
    const p2 = new MatterParticle({ position: [10, 0, 0], mass: 1 });
    p1.lifecycle = 'alive'; p2.lifecycle = 'alive';
    p1.captured = false; p2.captured = false;
    p1.escaped = false; p2.escaped = false;
    tree.build([], [p1, p2]);

    const acc = tree.computeAcceleration(p1);
    expect(isFinite(acc[0])).toBe(true);
  });

  it('should compute mutual gravity between matter particles', () => {
    const p1 = new MatterParticle({ position: [-10, 0, 0], mass: 1 });
    const p2 = new MatterParticle({ position: [10, 0, 0], mass: 1 });
    p1.lifecycle = 'alive'; p2.lifecycle = 'alive';
    p1.captured = false; p2.captured = false;
    p1.escaped = false; p2.escaped = false;
    tree.build([], [p1, p2]);

    const acc1 = tree.computeAcceleration(p1);
    const acc2 = tree.computeAcceleration(p2);
    expect(acc1[0]).toBeGreaterThan(0);
    expect(acc2[0]).toBeLessThan(0);
    expect(acc1[0]).toBeCloseTo(-acc2[0], 10);
  });
});

describe('Direct sum gravity comparison', () => {
  function directSumAcceleration(bodies, particles, queryObj, G) {
    let ax = 0, ay = 0, az = 0;
    for (const body of bodies) {
      const dx = body.position[0] - queryObj.position[0];
      const dy = body.position[1] - queryObj.position[1];
      const dz = body.position[2] - queryObj.position[2];
      const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
      const r = Math.sqrt(r2);
      const f = G * body.mass / (r2 * r);
      ax += f * dx;
      ay += f * dy;
      az += f * dz;
    }
    for (const p of particles) {
      if (p.id === queryObj.id) continue;
      const dx = p.position[0] - queryObj.position[0];
      const dy = p.position[1] - queryObj.position[1];
      const dz = p.position[2] - queryObj.position[2];
      const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
      const r = Math.sqrt(r2);
      const f = G * p.mass / (r2 * r);
      ax += f * dx;
      ay += f * dy;
      az += f * dz;
    }
    return [ax, ay, az];
  }

  it('should bound Barnes-Hut error for small particle set', () => {
    const tree = new BarnesHut();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0] });
    const bodies = [bh];
    const particles = [];
    for (let i = 0; i < 20; i++) {
      const p = new MatterParticle({
        position: [
          (Math.random() - 0.5) * 200,
          (Math.random() - 0.5) * 200,
          (Math.random() - 0.5) * 200,
        ],
        mass: 1e-3,
      });
      p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
      particles.push(p);
    }

    tree.build(bodies, particles);

    for (const p of particles) {
      const bhAcc = tree.computeAcceleration(p);
      const dsAcc = directSumAcceleration(bodies, particles, p, Constants.G_solar_km);

      const bhMag = Math.sqrt(bhAcc[0] ** 2 + bhAcc[1] ** 2 + bhAcc[2] ** 2);
      const dsMag = Math.sqrt(dsAcc[0] ** 2 + dsAcc[1] ** 2 + dsAcc[2] ** 2);
      const diff = Math.sqrt(
        (bhAcc[0] - dsAcc[0]) ** 2 +
        (bhAcc[1] - dsAcc[1]) ** 2 +
        (bhAcc[2] - dsAcc[2]) ** 2
      );

      if (dsMag > 1e-10) {
        const relError = diff / dsMag;
        expect(relError).toBeLessThan(0.15);
      }
    }
  });
});

describe('Energy and angular momentum regression', () => {
  it('should conserve energy for BH + matter particle two-body orbit', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const r = 2e7;
    const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r);
    const p = new MatterParticle({
      position: [r, 0, 0],
      velocity: [0, vCirc, 0],
      mass: 1e-6,
      internalEnergy: 0,
    });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    engine.addMatterParticles([p]);

    const ledgers = engine.getMatterDiagnostics();
    const e0 = ledgers.energy.total;
    expect(isFinite(e0)).toBe(true);

    for (let i = 0; i < 100; i++) {
      engine.step(0.01);
    }

    const ledgers2 = engine.getMatterDiagnostics();
    const e1 = ledgers2.energy.total;
    const drift = Math.abs((e1 - e0) / e0);
    expect(drift).toBeLessThan(0.01);
  });

  it('should conserve angular momentum for two-body orbit', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const r = 2e7;
    const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r);
    const p = new MatterParticle({
      position: [r, 0, 0],
      velocity: [0, vCirc, 0],
      mass: 1e-6,
      internalEnergy: 0,
    });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    engine.addMatterParticles([p]);

    const l0 = p.mass * (p.position[0] * p.velocity[1] - p.position[1] * p.velocity[0]);

    for (let i = 0; i < 100; i++) {
      engine.step(0.01);
    }

    const l1 = p.mass * (p.position[0] * p.velocity[1] - p.position[1] * p.velocity[0]);
    const drift = Math.abs((l1 - l0) / l0);
    expect(drift).toBeLessThan(0.01);
  });

  it('should integrate matter particles through same gravity path as bodies', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const r = 1e7;
    const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / r);
    const p = new MatterParticle({
      position: [r, 0, 0],
      velocity: [0, vCirc * 1.2, 0],
      mass: 1e-6,
      internalEnergy: 0,
    });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;
    engine.addMatterParticles([p]);

    for (let i = 0; i < 50; i++) {
      engine.step(0.01);
    }

    expect(isFinite(p.position[0])).toBe(true);
    expect(isFinite(p.position[1])).toBe(true);
    expect(isFinite(p.velocity[0])).toBe(true);
    expect(p.lifecycle).toBe('alive');
  });
});
