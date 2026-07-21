export class ConservationLedger {
  constructor() {
    this.reset();
  }

  reset() {
    this.totalMassInitial = 0;
    this.totalMassCurrent = 0;
    this.accretedMass = 0;
    this.escapedMass = 0;

    this.totalMomentum = [0, 0, 0];
    this.totalAngularMomentum = [0, 0, 0];

    this.kineticEnergy = 0;
    this.thermalEnergy = 0;
    this.potentialEnergy = 0;
    this.totalEnergy = 0;

    this.initialEnergy = 0;

    this.shockEnergy = 0;
    this.coolingEnergy = 0;
    this.accretedEnergy = 0;

    this.particleCount = 0;
    this.activeCount = 0;
    this.aliveCount = 0;
    this.capturedCount = 0;
    this.escapedCount = 0;
  }

  compute(matterParticles, bodies, G) {
    this.particleCount = matterParticles.length;
    this.activeCount = matterParticles.filter(p => p.isActive).length;
    this.aliveCount = matterParticles.filter(p => p.isAlive).length;
    this.capturedCount = matterParticles.filter(p => p.captured).length;
    this.escapedCount = matterParticles.filter(p => p.escaped).length;

    let totalMass = 0;
    let momentum = [0, 0, 0];
    let angMom = [0, 0, 0];
    let ke = 0;
    let te = 0;
    let pe = 0;

    for (const p of matterParticles) {
      if (!p.isActive) continue;
      totalMass += p.mass;
      momentum[0] += p.mass * p.velocity[0];
      momentum[1] += p.mass * p.velocity[1];
      momentum[2] += p.mass * p.velocity[2];

      angMom[0] += p.mass * (p.position[1] * p.velocity[2] - p.position[2] * p.velocity[1]);
      angMom[1] += p.mass * (p.position[2] * p.velocity[0] - p.position[0] * p.velocity[2]);
      angMom[2] += p.mass * (p.position[0] * p.velocity[1] - p.position[1] * p.velocity[0]);

      ke += p.kineticEnergy;
      te += p.thermalEnergy;
    }

    for (let i = 0; i < matterParticles.length; i++) {
      if (!matterParticles[i].isActive) continue;
      for (let j = i + 1; j < matterParticles.length; j++) {
        if (!matterParticles[j].isActive) continue;
        const dx = matterParticles[j].position[0] - matterParticles[i].position[0];
        const dy = matterParticles[j].position[1] - matterParticles[i].position[1];
        const dz = matterParticles[j].position[2] - matterParticles[i].position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz + 0.01 * 0.01);
        pe -= G * matterParticles[i].mass * matterParticles[j].mass / r;
      }
    }

    for (const body of bodies) {
      if (body.fixed) continue;
      ke += 0.5 * body.mass * (body.velocity[0] ** 2 + body.velocity[1] ** 2 + body.velocity[2] ** 2);

      for (const p of matterParticles) {
        if (!p.isActive) continue;
        const dx = body.position[0] - p.position[0];
        const dy = body.position[1] - p.position[1];
        const dz = body.position[2] - p.position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz + 0.01 * 0.01);
        pe -= G * body.mass * p.mass / r;
      }
    }

    for (let i = 0; i < bodies.length; i++) {
      for (let j = i + 1; j < bodies.length; j++) {
        const dx = bodies[j].position[0] - bodies[i].position[0];
        const dy = bodies[j].position[1] - bodies[i].position[1];
        const dz = bodies[j].position[2] - bodies[i].position[2];
        const r = Math.sqrt(dx * dx + dy * dy + dz * dz + 0.01 * 0.01);
        pe -= G * bodies[i].mass * bodies[j].mass / r;
      }
    }

    this.totalMassCurrent = totalMass;
    this.totalMomentum = momentum;
    this.totalAngularMomentum = angMom;
    this.kineticEnergy = ke;
    this.thermalEnergy = te;
    this.potentialEnergy = pe;
    this.totalEnergy = ke + te + pe;
  }

  recordAccretion(mass, momentum, energy) {
    this.accretedMass += mass;
    this.accretedEnergy += energy;
  }

  recordEscape(mass) {
    this.escapedMass += mass;
  }

  recordShockHeating(energy) {
    this.shockEnergy += energy;
  }

  recordCooling(energy) {
    this.coolingEnergy += energy;
  }

  getDiagnostics() {
    const energyImbalance = this.initialEnergy > 0
      ? (this.totalEnergy - this.initialEnergy + this.coolingEnergy) / this.initialEnergy
      : 0;

    return {
      mass: {
        current: this.totalMassCurrent,
        accreted: this.accretedMass,
        escaped: this.escapedMass,
        accounted: this.totalMassCurrent + this.accretedMass + this.escapedMass,
      },
      energy: {
        kinetic: this.kineticEnergy,
        thermal: this.thermalEnergy,
        potential: this.potentialEnergy,
        total: this.totalEnergy,
        shock: this.shockEnergy,
        cooling: this.coolingEnergy,
        accreted: this.accretedEnergy,
        imbalance: energyImbalance,
      },
      counts: {
        total: this.particleCount,
        active: this.activeCount,
        alive: this.aliveCount,
        captured: this.capturedCount,
        escaped: this.escapedCount,
      },
    };
  }
}
