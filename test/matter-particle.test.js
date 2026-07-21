import { describe, it, expect } from 'vitest';
import { MatterParticle } from '../src/objects/MatterParticle.js';

describe('MatterParticle', () => {
  it('should initialize with default values', () => {
    const p = new MatterParticle();
    expect(p.id).toBeDefined();
    expect(p.position).toEqual([0, 0, 0]);
    expect(p.velocity).toEqual([0, 0, 0]);
    expect(p.mass).toBe(0);
    expect(p.density).toBe(0);
    expect(p.pressure).toBe(0);
    expect(p.internalEnergy).toBe(0);
    expect(p.temperature).toBe(0);
    expect(p.phase).toBe('stellar');
    expect(p.lifecycle).toBe('alive');
    expect(p.captured).toBe(false);
    expect(p.escaped).toBe(false);
    expect(p.isAlive).toBe(true);
    expect(p.isActive).toBe(true);
  });

  it('should initialize with custom values', () => {
    const p = new MatterParticle({
      position: [1, 2, 3],
      velocity: [4, 5, 6],
      mass: 1e-4,
      density: 1.4e-7,
      pressure: 1.2e-10,
      internalEnergy: 5e8,
      temperature: 1e7,
      phase: 'debris',
      lifecycle: 'alive',
      smoothingLength: 0.5,
    });
    expect(p.position).toEqual([1, 2, 3]);
    expect(p.velocity).toEqual([4, 5, 6]);
    expect(p.mass).toBe(1e-4);
    expect(p.density).toBe(1.4e-7);
    expect(p.pressure).toBe(1.2e-10);
    expect(p.internalEnergy).toBe(5e8);
    expect(p.temperature).toBe(1e7);
    expect(p.phase).toBe('debris');
    expect(p.smoothingLength).toBe(0.5);
  });

  it('should compute kinetic energy', () => {
    const p = new MatterParticle({ mass: 1e-6, velocity: [1000, 0, 0] });
    expect(p.kineticEnergy).toBeCloseTo(0.5 * 1e-6 * 1e6, 10);
  });

  it('should compute thermal energy', () => {
    const p = new MatterParticle({ mass: 1e-6, internalEnergy: 5e8 });
    expect(p.thermalEnergy).toBeCloseTo(1e-6 * 5e8, 10);
  });

  it('should compute distance to another particle', () => {
    const a = new MatterParticle({ position: [0, 0, 0] });
    const b = new MatterParticle({ position: [3, 4, 0] });
    expect(a.distanceTo(b)).toBeCloseTo(5, 10);
  });

  it('should save and restore initial state', () => {
    const p = new MatterParticle({ position: [10, 20, 30], phase: 'stellar' });
    p.position = [40, 50, 60];
    p.phase = 'debris';
    p.reset();
    expect(p.position).toEqual([10, 20, 30]);
    expect(p.phase).toBe('stellar');
    expect(p.lifecycle).toBe('alive');
    expect(p.captured).toBe(false);
    expect(p.density).toBe(0);
  });

  it('should reflect lifecycle state', () => {
    const alive = new MatterParticle({ lifecycle: 'alive' });
    expect(alive.isAlive).toBe(true);
    expect(alive.isActive).toBe(true);

    alive.captured = true;
    expect(alive.isActive).toBe(false);
  });
});
