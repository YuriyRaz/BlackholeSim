import { describe, it, expect } from 'vitest';
import { SpatialHashGrid } from '../src/physics/SpatialHashGrid.js';
import { MatterParticle } from '../src/objects/MatterParticle.js';

describe('SpatialHashGrid', () => {
  it('should insert and query a single particle', () => {
    const grid = new SpatialHashGrid(1);
    const p = new MatterParticle({ position: [0, 0, 0] });
    grid.insert(p);
    const result = grid.query([0, 0, 0], 1.5);
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(p.id);
  });

  it('should find nearby particles', () => {
    const grid = new SpatialHashGrid(1);
    const p1 = new MatterParticle({ position: [0, 0, 0] });
    const p2 = new MatterParticle({ position: [0.5, 0, 0] });
    const p3 = new MatterParticle({ position: [5, 0, 0] });
    grid.insert(p1);
    grid.insert(p2);
    grid.insert(p3);
    const result = grid.query([0, 0, 0], 1.5);
    expect(result.length).toBe(2);
    expect(result.some(p => p.id === p3.id)).toBe(false);
  });

  it('should rebuild grid', () => {
    const grid = new SpatialHashGrid(1);
    const p1 = new MatterParticle({ position: [0, 0, 0] });
    const p2 = new MatterParticle({ position: [10, 0, 0] });
    grid.rebuild([p1, p2]);
    const result = grid.query([0, 0, 0], 1.5);
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(p1.id);
  });

  it('should query across cell boundaries', () => {
    const grid = new SpatialHashGrid(1);
    const particles = [];
    for (let i = 0; i < 5; i++) {
      for (let j = 0; j < 5; j++) {
        for (let k = 0; k < 5; k++) {
          particles.push(new MatterParticle({
            position: [i * 0.4, j * 0.4, k * 0.4],
          }));
        }
      }
    }
    grid.rebuild(particles);
    const result = grid.query([0.5, 0.5, 0.5], 0.5);
    expect(result.length).toBeGreaterThan(1);
    expect(result.length).toBeLessThan(particles.length);

    for (const p of result) {
      const dx = p.position[0] - 0.5;
      const dy = p.position[1] - 0.5;
      const dz = p.position[2] - 0.5;
      expect(dx * dx + dy * dy + dz * dz).toBeLessThanOrEqual(0.26);
    }
  });

  it('should handle empty grid query', () => {
    const grid = new SpatialHashGrid(1);
    const result = grid.query([0, 0, 0], 1);
    expect(result).toEqual([]);
  });

  it('should clear grid', () => {
    const grid = new SpatialHashGrid(1);
    const p = new MatterParticle({ position: [0, 0, 0] });
    grid.insert(p);
    grid.clear();
    const result = grid.query([0, 0, 0], 1);
    expect(result).toEqual([]);
  });

  it('should only return active particles after rebuild', () => {
    const grid = new SpatialHashGrid(1);
    const alive = new MatterParticle({ position: [0, 0, 0], lifecycle: 'alive' });
    const dead = new MatterParticle({ position: [0.5, 0, 0], lifecycle: 'dead' });
    grid.rebuild([alive, dead]);
    const result = grid.query([0, 0, 0], 2);
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(alive.id);
  });
});
