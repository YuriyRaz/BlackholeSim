import { describe, it, expect } from 'vitest';
import { RNG } from '../src/core/RNG.js';

describe('RNG', () => {
  it('should produce deterministic sequence from seed', () => {
    const rng1 = new RNG(42);
    const rng2 = new RNG(42);
    for (let i = 0; i < 100; i++) {
      expect(rng1.next()).toBe(rng2.next());
    }
  });

  it('should produce different sequences for different seeds', () => {
    const rng1 = new RNG(42);
    const rng2 = new RNG(99);
    let same = true;
    for (let i = 0; i < 10; i++) {
      if (rng1.next() !== rng2.next()) same = false;
    }
    expect(same).toBe(false);
  });

  it('should produce values in [0, 1)', () => {
    const rng = new RNG(12345);
    for (let i = 0; i < 1000; i++) {
      const v = rng.next();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it('should produce float in range', () => {
    const rng = new RNG(42);
    for (let i = 0; i < 100; i++) {
      const v = rng.nextFloat(5, 10);
      expect(v).toBeGreaterThanOrEqual(5);
      expect(v).toBeLessThan(10);
    }
  });

  it('should produce int in range', () => {
    const rng = new RNG(42);
    for (let i = 0; i < 100; i++) {
      const v = rng.nextInt(0, 10);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(10);
      expect(Number.isInteger(v)).toBe(true);
    }
  });

  it('should shuffle array deterministically', () => {
    const rng1 = new RNG(42);
    const rng2 = new RNG(42);
    const arr1 = [1, 2, 3, 4, 5];
    const arr2 = [1, 2, 3, 4, 5];
    rng1.shuffle(arr1);
    rng2.shuffle(arr2);
    expect(arr1).toEqual(arr2);
  });
});
