let gasId = 1;

export class GasParticle {
  constructor(options = {}) {
    this.id = gasId++;
    this.position = options.position || [0, 0, 0];
    this.velocity = options.velocity || [0, 0, 0];
    this.mass = options.mass || 1e-6;
    this.temperature = options.temperature || 1000;
    this.renderSize = options.renderSize;
    this.accreted = false;
    this.age = 0;
    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass
    };
  }

  get size() {
    if (this.renderSize !== undefined) return this.renderSize;
    return Math.max(0.5, Math.min(3.0, this.temperature / 5000));
  }

  get type() { return 'gas'; }

  reset() {
    this.position = [...this._initialState.position];
    this.velocity = [...this._initialState.velocity];
    this.mass = this._initialState.mass;
    this.accreted = false;
    this.age = 0;
  }

  saveInitialState() {
    this._initialState = {
      position: [...this.position],
      velocity: [...this.velocity],
      mass: this.mass
    };
  }
}
