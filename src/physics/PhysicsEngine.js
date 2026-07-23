import { Constants } from '../core/Constants.js';
import { Body } from '../objects/Body.js';
import { BlackHole } from '../objects/BlackHole.js';
import { Star } from '../objects/Star.js';
import { GasParticle } from '../objects/GasParticle.js';
import { MatterParticle } from '../objects/MatterParticle.js';
import { BarnesHut } from './BarnesHut.js';
import { SPHSolver } from './SPHSolver.js';
import { ConservationLedger } from './ConservationLedger.js';

export class PhysicsEngine {
  constructor() {
    this.bodies = [];
    this.gasParticles = [];
    this.matterParticles = [];
    this.simTime = 0;
    this.accretionRate = 0;
    this.gwFrequency = 0;
    this.gwStrain = 0;
    this.gwPhase = 0;
    this.gwLuminosity = 0;
    this._playing = true;
    this._speedMultiplier = 1.0;
    this._snapshots = [];
    this._snapshotCounter = 0;
    this._accretedMass = 0;
    this._accretionWindow = [];
    this._mergedBH = null;
    this._barnesHut = new BarnesHut();
    this._fallbackRate = 0;
    this._fallbackStartTime = -1;
    this._fallbackMass = 0;
    this._bhPairs = [];
    this._particleTrails = new Map();
    this._trailMaxLength = 50;
    this._gwRippleFadeStrain = 0;
    this._gwRippleFadeTime = 0;
    this._binaryOrbitSeparations = new Map();
    this._sphSolver = new SPHSolver();
    this._ledger = new ConservationLedger();
    this._smoothingLength = 0;
    this._dtHydro = 0;
    this._coolingBeta = Constants.coolingBeta;
    this._bhAccretionEnergy = 0;
  }

  get playing() { return this._playing; }
  get speedMultiplier() { return this._speedMultiplier; }

  set playing(val) { this._playing = val; }
  set speedMultiplier(val) { this._speedMultiplier = Math.max(0.1, Math.min(10, val)); }

  addObject(body) {
    this.bodies.push(body);
    body.saveInitialState();
  }

  removeObject(id) {
    this.bodies = this.bodies.filter(b => b.id !== id);
  }

  getObjectsByType(type) {
    return this.bodies.filter(b => b.type === type);
  }

  addGasParticle(particle) {
    this.gasParticles.push(particle);
    particle.saveInitialState();
  }

  reset() {
    for (const b of this.bodies) b.reset();
    for (const g of this.gasParticles) g.reset();
    for (const p of this.matterParticles) p.reset();
    this.matterParticles = [];
    this.simTime = 0;
    this.accretionRate = 0;
    this.gwFrequency = 0;
    this.gwStrain = 0;
    this.gwPhase = 0;
    this.gwLuminosity = 0;
    this._accretedMass = 0;
    this._accretionWindow = [];
    this._snapshots = [];
    this._snapshotCounter = 0;
    this._mergedBH = null;
    this._fallbackRate = 0;
    this._fallbackStartTime = -1;
    this._fallbackMass = 0;
    this._bhAccretionEnergy = 0;
    this._bhPairs = [];
    this._particleTrails = new Map();
    this._gwRippleFadeStrain = 0;
    this._gwRippleFadeTime = 0;
    this._binaryOrbitSeparations = new Map();
    this._ledger.reset();
  }

  loadPreset(presetData) {
    this.reset();
    this.bodies = [];
    this.gasParticles = [];
    this.matterParticles = [];
    if (presetData.bodies) {
      for (const bd of presetData.bodies) {
        let body;
        if (bd.type === 'blackhole') {
          body = new BlackHole(bd);
        } else if (bd.type === 'star') {
          body = new Star(bd);
        } else {
          body = new Body(bd);
        }
        this.addObject(body);
      }
    }
    if (presetData.gas) {
      for (const gd of presetData.gas) {
        this.addGasParticle(new GasParticle(gd));
      }
    }
    if (presetData.matterParticles) {
      for (const pd of presetData.matterParticles) {
        this.matterParticles.push(new MatterParticle(pd));
      }
    }
  }

  step(dt) {
    if (!this._playing) return;
    const effectiveDt = dt * this._speedMultiplier;
    this._blackHoles = this.bodies.filter(b => b.type === 'blackhole');

    const matterDt = this._computeMatterTimestep();
    const maxDt = Math.min(Constants.dt_max, matterDt);
    const substeps = Math.max(1, Math.ceil(effectiveDt / maxDt));
    const subDt = effectiveDt / substeps;

    for (let s = 0; s < substeps; s++) {
      this._integrateGravity(subDt);
      this._integrateMatterGravity(subDt);
      this._integrateMatterSPH(subDt);
      this._integrateGas(subDt);
      this._handleTidalDisruption(subDt);
      this._classifyBoundParticles();
      this._computeFallbackRate(subDt);
      this._updatePhaseTransitions(subDt);
      this._captureParticlesAtISCO(subDt);
      this._computeAccretion(subDt);
      this._computeGravitationalWaves(subDt);
      for (const body of this.bodies) {
        if (!body.fixed && !body.disrupted) {
          body.updateTrail();
        }
      }
      this._computeBHPairs();
      this.simTime += subDt;
      this._snapshotCounter++;
    }
  }

  _computeFallbackRate(dt) {
    const active = this.matterParticles.filter(p => p.isActive);
    if (active.length === 0) return;

    const blackHoles = this._blackHoles;
    if (blackHoles.length === 0) return;
    const bh = blackHoles[0];

    const dR = Constants.tidalDisruptionRadius(bh.mass, 1, 1);
    const fallbackRadius = dR * 2.0;
    let returningMass = 0;
    let returningCount = 0;

    for (const p of active) {
      if (p.phase !== 'debris' && p.phase !== 'disk') continue;
      if (p._wasReturning === undefined) p._wasReturning = false;

      const dx = p.position[0] - bh.position[0];
      const dy = p.position[1] - bh.position[1];
      const dz = p.position[2] - bh.position[2];
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);

      const vr = (dx * p.velocity[0] + dy * p.velocity[1] + dz * p.velocity[2]) / (r + 1e-15);

      const isReturning = r < fallbackRadius && vr < 0;
      if (isReturning && !p._wasReturning) {
        returningMass += p.mass;
        returningCount++;
      }
      p._wasReturning = r < fallbackRadius;
    }

