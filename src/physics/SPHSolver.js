import { SpatialHashGrid } from './SpatialHashGrid.js';
import { Constants } from '../core/Constants.js';

const GAMMA = 5 / 3;
const KERNEL_SUPPORT = 2.0;
const DENSITY_FLOOR = 1e-20;
const PRESSURE_FLOOR = 1e-20;
const ETA_SMOOTH = 1.2;
const ARTIFICIAL_VISC_ALPHA = 1.0;
const ARTIFICIAL_VISC_BETA = 2.0;
const COOLING_BETA = 10;

function wCubicSpline(r, h, norm) {
  const q = r / h;
  if (q < 0) return 0;
  if (q < 1) return norm * (1 - 1.5 * q * q + 0.75 * q * q * q);
  if (q < 2) return norm * 0.25 * (2 - q) * (2 - q) * (2 - q);
  return 0;
}

function gradWCubicSpline(r, h, norm, dir) {
  const q = r / h;
  if (q < 0.001 || q >= 2) return [0, 0, 0];
  let dwdq;
  if (q < 1) {
    dwdq = norm * (-3 * q + 2.25 * q * q);
  } else {
    dwdq = norm * (-0.75 * (2 - q) * (2 - q));
  }
  const dwdr = dwdq / h;
  const invR = 1 / r;
  return [dwdr * dir[0] * invR, dwdr * dir[1] * invR, dwdr * dir[2] * invR];
}

export class SPHSolver {
  constructor() {
    this.grid = new SpatialHashGrid(1);
    this._neighborCounts = [];
    this._overload = false;
    this._overloadThreshold = 100;
  }

  get overload() { return this._overload; }

  computeDensity(particles, smoothingLength) {
    this.grid.cellSize = smoothingLength * KERNEL_SUPPORT;
    this.grid.rebuild(particles);

    this._neighborCounts = [];
    this._overload = false;

    for (const p of particles) {
      if (!p.isActive) {
        this._neighborCounts.push(0);
        continue;
      }

      const h = smoothingLength;
      const norm3D = 1 / (Math.PI * h * h * h);
      const support = h * KERNEL_SUPPORT;

      const neighbors = this.grid.query(p.position, support);
      this._neighborCounts.push(neighbors.length);

      if (neighbors.length > this._overloadThreshold) {
        this._overload = true;
      }

      let rho = 0;
      for (const n of neighbors) {
        if (n.id === p.id) continue;
        const dx = n.position[0] - p.position[0];
        const dy = n.position[1] - p.position[1];
        const dz = n.position[2] - p.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
        rho += n.mass * wCubicSpline(r, h, norm3D);
      }

      p.density = Math.max(rho, DENSITY_FLOOR);
    }
  }

  computePressure(particles) {
    for (const p of particles) {
      if (!p.isActive) continue;
      p.pressure = Math.max((GAMMA - 1) * p.density * p.internalEnergy, PRESSURE_FLOOR);
    }
  }

