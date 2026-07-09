import { Constants } from '../core/Constants.js';
import { Body } from '../objects/Body.js';
import { BlackHole } from '../objects/BlackHole.js';
import { Star } from '../objects/Star.js';
import { GasParticle } from '../objects/GasParticle.js';
import { BarnesHut } from './BarnesHut.js';

export class PhysicsEngine {
  constructor() {
    this.bodies = [];
    this.gasParticles = [];
    this.jetParticles = [];
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
    this.jetParticles = [];
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
  }

  loadPreset(presetData) {
    this.reset();
    this.bodies = [];
    this.gasParticles = [];
    this.jetParticles = [];
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
  }

  step(dt) {
    if (!this._playing) return;
    const effectiveDt = dt * this._speedMultiplier;
    const substeps = Math.max(1, Math.ceil(effectiveDt / Constants.dt_max));
    const subDt = effectiveDt / substeps;
    this._blackHoles = this.bodies.filter(b => b.type === 'blackhole');

    for (let s = 0; s < substeps; s++) {
      this._integrateGravity(subDt);
      this._integrateGas(subDt);
      this._computeAccretion(subDt);
      this._computeGravitationalWaves(subDt);
      this._handleTidalDisruption();
      this._computeFallbackRate();
      this._updateJets(subDt);
      for (const body of this.bodies) {
        if (!body.fixed && !body.disrupted) {
          body.updateTrail();
        }
      }
      this.simTime += subDt;
      this._snapshotCounter++;
      if (this._snapshotCounter >= Constants.snapshotInterval) {
        this._saveSnapshot();
        this._snapshotCounter = 0;
      }
    }
  }

  _computeFallbackRate() {
    if (this._fallbackStartTime < 0) return;
    
    const t = this.simTime - this._fallbackStartTime;
    if (t <= 0) {
      this._fallbackRate = 0;
      return;
    }
    
    const T_fallback = 10.0;
    const tRatio = t / T_fallback;
    this._fallbackRate = this._fallbackMass * Math.pow(tRatio, -5/3) * 0.001;
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
          const f = Constants.G * bj.mass / (r2 * r);
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
          const f = Constants.G * bj.mass / (r2 * r);
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
        const f = Constants.G * bh.mass / (r2 * r);
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
        const f = Constants.G * bh.mass / (r2 * r);
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

    this._applyViscousTransport(dt);
    this.gasParticles = this.gasParticles.filter(gp => !gp.accreted);
  }

