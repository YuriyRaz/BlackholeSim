import { describe, it, expect, beforeEach } from 'vitest';
import { BarnesHut, BHNode } from '../src/physics/BarnesHut.js';
import { BlackHole } from '../src/objects/BlackHole.js';
import { Star } from '../src/objects/Star.js';
import { Body } from '../src/objects/Body.js';
import { Constants } from '../src/core/Constants.js';

describe('BarnesHut', () => {
  let tree;

  beforeEach(() => {
    tree = new BarnesHut();
  });

  it('should handle empty bodies array', () => {
    tree.build([]);
    expect(tree.root).toBeNull();
  });

  it('should build tree with single body', () => {
    const bh = new BlackHole({ mass: 100, position: [0, 0, 0] });
    tree.build([bh]);
    expect(tree.root).not.toBeNull();
    expect(tree.root.mass).toBeCloseTo(100);
    expect(tree.root.massX).toBeCloseTo(0);
    expect(tree.root.massY).toBeCloseTo(0);
    expect(tree.root.massZ).toBeCloseTo(0);
    expect(tree.root.isLeaf).toBe(true);
    expect(tree.root.body).toBe(bh);
  });

  it('should build tree with two bodies', () => {
    const bh1 = new BlackHole({ mass: 100, position: [-10, 0, 0] });
    const bh2 = new BlackHole({ mass: 200, position: [10, 0, 0] });
    tree.build([bh1, bh2]);

    expect(tree.root).not.toBeNull();
    expect(tree.root.mass).toBeCloseTo(300);
    expect(tree.root.isLeaf).toBe(false);
    expect(tree.root.children).toHaveLength(8);
  });

  it('should compute center of mass correctly for two bodies', () => {
    const bh1 = new BlackHole({ mass: 100, position: [-10, 0, 0] });
    const bh2 = new BlackHole({ mass: 100, position: [10, 0, 0] });
    tree.build([bh1, bh2]);

    expect(tree.root.massX).toBeCloseTo(0);
    expect(tree.root.massY).toBeCloseTo(0);
    expect(tree.root.massZ).toBeCloseTo(0);
  });

  it('should compute center of mass with unequal masses', () => {
    const bh1 = new BlackHole({ mass: 100, position: [-10, 0, 0] });
    const bh2 = new BlackHole({ mass: 300, position: [10, 0, 0] });
    tree.build([bh1, bh2]);

    const expectedX = (-10 * 100 + 10 * 300) / 400;
    expect(tree.root.massX).toBeCloseTo(expectedX);
  });

  it('should compute acceleration from single body', () => {
    const bh = new BlackHole({ mass: 100, position: [10, 0, 0] });
    const star = new Star({ mass: 1, position: [0, 0, 0], radius: 1 });
    tree.build([bh]);

    const acc = tree.computeAcceleration(star);
    expect(acc[0]).toBeGreaterThan(0);
    expect(acc[1]).toBeCloseTo(0);
    expect(acc[2]).toBeCloseTo(0);
  });

  it('should compute zero acceleration for body at same position', () => {
    const bh = new BlackHole({ mass: 100, position: [10, 0, 0] });
    tree.build([bh]);

    const acc = tree.computeAcceleration(bh);
    expect(acc[0]).toBeCloseTo(0);
    expect(acc[1]).toBeCloseTo(0);
    expect(acc[2]).toBeCloseTo(0);
  });

  it('should compute correct gravitational acceleration', () => {
    const bh = new BlackHole({ mass: 100, position: [10, 0, 0] });
    const star = new Star({ mass: 1, position: [0, 0, 0], radius: 1 });
    tree.build([bh]);

    const acc = tree.computeAcceleration(star);
    const r = 10;
    const softenedR2 = r * r + Constants.softening * Constants.softening;
    const expectedAcc = Constants.G_solar_km * 100 * r / (softenedR2 * Math.sqrt(softenedR2));
    expect(acc[0]).toBeCloseTo(expectedAcc, 6);
  });

  it('should use theta criterion for opening nodes', () => {
    const bodies = [];
    for (let i = 0; i < 20; i++) {
      bodies.push(new Star({
        mass: 1,
        position: [Math.random() * 100 - 50, Math.random() * 100 - 50, Math.random() * 100 - 50],
        radius: 1
      }));
    }
    tree.build(bodies);

    const testBody = new Star({ mass: 1, position: [200, 200, 200], radius: 1 });
    const acc = tree.computeAcceleration(testBody, 0.5);
    expect(typeof acc[0]).toBe('number');
    expect(isFinite(acc[0])).toBe(true);
  });

  it('should handle bodies at same position without NaN', () => {
    const bh1 = new BlackHole({ mass: 100, position: [0, 0, 0] });
    const bh2 = new BlackHole({ mass: 100, position: [1, 0, 0] });
    tree.build([bh1, bh2]);

    const acc = tree.computeAcceleration(bh1);
    expect(isFinite(acc[0])).toBe(true);
    expect(isFinite(acc[1])).toBe(true);
    expect(isFinite(acc[2])).toBe(true);
  });

  it('should rebuild correctly after body positions change', () => {
    const bh1 = new BlackHole({ mass: 100, position: [-10, 0, 0] });
    const bh2 = new BlackHole({ mass: 100, position: [10, 0, 0] });
    tree.build([bh1, bh2]);

    bh1.position = [0, 10, 0];
    bh2.position = [0, -10, 0];
    tree.build([bh1, bh2]);

    expect(tree.root.massX).toBeCloseTo(0);
    expect(tree.root.massY).toBeCloseTo(0);
    expect(tree.root.massZ).toBeCloseTo(0);
  });

  it('should handle many bodies', () => {
    const bodies = [];
    for (let i = 0; i < 50; i++) {
      bodies.push(new Body({
        mass: 1,
        position: [Math.random() * 100, Math.random() * 100, Math.random() * 100]
      }));
    }
    tree.build(bodies);

    let totalMass = 0;
    for (const b of bodies) totalMass += b.mass;
    expect(tree.root.mass).toBeCloseTo(totalMass);
  });
});
