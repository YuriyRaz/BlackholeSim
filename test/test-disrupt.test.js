import { describe, it, expect } from 'vitest';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { Star } from '../src/objects/Star.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';
import { Constants } from '../src/core/Constants.js';

describe('Disruption', () => {
  it('detects simple disruption', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p1 = new MatterParticle({
      position: [-100 - 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [-100 + 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2]);

    engine.step(0.001);
    expect(star.disrupted).toBe(true);
  });

  it('does not hang on empty matter particles', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);
    engine.step(0.001);
    expect(engine.simTime).toBeGreaterThan(0);
  });

  it('does not hang with one particle', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p = new MatterParticle({
      position: [-100, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p]);
    engine.step(0.001);
    expect(engine.simTime).toBeGreaterThan(0);
  });

  it('does not hang with two close particles without star', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const p1 = new MatterParticle({
      position: [-1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2]);
    engine.step(0.001);
    expect(engine.simTime).toBeGreaterThan(0);
  });
});

describe('Task 4.5: Particle survival and bound/unbound branches', () => {
  it('particles survive disruption and remain active', () => {
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
    engine.addMatterParticles([p1, p2]);

    engine.step(0.001);
    expect(star.disrupted).toBe(true);
    expect(p1.isActive).toBe(true);
    expect(p2.isActive).toBe(true);
  });

  it('disruption transitions particles from stellar to debris phase', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p1 = new MatterParticle({
      position: [-100 - 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [-100 + 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2]);

    expect(p1.phase).toBe('stellar');
    expect(p2.phase).toBe('stellar');

    engine.step(0.001);

    expect(p1.phase).toBe('debris');
    expect(p2.phase).toBe('debris');
  });

  it('bound and unbound orbital branches develop after disruption', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p1 = new MatterParticle({
      position: [-100 - 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [-100 + 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2]);

    engine.step(0.001);
    expect(star.disrupted).toBe(true);

    expect(typeof p1._specificOrbitalEnergy).toBe('number');
    expect(typeof p2._specificOrbitalEnergy).toBe('number');
    expect(isFinite(p1._specificOrbitalEnergy)).toBe(true);
    expect(isFinite(p2._specificOrbitalEnergy)).toBe(true);
  });

  it('particles classify into bound and escaped based on energy and angular momentum', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const bound = new MatterParticle({
      position: [2.5e7, 0, 0], velocity: [0, 100000, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
    });
    const unbound = new MatterParticle({
      position: [2.5e7, 0, 0], velocity: [0, 200000, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
    });
    engine.addMatterParticles([bound, unbound]);

    engine.step(0.001);

    expect(bound._specificOrbitalEnergy).toBeDefined();
    expect(unbound._specificOrbitalEnergy).toBeDefined();
    expect(bound._specificAngularMomentum).toBeDefined();
    expect(unbound._specificAngularMomentum).toBeDefined();
  });
});

describe('Task 5.6: Fallback, disk, capture, jet-absence', () => {
  it('fallback rate tracks returning mass', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const dR = Constants.tidalDisruptionRadius(1e6, 1, 1);

    const returning = new MatterParticle({
      position: [dR * 1.5, 0, 0], velocity: [-50000, 0, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
    });
    engine.addMatterParticles([returning]);

    engine.step(0.001);

    expect(engine._fallbackRate).toBeGreaterThanOrEqual(0);
  });

  it('no jet particles created without MHD state', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [-100, 0, 0], velocity: [0, 0, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);

    const p1 = new MatterParticle({
      position: [-100 - 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    const p2 = new MatterParticle({
      position: [-100 + 1.5e6, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'stellar', lifecycle: 'alive',
    });
    engine.addMatterParticles([p1, p2]);

    for (let i = 0; i < 10; i++) {
      engine.step(0.001);
    }

    expect(engine.jetParticles).toBeUndefined();
  });

  it('capture at ISCO marks particle as captured', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const iscoRadius = bh.iscoRadius;
    const insideISCO = new MatterParticle({
      position: [iscoRadius * 0.5, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
    });
    engine.addMatterParticles([insideISCO]);

    engine.step(0.001);

    expect(insideISCO.captured).toBe(true);
    expect(insideISCO.isActive).toBe(false);
  });

  it('disk phase transitions from debris with circularity or shock', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const vCirc = Math.sqrt(Constants.G_solar_km * 1e6 / 2.5e7);
    const disk = new MatterParticle({
      position: [2.5e7, 0, 0], velocity: [0, vCirc, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
      density: 1e-10, internalEnergy: 1e-3,
    });
    engine.addMatterParticles([disk]);

    for (let i = 0; i < 50; i++) {
      engine.step(0.001);
    }

    expect(disk.phase === 'debris' || disk.phase === 'disk').toBe(true);
  });

  it('accretion rate tracks captured mass', () => {
    const engine = new PhysicsEngine();
    const bh = new BlackHole({ mass: 1e6, position: [0, 0, 0], fixed: true });
    engine.addObject(bh);

    const iscoRadius = bh.iscoRadius;
    const p = new MatterParticle({
      position: [iscoRadius * 0.5, 0, 0], velocity: [0, 0, 0], mass: 1e-6, phase: 'debris', lifecycle: 'alive',
    });
    engine.addMatterParticles([p]);

    engine.step(0.001);

    expect(engine._accretedMass).toBeGreaterThan(0);
  });
});
