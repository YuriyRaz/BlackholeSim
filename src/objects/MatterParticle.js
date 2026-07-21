let nextId = 1;

export class MatterParticle {
  constructor(options = {}) {
    this.id = nextId++;
    this.position = options.position ? [...options.position] : [0, 0, 0];
    this.velocity = options.velocity ? [...options.velocity] : [0, 0, 0];
    this.mass = options.mass ?? 0;

    this.density = options.density ?? 0;
    this.pressure = options.pressure ?? 0;
    this.internalEnergy = options.internalEnergy ?? 0;
    this.temperature = options.temperature ?? 0;

    this.phase = options.phase || 'stellar';
    this.lifecycle = options.lifecycle || 'alive';

    this.smoothingLength = options.smoothingLength ?? 0;

    this.captured = false;
    this.escaped = false;
    this.accretionTime = -1;

    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass,
      phase: this.phase,
      lifecycle: this.lifecycle,
    };
  }

  get kineticEnergy() {
    const v2 = this.velocity[0] ** 2 + this.velocity[1] ** 2 + this.velocity[2] ** 2;
    return 0.5 * this.mass * v2;
  }

  get thermalEnergy() {
    return this.mass * this.internalEnergy;
  }

  get isAlive() {
    return this.lifecycle === 'alive';
  }

  get isActive() {
    return this.isAlive && !this.captured && !this.escaped;
  }

  distanceTo(other) {
    const dx = this.position[0] - other.position[0];
    const dy = this.position[1] - other.position[1];
    const dz = this.position[2] - other.position[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  }

  reset() {
    this.position = [...this._initialState.position];
    this.velocity = [...this._initialState.velocity];
    this.mass = this._initialState.mass;
    this.phase = this._initialState.phase;
    this.lifecycle = this._initialState.lifecycle;
    this.density = 0;
    this.pressure = 0;
    this.internalEnergy = 0;
    this.temperature = 0;
    this.smoothingLength = 0;
    this.captured = false;
    this.escaped = false;
    this.accretionTime = -1;
  }

  saveInitialState() {
    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass,
      phase: this.phase,
      lifecycle: this.lifecycle,
    };
  }
}