  computeHydroForces(particles, dt, smoothingLength) {
    this.grid.cellSize = smoothingLength * KERNEL_SUPPORT;
    this.grid.rebuild(particles);

    const accelerations = new Map();
    const duDt = new Map();

    for (const p of particles) {
      if (!p.isActive) continue;
      accelerations.set(p.id, [0, 0, 0]);
      duDt.set(p.id, 0);
    }

    const h = smoothingLength;
    const norm3D = 1 / (Math.PI * h * h * h);
    const support = h * KERNEL_SUPPORT;

    const processed = new Set();

    for (const pi of particles) {
      if (!pi.isActive) continue;

      const neighbors = this.grid.query(pi.position, support);

      for (const pj of neighbors) {
        if (pj.id === pi.id) continue;
        const pairKey = pi.id < pj.id ? `${pi.id}:${pj.id}` : `${pj.id}:${pi.id}`;
        if (processed.has(pairKey)) continue;
        processed.add(pairKey);

        if (!pj.isActive) continue;

        const dx = pj.position[0] - pi.position[0];
        const dy = pj.position[1] - pi.position[1];
        const dz = pj.position[2] - pi.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (r < 0.001) continue;

        const dir = [dx, dy, dz];
        const gradW = gradWCubicSpline(r, h, norm3D, dir);

        const dvx = pj.velocity[0] - pi.velocity[0];
        const dvy = pj.velocity[1] - pi.velocity[1];
        const dvz = pj.velocity[2] - pi.velocity[2];

        const dvDotDr = dvx * dx + dvy * dy + dvz * dz;
        const h2 = h * h;

        let Pi = 0;
        if (dvDotDr < 0) {
          const rho_ij = 0.5 * (pi.density + pj.density);
          const c_i = Math.sqrt(GAMMA * pi.pressure / pi.density);
          const c_j = Math.sqrt(GAMMA * pj.pressure / pj.density);
          const c_ij = 0.5 * (c_i + c_j);
          const v_sig = c_ij - ARTIFICIAL_VISC_BETA * dvDotDr / (r + 0.01 * h);
          const mu_ij = h * dvDotDr / (r * r + 0.01 * h2);
          Pi = (-ARTIFICIAL_VISC_ALPHA * c_ij * mu_ij + ARTIFICIAL_VISC_BETA * mu_ij * mu_ij) / rho_ij;
        }

        const term_i = pi.pressure / (pi.density * pi.density);
        const term_j = pj.pressure / (pj.density * pj.density);
        const forceScale = pi.mass * pj.mass * (term_i + term_j + Pi);

        const acc_i = accelerations.get(pi.id);
        acc_i[0] -= forceScale * gradW[0];
        acc_i[1] -= forceScale * gradW[1];
        acc_i[2] -= forceScale * gradW[2];

        const acc_j = accelerations.get(pj.id);
        acc_j[0] += forceScale * gradW[0];
        acc_j[1] += forceScale * gradW[1];
        acc_j[2] += forceScale * gradW[2];

        const vDotGradW = dvx * gradW[0] + dvy * gradW[1] + dvz * gradW[2];
        const duPair = 0.5 * pj.mass * (term_i + term_j + Pi) * vDotGradW;

        duDt.set(pi.id, duDt.get(pi.id) + duPair);
        duDt.set(pj.id, duDt.get(pj.id) + duPair);
      }
    }

    for (const p of particles) {
      if (!p.isActive) continue;
      const acc = accelerations.get(p.id);
      if (acc) {
        p._sphAcceleration = acc;
      }
      const du = duDt.get(p.id) || 0;
      p._duDtHydro = du;
    }
  }

  integrateInternalEnergy(particles, dt, coolingBeta) {
    const beta = coolingBeta ?? COOLING_BETA;

    for (const p of particles) {
      if (!p.isActive) continue;

      const duHydro = p._duDtHydro || 0;
      let du = duHydro;

      if (duHydro > 0) {
        p._shockHeating = duHydro;
      }

      if (p.density > DENSITY_FLOOR) {
        const t_dyn = 1 / Math.sqrt(Constants.G_solar_km * p.density);
        const t_cool = beta * t_dyn;
        const duCool = -p.internalEnergy / (t_cool + 1e-15);
        du += duCool;
        p._coolingRate = duCool;
      }

      p.internalEnergy = Math.max(p.internalEnergy + du * dt, 0);
      p.temperature = p.internalEnergy * 1e7;
    }
  }

  getNeighborStats() {
    if (this._neighborCounts.length === 0) return { avg: 0, max: 0, min: 0 };
    let sum = 0, max = 0, min = Infinity;
    for (const c of this._neighborCounts) {
      sum += c;
      if (c > max) max = c;
      if (c < min) min = c;
    }
    return { avg: sum / this._neighborCounts.length, max, min };
  }
}
