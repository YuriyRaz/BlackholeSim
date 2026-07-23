import { describe, it, expect } from 'vitest';
import { Body } from '../src/objects/Body.js';
import { Star } from '../src/objects/Star.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { GasParticle } from '../src/objects/GasParticle.js';

describe('Body', () => {
  it('should initialize with default values', () => {
    const body = new Body();
    expect(body.id).toBeDefined();
    expect(body.position).toEqual([0, 0, 0]);
    expect(body.velocity).toEqual([0, 0, 0]);
    expect(body.mass).toBe(0);
    expect(body.type).toBe('star');
    expect(body.fixed).toBe(false);
    expect(body.disrupted).toBe(false);
  });

  it('should initialize with custom values', () => {
    const body = new Body({
      position: [10, 20, 30],
      velocity: [1, 2, 3],
      mass: 5,
      type: 'debris',
      fixed: true
    });
    expect(body.position).toEqual([10, 20, 30]);
    expect(body.velocity).toEqual([1, 2, 3]);
    expect(body.mass).toBe(5);
    expect(body.type).toBe('debris');
    expect(body.fixed).toBe(true);
  });

  it('should save and restore initial state', () => {
    const body = new Body({ position: [1, 2, 3] });
    body.position = [4, 5, 6];
    body.reset();
    expect(body.position).toEqual([1, 2, 3]);
  });

  it('should compute kinetic energy', () => {
    const body = new Body({ mass: 2, velocity: [3, 0, 0] });
    expect(body.kineticEnergy).toBeCloseTo(9, 5);
  });

  it('should compute distance to other body', () => {
    const b1 = new Body({ position: [0, 0, 0] });
    const b2 = new Body({ position: [3, 4, 0] });
    expect(b1.distanceTo(b2)).toBeCloseTo(5, 5);
  });
});

describe('Star', () => {
  it('should initialize with star properties', () => {
    const star = new Star({ mass: 1, radius: 1, temperature: 5778 });
    expect(star.type).toBe('star');
    expect(star.starRadius).toBe(1);
    expect(star.temperature).toBe(5778);
    expect(star.luminosity).toBe(3.828e26);
  });

  it('should compute radius based on starRadius', () => {
    const star = new Star({ radius: 2 });
    expect(star.radius).toBeCloseTo(0.6, 5);
  });

  it('should return color based on temperature', () => {
    const hotStar = new Star({ temperature: 30000 });
    const coolStar = new Star({ temperature: 3000 });
    expect(hotStar.color[2]).toBeGreaterThan(coolStar.color[2]);
  });

  it('generateDisruptionParticles returns empty (particles now created by PhysicsEngine)', () => {
    const star = new Star({ mass: 1, radius: 1 });
    const particles = star.generateDisruptionParticles();
    expect(particles.length).toBe(0);
  });

  it('should compute deformation', () => {
    const bh = new BlackHole({ mass: 100, position: [0, 0, 0] });
    const star = new Star({ mass: 1, position: [50, 0, 0], radius: 1 });
    const deformation = star.computeDeformation(bh);
    expect(deformation).toBeGreaterThanOrEqual(0);
    expect(deformation).toBeLessThanOrEqual(3);
  });
});

describe('BlackHole', () => {
  it('should initialize with blackhole properties', () => {
    const bh = new BlackHole({ mass: 10, spin: 0.5 });
    expect(bh.type).toBe('blackhole');
    expect(bh.spin).toBe(0.5);
    expect(bh.spinAxis).toEqual([0, 1, 0]);
    expect(bh.fixed).toBe(true);
  });

  it('should compute Schwarzschild radius', () => {
    const bh = new BlackHole({ mass: 10 });
    expect(bh.rs).toBeGreaterThan(0);
    expect(bh.rs).toBeCloseTo(29.5, 1);
  });

  it('should compute ISCO radius', () => {
    const bh = new BlackHole({ mass: 10, spin: 0 });
    expect(bh.iscoRadius).toBeGreaterThan(bh.rs);
  });

  it('should compute frame dragging force', () => {
    const bh = new BlackHole({ mass: 10, spin: 0.5 });
    const force = bh.frameDraggingForce([10, 0, 0], [0, 0, 0]);
    expect(force.length).toBe(3);
    expect(isFinite(force[0])).toBe(true);
  });

  it('should detect ergosphere', () => {
    const bh = new BlackHole({ mass: 10, spin: 0.9 });
    const inside = bh.isInErgosphere([bh.rs * 0.5, 0, 0]);
    const outside = bh.isInErgosphere([bh.rs * 5, 0, 0]);
    expect(inside).toBe(true);
    expect(outside).toBe(false);
  });

  it('should detect ISCO', () => {
    const bh = new BlackHole({ mass: 10, spin: 0 });
    const inside = bh.isInsideISCO([bh.rs * 2, 0, 0]);
    const outside = bh.isInsideISCO([bh.rs * 10, 0, 0]);
    expect(inside).toBe(true);
    expect(outside).toBe(false);
  });
});

describe('GasParticle', () => {
  it('should initialize with default values', () => {
    const gas = new GasParticle();
    expect(gas.id).toBeDefined();
    expect(gas.position).toEqual([0, 0, 0]);
    expect(gas.velocity).toEqual([0, 0, 0]);
    expect(gas.mass).toBe(1e-6);
    expect(gas.temperature).toBe(1000);
    expect(gas.accreted).toBe(false);
    expect(gas.age).toBe(0);
  });

  it('should compute size based on temperature', () => {
    const cold = new GasParticle({ temperature: 1000 });
    const hot = new GasParticle({ temperature: 10000 });
    expect(hot.size).toBeGreaterThan(cold.size);
  });

  it('should save and restore initial state', () => {
    const gas = new GasParticle({ position: [1, 2, 3] });
    gas.position = [4, 5, 6];
    gas.reset();
    expect(gas.position).toEqual([1, 2, 3]);
    expect(gas.accreted).toBe(false);
  });
});