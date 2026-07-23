import { Body } from './Body.js';
import { Constants } from '../core/Constants.js';

export class Star extends Body {
  constructor(options = {}) {
    super({ ...options, type: 'star' });
    this.starRadius = options.radius || 1.0;
    this.temperature = options.temperature || 5778;
    this.luminosity = options.luminosity || 3.828e26;
    this.deformation = 0;
  }

  get radius() {
    return this.starRadius * 0.3;
  }

  get color() {
    const t = this.temperature;
    if (t > 30000) return [0.6, 0.7, 1.0];
    if (t > 10000) return [0.7, 0.8, 1.0];
    if (t > 7500) return [0.9, 0.9, 1.0];
    if (t > 6000) return [1.0, 1.0, 0.9];
    if (t > 5200) return [1.0, 0.95, 0.8];
    if (t > 3700) return [1.0, 0.8, 0.6];
    return [1.0, 0.6, 0.4];
  }

  get disruptionRadius() {
    return Constants.tidalDisruptionRadius(
      this.mass > 0 ? this.mass : 10,
      this.starRadius,
      this.mass
    );
  }

  generateDisruptionParticles(blackHole) {
    return [];
  }

  _directionFrom(from, to) {
    return this._normalize([
      to[0] - from[0],
      to[1] - from[1],
      to[2] - from[2]
    ]);
  }

  _tangentFromVelocity(radial) {
    const radialSpeed = this.velocity[0] * radial[0] + this.velocity[1] * radial[1] + this.velocity[2] * radial[2];
    const tangent = [
      this.velocity[0] - radial[0] * radialSpeed,
      this.velocity[1] - radial[1] * radialSpeed,
      this.velocity[2] - radial[2] * radialSpeed
    ];
    const tLen = Math.hypot(...tangent);
    if (tLen > 0.001) return tangent.map(v => v / tLen);
    return Math.abs(radial[1]) < 0.9 ? this._normalize([-radial[2], 0, radial[0]]) : [1, 0, 0];
  }

  _normalize(v) {
    const len = Math.hypot(...v);
    return len > 0 ? v.map(component => component / len) : [1, 0, 0];
  }

  computeDeformation(blackHole) {
    const dx = this.position[0] - blackHole.position[0];
    const dy = this.position[1] - blackHole.position[1];
    const dz = this.position[2] - blackHole.position[2];
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const dR = Constants.tidalDisruptionRadius(blackHole.mass, this.starRadius, this.mass);
    if (d < 0.001) return 0;
    this.deformation = Math.min(3.0, Math.pow(dR / d, 2));
    return this.deformation;
  }
}
