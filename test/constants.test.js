import { describe, it, expect } from 'vitest';
import { Constants } from '../src/core/Constants.js';

describe('Constants', () => {
  it('should have physical constants', () => {
    expect(Constants.G).toBe(6.674e-11);
    expect(Constants.c).toBe(2.998e8);
    expect(Constants.M_sun).toBe(1.989e30);
    expect(Constants.G_solar_km).toBeGreaterThan(0);
  });

  it('should compute Schwarzschild radius in km', () => {
    const rs1 = Constants.schwarzschildRadiusKm(1);
    const rs10 = Constants.schwarzschildRadiusKm(10);
    expect(rs1).toBeCloseTo(2.95, 1);
    expect(rs10).toBeCloseTo(29.5, 1);
  });

  it('should compute Schwarzschild radius in meters', () => {
    const rs = Constants.schwarzschildRadius(1);
    expect(rs).toBeGreaterThan(0);
    expect(rs).toBeCloseTo(2953.85, 0);
  });

  it('should compute ISCO radius for Schwarzschild BH', () => {
    const isco = Constants.iscoRadius(0);
    expect(isco).toBeCloseTo(6, 1);
  });

  it('should compute ISCO radius for extremal Kerr BH', () => {
    const iscoPrograde = Constants.iscoRadius(0.998);
    const iscoRetrograde = Constants.iscoRadius(-0.998);
    expect(iscoPrograde).toBeGreaterThan(0);
    expect(iscoRetrograde).toBeGreaterThan(0);
    expect(iscoPrograde).toBeCloseTo(1.24, 0);
  });

  it('should compute orbital velocity', () => {
    const v = Constants.orbitalVelocity(1, 100);
    expect(v).toBeGreaterThan(0);
    expect(isFinite(v)).toBe(true);
  });

  it('should compute orbital period', () => {
    const T = Constants.orbitalPeriod(1, 100);
    expect(T).toBeGreaterThan(0);
    expect(isFinite(T)).toBe(true);
  });

  it('should compute tidal disruption radius', () => {
    const rtd = Constants.tidalDisruptionRadius(100, 1, 1);
    expect(rtd).toBeGreaterThan(0);
    expect(isFinite(rtd)).toBe(true);
    expect(rtd).toBeCloseTo(Constants.R_sun_km * Math.cbrt(100), 6);
  });

  it('should compute chirp mass', () => {
    const Mc = Constants.chirpMass(10, 5);
    expect(Mc).toBeGreaterThan(0);
    expect(isFinite(Mc)).toBe(true);
  });

  it('should have proper configuration values', () => {
    expect(Constants.softening).toBe(0.01);
    expect(Constants.dt_max).toBe(0.01);
    expect(Constants.barnesHutTheta).toBe(0.5);
    expect(Constants.barnesHutThreshold).toBe(100);
  });
});
