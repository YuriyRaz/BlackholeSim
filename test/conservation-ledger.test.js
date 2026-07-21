import { describe, it, expect } from 'vitest';
import { ConservationLedger } from '../src/physics/ConservationLedger.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';
import { Body } from '../src/objects/Body.js';

describe('ConservationLedger', () => {
  it('should start with zero state', () => {
    const ledger = new ConservationLedger();
    const diag = ledger.getDiagnostics();
    expect(diag.mass.current).toBe(0);
    expect(diag.energy.total).toBe(0);
    expect(diag.counts.total).toBe(0);
  });

  it('should compute mass and energy for particles', () => {
    const ledger = new ConservationLedger();
    const p1 = new MatterParticle({ position: [0, 0, 0], velocity: [0, 0, 0], mass: 1e-3, internalEnergy: 1e8 });
    const p2 = new MatterParticle({ position: [10, 0, 0], velocity: [0, 0, 0], mass: 1e-3, internalEnergy: 1e8 });
    p1.lifecycle = 'alive'; p2.lifecycle = 'alive';
    p1.captured = false; p2.captured = false;
    p1.escaped = false; p2.escaped = false;

    ledger.compute([p1, p2], [], 132.7);
    const diag = ledger.getDiagnostics();

    expect(diag.mass.current).toBeCloseTo(0.002, 10);
    expect(diag.counts.total).toBe(2);
    expect(diag.counts.alive).toBe(2);
    expect(diag.energy.kinetic).toBe(0);
    expect(diag.energy.thermal).toBeCloseTo(2 * 1e-3 * 1e8, 5);
  });

  it('should compute kinetic energy for moving particles', () => {
    const ledger = new ConservationLedger();
    const p = new MatterParticle({ position: [0, 0, 0], velocity: [100, 0, 0], mass: 1e-3, internalEnergy: 0 });
    p.lifecycle = 'alive'; p.captured = false; p.escaped = false;

    ledger.compute([p], [], 132.7);
    const diag = ledger.getDiagnostics();

    expect(diag.energy.kinetic).toBeCloseTo(0.5 * 1e-3 * 10000, 10);
  });

  it('should track accretion and escape mass', () => {
    const ledger = new ConservationLedger();
    ledger.recordAccretion(1e-4, [0, 0, 0], 5e5);
    ledger.recordEscape(2e-5);
    const diag = ledger.getDiagnostics();
    expect(diag.mass.accreted).toBeCloseTo(1e-4, 15);
    expect(diag.mass.escaped).toBeCloseTo(2e-5, 15);
  });

  it('should track shock heating and cooling', () => {
    const ledger = new ConservationLedger();
    ledger.recordShockHeating(1e6);
    ledger.recordCooling(5e5);
    const diag = ledger.getDiagnostics();
    expect(diag.energy.shock).toBeCloseTo(1e6, 10);
    expect(diag.energy.cooling).toBeCloseTo(5e5, 10);
  });

  it('should count particles by state', () => {
    const ledger = new ConservationLedger();
    const alive = new MatterParticle({ position: [0, 0, 0], mass: 1e-6, internalEnergy: 0 });
    const captured = new MatterParticle({ position: [1, 0, 0], mass: 1e-6, internalEnergy: 0 });
    const escaped = new MatterParticle({ position: [2, 0, 0], mass: 1e-6, internalEnergy: 0 });
    alive.lifecycle = 'alive'; alive.captured = false; alive.escaped = false;
    captured.lifecycle = 'alive'; captured.captured = true; captured.escaped = false;
    escaped.lifecycle = 'alive'; escaped.captured = false; escaped.escaped = true;

    ledger.compute([alive, captured, escaped], [], 1);
    const diag = ledger.getDiagnostics();

    expect(diag.counts.total).toBe(3);
    expect(diag.counts.active).toBe(1);
    expect(diag.counts.captured).toBe(1);
    expect(diag.counts.escaped).toBe(1);
  });

  it('should include gravitational potential energy', () => {
    const ledger = new ConservationLedger();
    const p1 = new MatterParticle({ position: [0, 0, 0], mass: 1, internalEnergy: 0 });
    const p2 = new MatterParticle({ position: [10, 0, 0], mass: 1, internalEnergy: 0 });
    p1.lifecycle = 'alive'; p2.lifecycle = 'alive';
    p1.captured = false; p2.captured = false;
    p1.escaped = false; p2.escaped = false;

    ledger.compute([p1, p2], [], 132.7);
    const diag = ledger.getDiagnostics();

    expect(diag.energy.potential).toBeLessThan(0);
    expect(diag.energy.total).toBeLessThan(0);
  });

  it('should reset to zero', () => {
    const ledger = new ConservationLedger();
    ledger.recordAccretion(1, [0, 0, 0], 1);
    ledger.reset();
    const diag = ledger.getDiagnostics();
    expect(diag.mass.accreted).toBe(0);
    expect(diag.energy.shock).toBe(0);
  });
});
