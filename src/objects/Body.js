import { Constants } from '../core/Constants.js';

let nextId = 1;

export class Body {
  constructor(options = {}) {
    this.id = nextId++;
    this.position = options.position || [0, 0, 0];
    this.velocity = options.velocity || [0, 0, 0];
    this.mass = options.mass || 0;
    this.type = options.type || 'star';
    this.name = options.name || `${this.type}_${this.id}`;
    this.fixed = options.fixed || false;
    this.disrupted = false;
    this.disruptionTime = -1;
    this.disruptionParticles = [];
    this.trail = [];
    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass,
      fixed: this.fixed,
      disrupted: false
    };
  }

  get rs() { return 0; }

  reset() {
    this.position = [...this._initialState.position];
    this.velocity = [...this._initialState.velocity];
    this.mass = this._initialState.mass;
    this.fixed = this._initialState.fixed;
    this.disrupted = this._initialState.disrupted;
    this.disruptionParticles = [];
    this.trail = [];
  }

  saveInitialState() {
    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass,
      fixed: this.fixed,
      disrupted: this.disrupted
    };
  }

  updateTrail() {
    this.trail.push([...this.position]);
    if (this.trail.length > Constants.trailMaxPoints) {
      this.trail.shift();
    }
  }

  get color() {
    return [1, 1, 1];
  }

  get radius() {
    return 1.0;
  }

  get kineticEnergy() {
    const v2 = this.velocity[0] ** 2 + this.velocity[1] ** 2 + this.velocity[2] ** 2;
    return 0.5 * this.mass * v2;
  }

  distanceTo(other) {
    const dx = this.position[0] - other.position[0];
    const dy = this.position[1] - other.position[1];
    const dz = this.position[2] - other.position[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  }
}