    this._fallbackRate = returningMass / Math.max(dt, 1e-15);
    if (returningCount > 0 && this._fallbackStartTime < 0) {
      this._fallbackStartTime = this.simTime;
    }
  }

  _computeBinaryGWMetrics(bi, bj, separationKm) {
    const totalMassSolar = bi.mass + bj.mass;
    const separationM = Math.max(separationKm * 1000, 1);
    const fGW = Math.sqrt(Constants.G_solar_km * totalMassSolar / Math.pow(separationKm, 3)) / Math.PI;
    const chirpMassKg = Constants.chirpMass(bi.mass, bj.mass) * Constants.M_sun;
    const m1Kg = bi.mass * Constants.M_sun;
    const m2Kg = bj.mass * Constants.M_sun;
    const totalMassKg = totalMassSolar * Constants.M_sun;
    const strain = (4 / separationM) *
      Math.pow(Constants.G * chirpMassKg / (Constants.c * Constants.c), 5 / 3) *
      Math.pow(Math.PI * fGW / Constants.c, 2 / 3);
    const luminosity = (32 / 5) * Math.pow(Constants.G, 4) *
      m1Kg * m1Kg * m2Kg * m2Kg * totalMassKg /
      (Math.pow(Constants.c, 5) * Math.pow(separationM, 5));

    return { frequency: fGW, strain, luminosity };
  }

  _petersDecayRateKmPerSec(m1Solar, m2Solar, separationKm) {
    const m1Kg = m1Solar * Constants.M_sun;
    const m2Kg = m2Solar * Constants.M_sun;
    const totalMassKg = m1Kg + m2Kg;
    const separationM = Math.max(separationKm * 1000, 1);
    const daDtMeters = -(64 / 5) * Math.pow(Constants.G, 3) * m1Kg * m2Kg * totalMassKg /
      (Math.pow(Constants.c, 5) * Math.pow(separationM, 3));
    return daDtMeters / 1000;
  }

  _applyGWOrbitalDecay(bi, bj, dt) {
    if (bi.fixed || bj.fixed) return;

    const dx = bj.position[0] - bi.position[0];
    const dy = bj.position[1] - bi.position[1];
    const dz = bj.position[2] - bi.position[2];
    const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (r < 0.001) return;

    const pairKey = [bi.id, bj.id].sort((a, b) => a - b).join(':');
    const targetR = this._binaryOrbitSeparations.get(pairKey) ?? r;
    const decayRate = this._petersDecayRateKmPerSec(bi.mass, bj.mass, targetR);
    if (!Number.isFinite(decayRate) || decayRate >= 0) return;

    const maxShrink = targetR * 0.05;
    const dr = Math.max(decayRate * dt, -maxShrink);
    if (dr >= 0) return;

    const totalMass = bi.mass + bj.mass;
    const newR = Math.max(targetR + dr, 0.001);
    this._binaryOrbitSeparations.set(pairKey, newR);
    const n = [dx / r, dy / r, dz / r];
    const com = [
      (bi.position[0] * bi.mass + bj.position[0] * bj.mass) / totalMass,
      (bi.position[1] * bi.mass + bj.position[1] * bj.mass) / totalMass,
      (bi.position[2] * bi.mass + bj.position[2] * bj.mass) / totalMass
    ];
    const comVel = [
      (bi.velocity[0] * bi.mass + bj.velocity[0] * bj.mass) / totalMass,
      (bi.velocity[1] * bi.mass + bj.velocity[1] * bj.mass) / totalMass,
      (bi.velocity[2] * bi.mass + bj.velocity[2] * bj.mass) / totalMass
    ];
    const relVel = [
      bj.velocity[0] - bi.velocity[0],
      bj.velocity[1] - bi.velocity[1],
      bj.velocity[2] - bi.velocity[2]
    ];
    const radialSpeed = relVel[0] * n[0] + relVel[1] * n[1] + relVel[2] * n[2];
    let tangent = [
      relVel[0] - radialSpeed * n[0],
      relVel[1] - radialSpeed * n[1],
      relVel[2] - radialSpeed * n[2]
    ];
    let tangentLen = Math.sqrt(tangent[0] ** 2 + tangent[1] ** 2 + tangent[2] ** 2);
    if (tangentLen < 0.001) {
      tangent = Math.abs(n[1]) < 0.9 ? [-n[2], 0, n[0]] : [1, 0, 0];
      tangentLen = Math.sqrt(tangent[0] ** 2 + tangent[1] ** 2 + tangent[2] ** 2);
    }
    const t = [tangent[0] / tangentLen, tangent[1] / tangentLen, tangent[2] / tangentLen];
    const circularSpeed = Math.sqrt(Constants.G_solar_km * totalMass / newR);
    const inwardSpeed = dr / dt;
    const newRelVel = [
      t[0] * circularSpeed + n[0] * inwardSpeed,
      t[1] * circularSpeed + n[1] * inwardSpeed,
      t[2] * circularSpeed + n[2] * inwardSpeed
    ];

    bi.position = [
      com[0] - n[0] * newR * (bj.mass / totalMass),
      com[1] - n[1] * newR * (bj.mass / totalMass),
      com[2] - n[2] * newR * (bj.mass / totalMass)
    ];
    bj.position = [
      com[0] + n[0] * newR * (bi.mass / totalMass),
      com[1] + n[1] * newR * (bi.mass / totalMass),
      com[2] + n[2] * newR * (bi.mass / totalMass)
    ];
    bi.velocity = [
      comVel[0] - newRelVel[0] * (bj.mass / totalMass),
      comVel[1] - newRelVel[1] * (bj.mass / totalMass),
      comVel[2] - newRelVel[2] * (bj.mass / totalMass)
    ];
    bj.velocity = [
      comVel[0] + newRelVel[0] * (bi.mass / totalMass),
      comVel[1] + newRelVel[1] * (bi.mass / totalMass),
      comVel[2] + newRelVel[2] * (bi.mass / totalMass)
    ];
  }

  _shouldMergeBlackHoles(bi, bj) {
    return bi.distanceTo(bj) <= Math.max(bi.rs + bj.rs, Constants.softening);
  }

  _estimateRemnantSpin(bi, bj) {
    const totalMass = bi.mass + bj.mass;
    const weightedSpin = (Math.abs(bi.spin || 0) * bi.mass + Math.abs(bj.spin || 0) * bj.mass) / totalMass;
    return Math.max(0.67, Math.min(0.98, weightedSpin + 0.35));
  }

  _ringdownFrequency(massSolar, spin) {
    const massKg = massSolar * Constants.M_sun;
    const qnmFactor = 1 - 0.63 * Math.pow(Math.max(1 - spin, 0.001), 0.3);
    return Math.pow(Constants.c, 3) / (2 * Math.PI * Constants.G * massKg) * qnmFactor;
  }

  _mergeBlackHoles(bi, bj, peakFrequency, peakStrain) {
    if (!this.bodies.includes(bi) || !this.bodies.includes(bj)) return;

    const totalMass = bi.mass + bj.mass;
    const remnantMass = totalMass * 0.95;
    const spin = this._estimateRemnantSpin(bi, bj);
    const position = [
      (bi.position[0] * bi.mass + bj.position[0] * bj.mass) / totalMass,
      (bi.position[1] * bi.mass + bj.position[1] * bj.mass) / totalMass,
      (bi.position[2] * bi.mass + bj.position[2] * bj.mass) / totalMass
    ];
    const velocity = [
      (bi.velocity[0] * bi.mass + bj.velocity[0] * bj.mass) / totalMass,
      (bi.velocity[1] * bi.mass + bj.velocity[1] * bj.mass) / totalMass,
      (bi.velocity[2] * bi.mass + bj.velocity[2] * bj.mass) / totalMass
    ];
    const remnant = new BlackHole({
      mass: remnantMass,
      position,
      velocity,
      spin,
      fixed: bi.fixed && bj.fixed,
      name: `Remnant_${bi.name}_${bj.name}`
    });
    remnant.trail = [...bi.trail.slice(-50), ...bj.trail.slice(-50)].slice(-Constants.trailMaxPoints);

    this.bodies = this.bodies.filter(body => body !== bi && body !== bj);
    this.addObject(remnant);
    this._binaryOrbitSeparations.delete([bi.id, bj.id].sort((a, b) => a - b).join(':'));
    this._mergedBH = {
      id: remnant.id,
      mass: remnantMass,
      spin,
      mergeTime: this.simTime,
      peakFrequency,
      peakStrain: Math.max(peakStrain, 0.001),
      ringdownFrequency: this._ringdownFrequency(remnantMass, spin),
      dampingTime: 0.2
    };
    this._gwRippleFadeStrain = this._mergedBH.peakStrain;
    this._gwRippleFadeTime = this.simTime;
  }

  _integrateGravity(dt) {
    const n = this.bodies.length;
    const useBarnesHut = n > Constants.barnesHutThreshold;
    
    if (useBarnesHut) {
      this._barnesHut.build(this.bodies);
    }

    const acc = new Array(n);
    for (let i = 0; i < n; i++) acc[i] = [0, 0, 0];

    for (let i = 0; i < n; i++) {
      if (this.bodies[i].fixed) continue;
      const bi = this.bodies[i];
      
      if (useBarnesHut) {
        const accBH = this._barnesHut.computeAcceleration(bi);
        acc[i][0] = accBH[0];
        acc[i][1] = accBH[1];
        acc[i][2] = accBH[2];
      } else {
        for (let j = 0; j < n; j++) {
          if (i === j) continue;
          const bj = this.bodies[j];
          const dx = bj.position[0] - bi.position[0];
          const dy = bj.position[1] - bi.position[1];
          const dz = bj.position[2] - bi.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * bj.mass / (r2 * r);
          acc[i][0] += f * dx;
          acc[i][1] += f * dy;
          acc[i][2] += f * dz;

          if (bj.type === 'blackhole' && bj.spin !== 0) {
            const fd = bj.frameDraggingForce(bi.position, bi.velocity);
            acc[i][0] += fd[0];
            acc[i][1] += fd[1];
            acc[i][2] += fd[2];
          }
        }
      }
    }

    for (let i = 0; i < n; i++) {
      if (this.bodies[i].fixed) continue;
      const b = this.bodies[i];
      b.position[0] += b.velocity[0] * dt + 0.5 * acc[i][0] * dt * dt;
      b.position[1] += b.velocity[1] * dt + 0.5 * acc[i][1] * dt * dt;
      b.position[2] += b.velocity[2] * dt + 0.5 * acc[i][2] * dt * dt;
    }

    const newAcc = new Array(n);
    for (let i = 0; i < n; i++) newAcc[i] = [0, 0, 0];

    if (useBarnesHut) {
      this._barnesHut.build(this.bodies);
    }

    for (let i = 0; i < n; i++) {
      if (this.bodies[i].fixed) continue;
      const bi = this.bodies[i];
      
      if (useBarnesHut) {
        const accBH = this._barnesHut.computeAcceleration(bi);
        newAcc[i][0] = accBH[0];
        newAcc[i][1] = accBH[1];
        newAcc[i][2] = accBH[2];
      } else {
        for (let j = 0; j < n; j++) {
          if (i === j) continue;
          const bj = this.bodies[j];
          const dx = bj.position[0] - bi.position[0];
          const dy = bj.position[1] - bi.position[1];
          const dz = bj.position[2] - bi.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * bj.mass / (r2 * r);
          newAcc[i][0] += f * dx;
          newAcc[i][1] += f * dy;
          newAcc[i][2] += f * dz;

          if (bj.type === 'blackhole' && bj.spin !== 0) {
            const fd = bj.frameDraggingForce(bi.position, bi.velocity);
            newAcc[i][0] += fd[0];
            newAcc[i][1] += fd[1];
            newAcc[i][2] += fd[2];
          }
        }
      }
    }

    for (let i = 0; i < n; i++) {
      if (this.bodies[i].fixed) continue;
      const b = this.bodies[i];
      b.velocity[0] += 0.5 * (acc[i][0] + newAcc[i][0]) * dt;
      b.velocity[1] += 0.5 * (acc[i][1] + newAcc[i][1]) * dt;
      b.velocity[2] += 0.5 * (acc[i][2] + newAcc[i][2]) * dt;
    }
  }

  _integrateGas(dt) {
    const blackHoles = this._blackHoles;

    const accelerations = [];
    for (const gp of this.gasParticles) {
      if (gp.accreted) {
        accelerations.push([0, 0, 0]);
        continue;
      }
      let ax = 0, ay = 0, az = 0;

      for (const bh of blackHoles) {
        const dx = bh.position[0] - gp.position[0];
        const dy = bh.position[1] - gp.position[1];
        const dz = bh.position[2] - gp.position[2];
        const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
        const r = Math.sqrt(r2);
        const f = Constants.G_solar_km * bh.mass / (r2 * r);
        ax += f * dx;
        ay += f * dy;
        az += f * dz;

        if (bh.spin !== 0) {
          const fd = bh.frameDraggingForce(gp.position, gp.velocity);
          ax += fd[0];
          ay += fd[1];
          az += fd[2];
        }

        if (bh.isInErgosphere(gp.position)) {
          const spinDir = bh.spinAxis;
          const speed = Math.sqrt(gp.velocity[0] ** 2 + gp.velocity[1] ** 2 + gp.velocity[2] ** 2);
          const perp = [
            -dz * spinDir[1] + dy * spinDir[2],
            dx * spinDir[2] - dz * spinDir[0],
            dy * spinDir[0] - dx * spinDir[1]
          ];
          const perpLen = Math.sqrt(perp[0] ** 2 + perp[1] ** 2 + perp[2] ** 2);
          if (perpLen > 0.001 && speed > 0.001) {
            const targetSpeed = speed;
            const targetVel = [
              perp[0] / perpLen * targetSpeed,
              perp[1] / perpLen * targetSpeed,
              perp[2] / perpLen * targetSpeed
            ];
            const ergoStrength = 0.5;
            ax += ergoStrength * (targetVel[0] - gp.velocity[0]) / dt;
            ay += ergoStrength * (targetVel[1] - gp.velocity[1]) / dt;
            az += ergoStrength * (targetVel[2] - gp.velocity[2]) / dt;
          }
        }
      }
      accelerations.push([ax, ay, az]);
    }

    for (let i = 0; i < this.gasParticles.length; i++) {
      const gp = this.gasParticles[i];
      if (gp.accreted) continue;
      const [ax, ay, az] = accelerations[i];

      gp.position[0] += gp.velocity[0] * dt + 0.5 * ax * dt * dt;
      gp.position[1] += gp.velocity[1] * dt + 0.5 * ay * dt * dt;
      gp.position[2] += gp.velocity[2] * dt + 0.5 * az * dt * dt;
    }

    const newAccelerations = [];
    for (const gp of this.gasParticles) {
      if (gp.accreted) {
        newAccelerations.push([0, 0, 0]);
        continue;
      }
      let ax = 0, ay = 0, az = 0;

      for (const bh of blackHoles) {
        const dx = bh.position[0] - gp.position[0];
        const dy = bh.position[1] - gp.position[1];
        const dz = bh.position[2] - gp.position[2];
        const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
        const r = Math.sqrt(r2);
        const f = Constants.G_solar_km * bh.mass / (r2 * r);
        ax += f * dx;
        ay += f * dy;
        az += f * dz;

        if (bh.spin !== 0) {
          const fd = bh.frameDraggingForce(gp.position, gp.velocity);
          ax += fd[0];
          ay += fd[1];
          az += fd[2];
        }
      }
      newAccelerations.push([ax, ay, az]);
    }

    for (let i = 0; i < this.gasParticles.length; i++) {
      const gp = this.gasParticles[i];
      if (gp.accreted) continue;
      const [oldAx, oldAy, oldAz] = accelerations[i];
      const [newAx, newAy, newAz] = newAccelerations[i];

      gp.velocity[0] += 0.5 * (oldAx + newAx) * dt;
      gp.velocity[1] += 0.5 * (oldAy + newAy) * dt;
      gp.velocity[2] += 0.5 * (oldAz + newAz) * dt;

      const v2 = gp.velocity[0] ** 2 + gp.velocity[1] ** 2 + gp.velocity[2] ** 2;
      gp.temperature = v2 * 1e4;
      gp.age += dt;
    }

    this.gasParticles = this.gasParticles.filter(gp => !gp.accreted);
  }

  _computeAccretion(dt) {
    const blackHoles = this._blackHoles;
    let accretedThisStep = 0;

    for (const gp of this.gasParticles) {
      if (gp.accreted) continue;
      for (const bh of blackHoles) {
        if (bh.isInsideISCO(gp.position)) {
          const dx = gp.position[0] - bh.position[0];
          const dy = gp.position[1] - bh.position[1];
          const dz = gp.position[2] - bh.position[2];
          const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
          const plungeAccel = 100 / (r + 0.1);
          gp.velocity[0] += -dx / r * plungeAccel * dt;
          gp.velocity[1] += -dy / r * plungeAccel * dt;
          gp.velocity[2] += -dz / r * plungeAccel * dt;

          if (r < bh.rs * 0.5) {
            gp.accreted = true;
            accretedThisStep += gp.mass;
          }
        }
      }
    }

    this._accretedMass += accretedThisStep;
    this._accretionWindow.push({ time: this.simTime, mass: accretedThisStep });
    while (this._accretionWindow.length > 100) this._accretionWindow.shift();
    if (this._accretionWindow.length > 0) {
      const windowMass = this._accretionWindow.reduce((s, e) => s + e.mass, 0);
      const windowTime = this._accretionWindow.length * dt * this._speedMultiplier;
      this.accretionRate = windowTime > 0 ? windowMass / windowTime : 0;
    }
  }

  _classifyBoundParticles() {
    const blackHoles = this._blackHoles;
    if (blackHoles.length === 0) return;
    const bh = blackHoles[0];

    for (const p of this.matterParticles) {
      if (!p.isActive) continue;

      const dx = p.position[0] - bh.position[0];
      const dy = p.position[1] - bh.position[1];
      const dz = p.position[2] - bh.position[2];
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const v2 = p.velocity[0] ** 2 + p.velocity[1] ** 2 + p.velocity[2] ** 2;

      const rs = bh.rs;
      const rMinusRs = Math.max(r - rs, rs * 0.1);
      const specificOrbitalEnergy = 0.5 * v2 - Constants.G_solar_km * bh.mass / rMinusRs;

      const Lx = dy * p.velocity[2] - dz * p.velocity[1];
      const Ly = dz * p.velocity[0] - dx * p.velocity[2];
      const Lz = dx * p.velocity[1] - dy * p.velocity[0];
      const specificAngularMomentum = Math.sqrt(Lx * Lx + Ly * Ly + Lz * Lz);
      const vCirc = Math.sqrt(Constants.G_solar_km * bh.mass / Math.max(r, 1));

      p._specificOrbitalEnergy = specificOrbitalEnergy;
      p._specificAngularMomentum = specificAngularMomentum;
      p._vCirc = vCirc;

      if (p.phase === 'debris' || p.phase === 'disk') {
        if (specificOrbitalEnergy > 0 && r > rs * 100) {
          p.escaped = true;
        }
      }
    }
  }

  _updatePhaseTransitions(dt) {
    const blackHoles = this._blackHoles;
    if (blackHoles.length === 0) return;
    const bh = blackHoles[0];

    for (const p of this.matterParticles) {
      if (!p.isActive) continue;
      if (p.phase !== 'debris') continue;

      const dx = p.position[0] - bh.position[0];
      const dy = p.position[1] - bh.position[1];
      const dz = p.position[2] - bh.position[2];
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (r < bh.rs * 10) continue;

      const vCirc = Math.sqrt(Constants.G_solar_km * bh.mass / r);
      const vPhi = Math.abs(
        (dx * p.velocity[2] - dz * p.velocity[0]) / (r + 1e-15)
      );
      const circularity = vPhi / (vCirc + 1e-15);
      const hasShockHeating = p._shockHeating > 0;

      if ((circularity > 0.7 || hasShockHeating) && p.density > 1e-15) {
        p.phase = 'disk';
      }
    }
  }

  _captureParticlesAtISCO(dt) {
    const blackHoles = this._blackHoles;
    if (blackHoles.length === 0) return;
    const bh = blackHoles[0];
    let capturedThisStep = 0;

    for (const p of this.matterParticles) {
      if (!p.isActive) continue;
      if (!bh.isInsideISCO(p.position)) continue;

      const dx = p.position[0] - bh.position[0];
      const dy = p.position[1] - bh.position[1];
      const dz = p.position[2] - bh.position[2];
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);

      const pMomentum = [
        p.mass * p.velocity[0],
        p.mass * p.velocity[1],
        p.mass * p.velocity[2],
      ];
      const pEnergy = 0.5 * p.mass * (
        p.velocity[0] ** 2 + p.velocity[1] ** 2 + p.velocity[2] ** 2
      ) + p.mass * p.internalEnergy;

      p.captured = true;
      p.accretionTime = this.simTime;

      capturedThisStep += p.mass;
      this._ledger.recordAccretion(p.mass, pMomentum, pEnergy);

      const pe = -Constants.G_solar_km * bh.mass * p.mass / Math.max(r, bh.rs);
      this._accretedMass += p.mass;
      this._bhAccretionEnergy = (this._bhAccretionEnergy || 0) + pEnergy + pe;
    }

    this._accretionWindow.push({ time: this.simTime, mass: capturedThisStep });
    while (this._accretionWindow.length > 100) this._accretionWindow.shift();
    if (this._accretionWindow.length > 0) {
      const windowMass = this._accretionWindow.reduce((s, e) => s + e.mass, 0);
      const windowTime = this._accretionWindow.length * dt;
      this.accretionRate = windowTime > 0 ? windowMass / windowTime : 0;
    }
  }

  _handleTidalDisruption(dt) {
    const blackHoles = this._blackHoles;
    if (blackHoles.length === 0) return;
    const bh = blackHoles[0];
    const bhPos = bh.position;
    const bhMass = bh.mass;

    const stellarParticles = this.matterParticles.filter(p => p.isActive && p.phase === 'stellar');
    if (stellarParticles.length === 0) return;

    const stars = this.bodies.filter(b => b.type === 'star' && !b.disrupted);
    if (stars.length === 0) return;

    const star = stars[0];
    const R_star_km = star.starRadius * Constants.R_sun_km;

    const cx = stellarParticles.reduce((s, p) => s + p.position[0], 0) / stellarParticles.length;
    const cy = stellarParticles.reduce((s, p) => s + p.position[1], 0) / stellarParticles.length;
    const cz = stellarParticles.reduce((s, p) => s + p.position[2], 0) / stellarParticles.length;

    let maxSpread = 0;
    for (const p of stellarParticles) {
      const dx = p.position[0] - cx;
      const dy = p.position[1] - cy;
      const dz = p.position[2] - cz;
      const spread = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (spread > maxSpread) maxSpread = spread;
    }

    star.computeDeformation(bh);

    const dR = Constants.tidalDisruptionRadius(bhMass, star.starRadius, star.mass);
    const dCenter = Math.sqrt(
      (cx - bhPos[0]) ** 2 + (cy - bhPos[1]) ** 2 + (cz - bhPos[2]) ** 2
    );

    const tidalOverSelfGravity = (2 * Constants.G_solar_km * bhMass * R_star_km) /
      (Math.pow(dCenter + 0.1, 3) * Constants.G_solar_km * stellarParticles.reduce((s, p) => s + p.mass, 0) /
      (R_star_km * R_star_km + 0.01));

    const disrupted = maxSpread > R_star_km * 2 || (dCenter < dR * 1.5 && tidalOverSelfGravity > 0.5);

    if (!star.disrupted && disrupted) {
      star.disrupted = true;
      star.disruptionTime = this.simTime;
      this._fallbackMass = stellarParticles.reduce((s, p) => s + p.mass, 0);

      for (const p of stellarParticles) {
        p.phase = 'debris';
      }
    }
  }

  _computeGravitationalWaves(subDt) {
    const bodies = this.bodies.filter(b => !b.fixed && !b.disrupted);
    let maxFreq = 0;
    let maxStrain = 0;
    let totalLuminosity = 0;

    for (let i = 0; i < bodies.length; i++) {
      for (let j = i + 1; j < bodies.length; j++) {
        const bi = bodies[i];
        const bj = bodies[j];
        if (bi.mass < 1 || bj.mass < 1) continue;

        const dx = bj.position[0] - bi.position[0];
        const dy = bj.position[1] - bi.position[1];
        const dz = bj.position[2] - bi.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (r < 0.001) continue;

        const metrics = this._computeBinaryGWMetrics(bi, bj, r);

        if (metrics.frequency > maxFreq) maxFreq = metrics.frequency;
        if (metrics.strain > maxStrain) maxStrain = metrics.strain;
        totalLuminosity += metrics.luminosity;

        if (bi.type === 'blackhole' && bj.type === 'blackhole') {
          this._applyGWOrbitalDecay(bi, bj, subDt);
          if (this._shouldMergeBlackHoles(bi, bj)) {
            this._mergeBlackHoles(bi, bj, metrics.frequency, metrics.strain);
          }
        }
      }
    }

    let outputFreq = maxFreq;
    let outputStrain = maxStrain;
    this.gwLuminosity = totalLuminosity;

    if (this._mergedBH) {
      const elapsed = Math.max(0, this.simTime - this._mergedBH.mergeTime);
      const ringdownStrain = this._mergedBH.peakStrain * Math.exp(-elapsed / this._mergedBH.dampingTime);
      if (ringdownStrain > outputStrain) {
        outputFreq = this._mergedBH.ringdownFrequency;
        outputStrain = ringdownStrain;
      }
    }

    this.gwFrequency = outputFreq;
    this.gwStrain = outputStrain;
    this.gwPhase += outputFreq * subDt;
  }

  _computeBHPairs() {
    const bhs = this.bodies.filter(b => b.type === 'blackhole');
    this._bhPairs = [];
    for (let i = 0; i < bhs.length; i++) {
      for (let j = i + 1; j < bhs.length; j++) {
        const dx = bhs[j].position[0] - bhs[i].position[0];
        const dy = bhs[j].position[1] - bhs[i].position[1];
        const dz = bhs[j].position[2] - bhs[i].position[2];
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
        this._bhPairs.push({ a: i, b: j, distance });
      }
    }
  }

  _updateParticleTrails() {
    for (const gp of this.gasParticles) {
      if (gp.accreted) continue;
      if (!this._particleTrails.has(gp.id)) {
        this._particleTrails.set(gp.id, []);
      }
      const trail = this._particleTrails.get(gp.id);
      trail.push([...gp.position]);
      if (trail.length > this._trailMaxLength) {
        trail.shift();
      }
    }
    for (const mp of this.matterParticles) {
      if (mp.captured || !mp.isActive) continue;
      if (!this._particleTrails.has(mp.id)) {
        this._particleTrails.set(mp.id, []);
      }
      const trail = this._particleTrails.get(mp.id);
      trail.push([...mp.position]);
      if (trail.length > this._trailMaxLength) {
        trail.shift();
      }
    }
  }

  _saveSnapshot() {
    const snapshot = {
      time: this.simTime,
      bodies: this.bodies.map(b => ({
        id: b.id,
        position: [...b.position],
        velocity: [...b.velocity],
        mass: b.mass,
        disrupted: b.disrupted
      })),
      gas: this.gasParticles.map(g => ({
        position: [...g.position],
        velocity: [...g.velocity],
        mass: g.mass,
        temperature: g.temperature
      })),
      gw: {
        frequency: this.gwFrequency,
        strain: this.gwStrain,
        phase: this.gwPhase,
        luminosity: this.gwLuminosity
      },
      accretionRate: this.accretionRate,
      fallbackRate: this._fallbackRate,
      fallbackStartTime: this._fallbackStartTime,
      fallbackMass: this._fallbackMass,
      gwRippleFadeStrain: this._gwRippleFadeStrain,
      gwRippleFadeTime: this._gwRippleFadeTime
    };
    this._snapshots.push(snapshot);
    if (this._snapshots.length > Constants.maxSnapshots) {
      this._snapshots.shift();
    }
  }

  getSnapshotAt(targetTime) {
    let best = this._snapshots[0];
    for (const s of this._snapshots) {
      if (s.time <= targetTime) best = s;
    }
    return best;
  }

  scrubTo(targetTime) {
    const snapshot = this.getSnapshotAt(targetTime);
    if (!snapshot) return;

    for (const bd of snapshot.bodies) {
      const body = this.bodies.find(b => b.id === bd.id);
      if (body) {
        body.position = [...bd.position];
        body.velocity = [...bd.velocity];
        body.disrupted = bd.disrupted;
      }
    }

    if (snapshot.gas) {
      this.gasParticles = snapshot.gas.map(g => ({
        position: [...g.position],
        velocity: [...g.velocity],
        mass: g.mass,
        temperature: g.temperature,
        accreted: false
      }));
    }

    if (snapshot.gw) {
      this.gwFrequency = snapshot.gw.frequency;
      this.gwStrain = snapshot.gw.strain;
      this.gwPhase = snapshot.gw.phase;
      this.gwLuminosity = snapshot.gw.luminosity;
    }

    if (snapshot.accretionRate !== undefined) this.accretionRate = snapshot.accretionRate;
    if (snapshot.fallbackRate !== undefined) this._fallbackRate = snapshot.fallbackRate;
    if (snapshot.fallbackStartTime !== undefined) this._fallbackStartTime = snapshot.fallbackStartTime;
    if (snapshot.fallbackMass !== undefined) this._fallbackMass = snapshot.fallbackMass;
    if (snapshot.gwRippleFadeStrain !== undefined) this._gwRippleFadeStrain = snapshot.gwRippleFadeStrain;
    if (snapshot.gwRippleFadeTime !== undefined) this._gwRippleFadeTime = snapshot.gwRippleFadeTime;

    let dt = targetTime - snapshot.time;
    const steps = Math.min(Constants.maxRecomputeSteps, Math.ceil(Math.abs(dt) / Constants.dt_max));
    const subDt = dt / steps;
    this._blackHoles = this.bodies.filter(b => b.type === 'blackhole');
    for (let i = 0; i < steps; i++) {
      this._integrateGravity(subDt);
      this._integrateGas(subDt);
    }
    this.simTime = targetTime;
  }

  getState() {
    return {
      bodies: this.bodies.map(b => ({
        id: b.id,
        position: [...b.position],
        velocity: [...b.velocity],
        mass: b.mass,
        type: b.type,
        fixed: b.fixed,
        disrupted: b.disrupted,
        name: b.name,
        color: b.color,
        radius: b.renderRadius ?? b.radius,
        rs: b.rs || 0,
        spin: b.spin || 0,
        trail: b.trail || [],
        selected: b.selected || false
      })),
      gasParticles: this.gasParticles.filter(g => !g.accreted).map(g => ({
        position: [...g.position],
        velocity: [...g.velocity],
        temperature: g.temperature,
        size: g.size,
        type: 'gas'
      })),
      matterParticles: this.matterParticles.filter(p => p.isActive).map(p => ({
        id: p.id,
        position: [...p.position],
        velocity: [...p.velocity],
        mass: p.mass,
        density: p.density,
        pressure: p.pressure,
        internalEnergy: p.internalEnergy,
        temperature: p.temperature,
        phase: p.phase,
        lifecycle: p.lifecycle,
        smoothingLength: p.smoothingLength,
        type: 'matter'
      })),
      gw: {
        frequency: this.gwFrequency,
        strain: this.gwStrain,
        phase: this.gwPhase,
        luminosity: this.gwLuminosity
      },
      accretionRate: this.accretionRate,
      fallbackRate: this._fallbackRate,
      fallbackMass: this._fallbackMass,
      bhAccretionEnergy: this._bhAccretionEnergy,
      simTime: this.simTime,
      bhPairs: this._bhPairs,
      particleTrails: Object.fromEntries(this._particleTrails),
      ledgers: this.getMatterDiagnostics()
    };
  }

  addMatterParticles(particles) {
    for (const p of particles) {
      p.saveInitialState();
      this.matterParticles.push(p);
    }
  }

  _computeSmoothingLength() {
    const active = this.matterParticles.filter(p => p.isActive);
    if (active.length === 0) {
      this._smoothingLength = 1;
      return;
    }
    const R = Math.max(...active.map(p => {
      const dx = p.position[0], dy = p.position[1], dz = p.position[2];
      return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }));
    const volume = (4 / 3) * Math.PI * Math.pow(R + 1, 3);
    this._smoothingLength = Constants.sphEtaSmooth * Math.pow(volume / active.length, 1 / 3);
  }

  _integrateMatterGravity(dt) {
    const active = this.matterParticles.filter(p => p.isActive);
    const n = active.length;
    if (n === 0) return;

    const allGravitating = this.bodies;
    const useBarnesHut = allGravitating.length + n > Constants.barnesHutThreshold;

    if (useBarnesHut) {
      this._barnesHut.build(allGravitating, active);
    }

    const acc = new Array(n);
    for (let i = 0; i < n; i++) acc[i] = [0, 0, 0];

    for (let i = 0; i < n; i++) {
      const p = active[i];
      if (useBarnesHut) {
        const accBH = this._barnesHut.computeAcceleration(p);
        acc[i][0] = accBH[0];
        acc[i][1] = accBH[1];
        acc[i][2] = accBH[2];
      } else {
        let ax = 0, ay = 0, az = 0;
        for (const bh of allGravitating) {
          const dx = bh.position[0] - p.position[0];
          const dy = bh.position[1] - p.position[1];
          const dz = bh.position[2] - p.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * bh.mass / (r2 * r);
          ax += f * dx;
          ay += f * dy;
          az += f * dz;
        }
        for (const pj of active) {
          if (pj.id === p.id) continue;
          const dx = pj.position[0] - p.position[0];
          const dy = pj.position[1] - p.position[1];
          const dz = pj.position[2] - p.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * pj.mass / (r2 * r);
          ax += f * dx;
          ay += f * dy;
          az += f * dz;
        }
        acc[i][0] = ax;
        acc[i][1] = ay;
        acc[i][2] = az;
      }
    }

    for (let i = 0; i < n; i++) {
      const p = active[i];
      p.position[0] += p.velocity[0] * dt + 0.5 * acc[i][0] * dt * dt;
      p.position[1] += p.velocity[1] * dt + 0.5 * acc[i][1] * dt * dt;
      p.position[2] += p.velocity[2] * dt + 0.5 * acc[i][2] * dt * dt;
    }

    const newAcc = new Array(n);
    for (let i = 0; i < n; i++) newAcc[i] = [0, 0, 0];

    if (useBarnesHut) {
      this._barnesHut.build(allGravitating, active);
    }

    for (let i = 0; i < n; i++) {
      const p = active[i];
      if (useBarnesHut) {
        const accBH = this._barnesHut.computeAcceleration(p);
        newAcc[i][0] = accBH[0];
        newAcc[i][1] = accBH[1];
        newAcc[i][2] = accBH[2];
      } else {
        let ax = 0, ay = 0, az = 0;
        for (const bh of allGravitating) {
          const dx = bh.position[0] - p.position[0];
          const dy = bh.position[1] - p.position[1];
          const dz = bh.position[2] - p.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * bh.mass / (r2 * r);
          ax += f * dx;
          ay += f * dy;
          az += f * dz;
        }
        for (const pj of active) {
          if (pj.id === p.id) continue;
          const dx = pj.position[0] - p.position[0];
          const dy = pj.position[1] - p.position[1];
          const dz = pj.position[2] - p.position[2];
          const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
          const r = Math.sqrt(r2);
          const f = Constants.G_solar_km * pj.mass / (r2 * r);
          ax += f * dx;
          ay += f * dy;
          az += f * dz;
        }
        newAcc[i][0] = ax;
        newAcc[i][1] = ay;
        newAcc[i][2] = az;
      }
    }

    for (let i = 0; i < n; i++) {
      const p = active[i];
      p.velocity[0] += 0.5 * (acc[i][0] + newAcc[i][0]) * dt;
      p.velocity[1] += 0.5 * (acc[i][1] + newAcc[i][1]) * dt;
      p.velocity[2] += 0.5 * (acc[i][2] + newAcc[i][2]) * dt;
    }
  }

  _integrateMatterSPH(dt) {
    const active = this.matterParticles.filter(p => p.isActive);
    if (active.length === 0) return;

    this._computeSmoothingLength();
    const h = this._smoothingLength;

    this._sphSolver.computeDensity(active, h);
    this._sphSolver.computePressure(active);
    this._sphSolver.computeHydroForces(active, dt, h);

    for (const p of active) {
      const acc = p._sphAcceleration || [0, 0, 0];
      p.velocity[0] += 0.5 * acc[0] * dt;
      p.velocity[1] += 0.5 * acc[1] * dt;
      p.velocity[2] += 0.5 * acc[2] * dt;
    }

    this._sphSolver.integrateInternalEnergy(active, dt, this._coolingBeta);

    for (const p of active) {
      if (p._shockHeating) {
        this._ledger.recordShockHeating(p.mass * p._shockHeating);
        p._shockHeating = 0;
      }
      if (p._coolingRate) {
        this._ledger.recordCooling(-p.mass * p._coolingRate * dt);
        p._coolingRate = 0;
      }
      p._sphAcceleration = null;
      p._duDtHydro = 0;
    }
  }

  _computeMatterTimestep() {
    const active = this.matterParticles.filter(p => p.isActive);
    if (active.length === 0) return Infinity;

    const h = this._smoothingLength > 0
      ? this._smoothingLength
      : Math.max(...active.map(p => {
          const dx = p.position[0], dy = p.position[1], dz = p.position[2];
          return Math.sqrt(dx * dx + dy * dy + dz * dz);
        })) || 1;

    let dtMin = Infinity;

    for (const p of active) {
      const cs = Math.sqrt(Constants.sphGamma * p.pressure / Math.max(p.density, Constants.sphDensityFloor));
      const vSig = Math.max(cs, 1e-15);
      const dtSph = Constants.dt_factor * h / vSig;
      if (dtSph < dtMin) dtMin = dtSph;

      for (const bh of this._blackHoles) {
        const dx = p.position[0] - bh.position[0];
        const dy = p.position[1] - bh.position[1];
        const dz = p.position[2] - bh.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (r < bh.rs * 10) {
          const vRel = Math.sqrt(
            (p.velocity[0] - bh.velocity[0]) ** 2 +
            (p.velocity[1] - bh.velocity[1]) ** 2 +
            (p.velocity[2] - bh.velocity[2]) ** 2
          );
          const dtEnc = Constants.dt_factor * r / (vRel + 1e-15);
          if (dtEnc < dtMin) dtMin = dtEnc;
        }
      }
    }

    return dtMin;
  }

  getMatterDiagnostics() {
    this._ledger.compute(this.matterParticles, this.bodies, Constants.G_solar_km);
    return this._ledger.getDiagnostics();
  }

  getTotalEnergy() {
    let kinetic = 0;
    let potential = 0;
    const n = this.bodies.length;
    for (let i = 0; i < n; i++) {
      const bi = this.bodies[i];
      const v2 = bi.velocity[0] ** 2 + bi.velocity[1] ** 2 + bi.velocity[2] ** 2;
      kinetic += 0.5 * bi.mass * v2;
      for (let j = i + 1; j < n; j++) {
        const bj = this.bodies[j];
        const dx = bj.position[0] - bi.position[0];
        const dy = bj.position[1] - bi.position[1];
        const dz = bj.position[2] - bi.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening);
        potential -= Constants.G_solar_km * bi.mass * bj.mass / r;
      }
    }
    return kinetic + potential;
  }

  getSnapshots() { return this._snapshots; }
}
