import { Body } from './Body.js';
import { Constants } from '../core/Constants.js';

export class BlackHole extends Body {
  constructor(options = {}) {
    super({ ...options, type: 'blackhole' });
    this.spin = options.spin || 0;
    this.spinAxis = options.spinAxis || [0, 1, 0];
    this._rs = Constants.schwarzschildRadiusKm(this.mass);
    this.fixed = options.fixed !== undefined ? options.fixed : true;
  }

  get rs() { return this._rs; }
  get iscoRadius() { return Constants.iscoRadius(this.spin) * this._rs; }

  ergosphereRadius(theta) {
    return Constants.ergosphereRadius(this.spin, theta) * this._rs;
  }

  get color() {
    return [0.05, 0.05, 0.1];
  }

  get radius() {
    return Math.max(this._rs * 0.5, 2.0);
  }

  frameDraggingForce(particlePos, particleVel) {
    if (this.spin === 0) return [0, 0, 0];
    const dx = particlePos[0] - this.position[0];
    const dy = particlePos[1] - this.position[1];
    const dz = particlePos[2] - this.position[2];
    const r2 = dx * dx + dy * dy + dz * dz;
    const r = Math.sqrt(r2);
    if (r < 0.001) return [0, 0, 0];
    const rs = this._rs;
    const dragFactor = this.spin * rs * rs / (r2 * r);
    const ax = -dy * dragFactor;
    const ay = dx * dragFactor;
    const az = 0;
    return [ax * this.spin * 0.1, ay * this.spin * 0.1, az * this.spin * 0.1];
  }

  isInErgosphere(pos) {
    const dx = pos[0] - this.position[0];
    const dy = pos[1] - this.position[1];
    const dz = pos[2] - this.position[2];
    const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const theta = Math.acos(Math.max(-1, Math.min(1, dy / (r || 1))));
    const rErgo = this.ergosphereRadius(theta);
    return r < rErgo;
  }

  isInsideISCO(pos) {
    const dx = pos[0] - this.position[0];
    const dy = pos[1] - this.position[1];
    const dz = pos[2] - this.position[2];
    const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
    return r < this.iscoRadius;
  }

  kerrMetricParams() {
    const a = this.spin;
    return {
      rs: this._rs,
      spin: a,
      isco: this.iscoRadius,
      ergoPole: this.ergosphereRadius(0),
      ergoEquator: this.ergosphereRadius(Math.PI / 2)
    };
  }
}
