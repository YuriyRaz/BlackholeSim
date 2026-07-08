import { describe, it, expect, beforeEach } from 'vitest';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { Star } from '../src/objects/Star.js';
import { GasParticle } from '../src/objects/GasParticle.js';
import { Body } from '../src/objects/Body.js';

describe('PhysicsEngine', () => {
  let engine;

  beforeEach(() => {
    engine = new PhysicsEngine();
  });

  it('should initialize with empty arrays', () => {
    expect(engine.bodies).toEqual([]);
    expect(engine.gasParticles).toEqual([]);
    expect(engine.jetParticles).toEqual([]);
    expect(engine.simTime).toBe(0);
  });

  it('should add and remove objects', () => {
    const bh = new BlackHole({ mass: 10, position: [0, 0, 0] });
    engine.addObject(bh);
    expect(engine.bodies.length).toBe(1);
    
    engine.removeObject(bh.id);
    expect(engine.bodies.length).toBe(0);
  });

  it('should add gas particles', () => {
    const gas = new GasParticle({ position: [10, 0, 0], velocity: [0, 1, 0] });
    engine.addGasParticle(gas);
    expect(engine.gasParticles.length).toBe(1);
  });

  it('should step simulation forward', () => {
    const bh = new BlackHole({ mass: 100, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [100, 0, 0], velocity: [0, 0.5, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);
    
    const initialPos = [...star.position];
    engine.step(0.01);
    
    expect(engine.simTime).toBeGreaterThan(0);
    expect(star.position[1]).not.toBe(initialPos[1]);
  });

  it('should compute total energy', () => {
    const bh = new BlackHole({ mass: 100, position: [0, 0, 0] });
    const star = new Star({ mass: 1, position: [100, 0, 0], velocity: [0, 0.5, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);
    
    const energy = engine.getTotalEnergy();
    expect(typeof energy).toBe('number');
    expect(isFinite(energy)).toBe(true);
  });

  it('should compute total energy consistently', () => {
    const bh = new BlackHole({ mass: 100, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [100, 0, 0], velocity: [0, 0.5, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);
    
    const energy1 = engine.getTotalEnergy();
    const energy2 = engine.getTotalEnergy();
    
    expect(energy1).toBeCloseTo(energy2, 10);
  });

  it('should get state snapshot', () => {
    const bh = new BlackHole({ mass: 10, position: [0, 0, 0] });
    engine.addObject(bh);
    
    const state = engine.getState();
    expect(state.bodies.length).toBe(1);
    expect(state.simTime).toBe(0);
    expect(state.gw).toBeDefined();
  });

  it('should reset simulation', () => {
    const bh = new BlackHole({ mass: 10, position: [0, 0, 0] });
    engine.addObject(bh);
    engine.step(0.01);
    
    engine.reset();
    expect(engine.simTime).toBe(0);
    expect(engine.bodies.length).toBe(1);
  });

  it('should load preset', () => {
    const preset = {
      bodies: [
        { type: 'blackhole', mass: 100, position: [0, 0, 0], spin: 0.5 },
        { type: 'star', mass: 1, position: [100, 0, 0], radius: 1 }
      ],
      gas: [
        { position: [50, 0, 0], velocity: [0, 0.3, 0] }
      ]
    };
    
    engine.loadPreset(preset);
    expect(engine.bodies.length).toBe(2);
    expect(engine.gasParticles.length).toBe(1);
  });

  it('should handle tidal disruption', () => {
    const bh = new BlackHole({ mass: 1000, position: [0, 0, 0], fixed: true });
    const star = new Star({ mass: 1, position: [50, 0, 0], velocity: [0, 0.1, 0], radius: 1 });
    engine.addObject(bh);
    engine.addObject(star);
    
    const initialBodies = engine.bodies.length;
    
    for (let i = 0; i < 1000; i++) {
      engine.step(0.001);
      if (star.disrupted) break;
    }
    
    expect(star.disrupted).toBe(true);
    expect(engine.bodies.length).toBeGreaterThan(initialBodies);
  });
});