import { describe, it, expect } from 'vitest';
import { generatePolytrope, clampParticleCount } from '../src/physics/Polytrope.js';
import { Constants } from '../src/core/Constants.js';

describe('Polytrope', () => {
  it('should generate correct number of particles', () => {
    const result = generatePolytrope({ mass: 1, radius: 1, numParticles: 500, seed: 42 });
    expect(result.particles.length).toBe(500);
  });

  it('should conserve total mass', () => {
    const result = generatePolytrope({ mass: 1, radius: 1, numParticles: 1000, seed: 42 });
    const totalMass = result.particles.reduce((sum, p) => sum + p.mass, 0);
    expect(totalMass).toBeCloseTo(1, 5);
  });

  it('should be deterministic with same seed', () => {
    const a = generatePolytrope({ mass: 1, radius: 1, numParticles: 500, seed: 42 });
    const b = generatePolytrope({ mass: 1, radius: 1, numParticles: 500, seed: 42 });
    for (let i = 0; i < 500; i++) {
      expect(a.particles[i].position[0]).toBe(b.particles[i].position[0]);
      expect(a.particles[i].mass).toBe(b.particles[i].mass);
      expect(a.particles[i].density).toBe(b.particles[i].density);
    }
  });

  it('should produce spherical density profile with central concentration', () => {
    const result = generatePolytrope({ mass: 1, radius: 1, numParticles: 1000, seed: 42 });
    let avgCentralDensity = 0;
    let centralCount = 0;
    let avgOuterDensity = 0;
    let outerCount = 0;
    for (const p of result.particles) {
      const r = Math.sqrt(p.position[0] ** 2 + p.position[1] ** 2 + p.position[2] ** 2);
      if (r < result.radiusKm * 0.3) {
        avgCentralDensity += p.density;
        centralCount++;
      }
      if (r > result.radiusKm * 0.8) {
        avgOuterDensity += p.density;
        outerCount++;
      }
    }
    avgCentralDensity /= centralCount;
    avgOuterDensity /= outerCount;
    expect(avgCentralDensity).toBeGreaterThan(avgOuterDensity);
  });

  it('should have γ=5/3', () => {
    const result = generatePolytrope({ mass: 1, radius: 1, numParticles: 100, seed: 42 });
    expect(result.gamma).toBeCloseTo(5 / 3, 10);
    expect(result.n).toBeCloseTo(1.5, 10);
  });

  it('should assign internal energy to particles', () => {
    const result = generatePolytrope({ mass: 1, radius: 1, numParticles: 100, seed: 42 });
    for (const p of result.particles) {
      expect(p.internalEnergy).toBeGreaterThan(0);
      expect(p.temperature).toBeGreaterThan(0);
    }
  });

  it('should clamp particle count', () => {
    expect(clampParticleCount(0.1)).toBe(200);
    expect(clampParticleCount(1)).toBe(1000);
    expect(clampParticleCount(2.5)).toBe(2000);
    expect(clampParticleCount(5)).toBe(2000);
  });

  it('should adjust to different masses', () => {
    const small = generatePolytrope({ mass: 0.5, radius: 1, numParticles: 200, seed: 42 });
    const large = generatePolytrope({ mass: 2, radius: 1, numParticles: 200, seed: 42 });
    const massSmall = small.particles.reduce((s, p) => s + p.mass, 0);
    const massLarge = large.particles.reduce((s, p) => s + p.mass, 0);
    expect(massSmall).toBeCloseTo(0.5, 5);
    expect(massLarge).toBeCloseTo(2, 5);
  });
});