  _applyViscousTransport(dt) {
    for (let i = 0; i < this.gasParticles.length; i++) {
      const gp = this.gasParticles[i];
      if (gp.accreted) continue;
      const blackHoles = this._blackHoles;
      for (const bh of blackHoles) {
        const dx = gp.position[0] - bh.position[0];
        const dy = gp.position[1] - bh.position[1];
        const dz = gp.position[2] - bh.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (r < 0.001) continue;

        const orbitalPeriod = Constants.orbitalPeriod(bh.mass, r);
        const H = r * Constants.gasDiskThickness;
        const viscousTimescale = orbitalPeriod * (r / H) * (r / H);
        const viscousAccel = Constants.alpha_visc * r / (viscousTimescale * viscousTimescale + 1);
        const rVec = [dx / r, dy / r, dz / r];
        const tangential = [-rVec[1], rVec[0], 0];
        const tLen = Math.sqrt(tangential[0] ** 2 + tangential[1] ** 2 + tangential[2] ** 2);
        if (tLen > 0.001) {
          tangential[0] /= tLen;
          tangential[1] /= tLen;
          tangential[2] /= tLen;
        }
        const inward = [-rVec[0], -rVec[1], -rVec[2]];
        const transport = 0.001 * viscousAccel * dt;
        gp.velocity[0] += tangential[0] * transport + inward[0] * transport * 0.01;
        gp.velocity[1] += tangential[1] * transport + inward[1] * transport * 0.01;
        gp.velocity[2] += tangential[2] * transport + inward[2] * transport * 0.01;
      }
    }
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
            this._emitJetParticles(bh, gp);
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

  _emitJetParticles(bh, gasParticle) {
    if (bh.spin === 0) return;
    const jetProb = bh.spin * bh.spin;
    if (Math.random() > jetProb) return;

    const count = Math.min(2, Math.floor(jetProb * 3) + 1);
    for (let i = 0; i < count; i++) {
      if (this.jetParticles.length >= Constants.jetMaxParticles) {
        this.jetParticles.shift();
      }
      const spinAxis = bh.spinAxis;
      const speed = Constants.c * 0.95 * (0.9 + Math.random() * 0.09);
      const scaledSpeed = speed * 1e-6;
      const wobble = bh.spin * 0.1;
      const axis = [
        spinAxis[0] + (Math.random() - 0.5) * wobble,
        spinAxis[1] + (Math.random() - 0.5) * wobble,
        spinAxis[2] + (Math.random() - 0.5) * wobble
      ];
      const sign = Math.random() > 0.5 ? 1 : -1;

      this.jetParticles.push({
        position: [...bh.position],
        velocity: [axis[0] * scaledSpeed * sign, axis[1] * scaledSpeed * sign, axis[2] * scaledSpeed * sign],
        type: 'jet',
        age: 0,
        birthTime: this.simTime
      });
    }
  }

  _updateJets(dt) {
    for (const jp of this.jetParticles) {
      jp.position[0] += jp.velocity[0] * dt;
      jp.position[1] += jp.velocity[1] * dt;
      jp.position[2] += jp.velocity[2] * dt;
      jp.age += dt;
    }

    const blackHoles = this._blackHoles;
    this.jetParticles = this.jetParticles.filter(jp => {
      for (const bh of blackHoles) {
        const dx = jp.position[0] - bh.position[0];
        const dy = jp.position[1] - bh.position[1];
        const dz = jp.position[2] - bh.position[2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist > bh.rs * Constants.jetMaxDistance) return false;
      }
      return true;
    });
  }

  _handleTidalDisruption() {
    const blackHoles = this._blackHoles;
    const stars = this.bodies.filter(b => b.type === 'star' && !b.disrupted);

    for (const star of stars) {
      for (const bh of blackHoles) {
        const dx = star.position[0] - bh.position[0];
        const dy = star.position[1] - bh.position[1];
        const dz = star.position[2] - bh.position[2];
        const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const dR = Constants.tidalDisruptionRadius(bh.mass, star.starRadius, star.mass);

        star.computeDeformation(bh);

        if (d < dR) {
          star.disrupted = true;
          star.disruptionTime = this.simTime;
          const particles = star.generateDisruptionParticles();
          star.disruptionParticles = particles;
          
          if (this._fallbackStartTime < 0) {
            this._fallbackStartTime = this.simTime;
            this._fallbackMass = star.mass;
          }
          
          for (const p of particles) {
            const captureProb = 0.3;
            if (Math.random() < captureProb) {
              this.addGasParticle(new GasParticle({
                position: p.position,
                velocity: p.velocity,
                mass: p.mass * 0.8
              }));
            } else {
              this.bodies.push(new Body({
                position: p.position,
                velocity: p.velocity,
                mass: p.mass * 0.2,
                type: 'debris',
                name: `debris_${star.name}_${Math.floor(Math.random() * 1000)}`
              }));
            }
          }
        }
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

        const M = bi.mass + bj.mass;
        const fOrb = Math.sqrt(Constants.G * M * Constants.M_sun) / (2 * Math.PI * Math.pow(r, 1.5));
        const fGW = 2 * fOrb;
        const Mc = Constants.chirpMass(bi.mass, bj.mass);
        const McKg = Mc * Constants.M_sun;
        const MKg = M * Constants.M_sun;
        const strain = (4 / r) * Math.pow(Constants.G * McKg / (Constants.c * Constants.c), 5 / 3) *
          Math.pow(Math.PI * fGW / Constants.c, 2 / 3);

        const luminosity = (32 / 5) * Math.pow(Constants.G, 7 / 3) *
          Math.pow(Mc, 10 / 3) * Math.pow(Math.PI * fGW, 10 / 3) / Math.pow(Constants.c, 5);

        if (!bi.fixed) {
          const v2_bi = bi.velocity[0] ** 2 + bi.velocity[1] ** 2 + bi.velocity[2] ** 2;
          const v_bi = Math.sqrt(v2_bi);
          if (v_bi > 0.001) {
            const dvDt = luminosity / (MKg * v_bi);
            bi.velocity[0] += (dx / r) * dvDt * subDt;
            bi.velocity[1] += (dy / r) * dvDt * subDt;
            bi.velocity[2] += (dz / r) * dvDt * subDt;
          }
        }

        if (!bj.fixed) {
          const v2_bj = bj.velocity[0] ** 2 + bj.velocity[1] ** 2 + bj.velocity[2] ** 2;
          const v_bj = Math.sqrt(v2_bj);
          if (v_bj > 0.001) {
            const dvDt = luminosity / (MKg * v_bj);
            bj.velocity[0] += (-dx / r) * dvDt * subDt;
            bj.velocity[1] += (-dy / r) * dvDt * subDt;
            bj.velocity[2] += (-dz / r) * dvDt * subDt;
          }
        }

        if (fGW > maxFreq) maxFreq = fGW;
        if (strain > maxStrain) maxStrain = strain;
        totalLuminosity += luminosity;
      }
    }

    this.gwFrequency = maxFreq;
    this.gwStrain = maxStrain;
    this.gwPhase += maxFreq * subDt;
    this.gwLuminosity = totalLuminosity;

    if (this._mergedBH) {
      const tau = 0.001;
      const ringdownFreq = this._mergedBH.spin * 0.5;
      const dampingTime = tau * (1 - this._mergedBH.spin * 0.5);
      this.gwFrequency = ringdownFreq * Math.exp(-this.simTime / dampingTime);
      this.gwStrain = maxStrain * Math.exp(-this.simTime / dampingTime);
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
      jets: this.jetParticles.map(j => ({
        position: [...j.position],
        velocity: [...j.velocity],
        type: j.type,
        age: j.age,
        birthTime: j.birthTime
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
      fallbackMass: this._fallbackMass
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

    if (snapshot.jets) {
      this.jetParticles = snapshot.jets.map(j => ({
        position: [...j.position],
        velocity: [...j.velocity],
        type: j.type,
        age: j.age,
        birthTime: j.birthTime
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
        radius: b.radius,
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
      jetParticles: this.jetParticles.map(j => ({
        position: [...j.position],
        velocity: [...j.velocity],
        type: 'jet'
      })),
      gw: {
        frequency: this.gwFrequency,
        strain: this.gwStrain,
        phase: this.gwPhase,
        luminosity: this.gwLuminosity
      },
      accretionRate: this.accretionRate,
      fallbackRate: this._fallbackRate,
      simTime: this.simTime
    };
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
        potential -= Constants.G * bi.mass * bj.mass / r;
      }
    }
    return kinetic + potential;
  }

  getSnapshots() { return this._snapshots; }
}
