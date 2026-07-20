import { Body } from './Body.js';
import { Constants } from '../core/Constants.js';

export class Star extends Body {
  constructor(options = {}) {
    super({ ...options, type: 'star' });
    this.starRadius = options.radius || 1.0;
    this.temperature = options.temperature || 5778;
    this.luminosity = options.luminosity || 3.828e26;
    this.pulsationFreq = Math.random() * 2 + 0.5;
    this.pulsationPhase = Math.random() * Constants.TWO_PI;
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

  generateDisruptionParticles(blackHole = null) {
    const baseCount = Math.max(
      Constants.minStarParticles,
      Math.min(
        Constants.maxStarParticles,
        Math.floor(this.mass / Constants.starParticleMassFraction)
      )
    );
    const n = blackHole ? Math.max(baseCount, 1400) : baseCount;
    const particles = [];
    const stellarRadius = this.starRadius * Constants.R_sun_km;
    const dR = blackHole ? Constants.tidalDisruptionRadius(blackHole.mass, this.starRadius, this.mass) : stellarRadius;
    const streamLength = blackHole ? dR * 1.75 : stellarRadius;
    const streamWidth = blackHole ? dR * 0.045 : stellarRadius;
    const visualSize = blackHole ? dR * 0.13 : undefined;
    const radial = this._directionFrom(blackHole?.position || [0, 0, 0], this.position);
    const tangent = this._tangentFromVelocity(radial);
    const normal = this._normalize([
      radial[1] * tangent[2] - radial[2] * tangent[1],
      radial[2] * tangent[0] - radial[0] * tangent[2],
      radial[0] * tangent[1] - radial[1] * tangent[0]
    ]);
    const speed = Math.hypot(...this.velocity);
    for (let i = 0; i < n; i++) {
      const streamT = (i / Math.max(n - 1, 1)) - 0.5;
      const jitterT = (Math.random() - 0.5) * 0.18;
      const along = (streamT + jitterT) * streamLength;
      const sweep = Math.sign(streamT || 1) * streamT * streamT * streamLength * 0.42;
      const across = (Math.random() - 0.5) * streamWidth;
      const lift = (Math.random() - 0.5) * streamWidth * 0.35;
      const perturbation = 0.1;
      const vOrb = Math.sqrt(Constants.G_solar_km * this.mass / (stellarRadius || 1));
      const shear = blackHole ? streamT * speed * 0.7 : 0;
      let position = [
        this.position[0] + radial[0] * along + tangent[0] * (across + sweep) + normal[0] * lift,
        this.position[1] + radial[1] * along + tangent[1] * (across + sweep) + normal[1] * lift,
        this.position[2] + radial[2] * along + tangent[2] * (across + sweep) + normal[2] * lift
      ];
      if (blackHole && streamT < -0.2) {
        const wrap = (-streamT - 0.2) / 0.3;
        const angle = -wrap * Math.PI * 0.95 + (Math.random() - 0.5) * 0.12;
        const radius = dR * (0.18 + wrap * 0.35) + (Math.random() - 0.5) * streamWidth;
        position = [
          blackHole.position[0] + radial[0] * Math.cos(angle) * radius + tangent[0] * Math.sin(angle) * radius + normal[0] * lift,
          blackHole.position[1] + radial[1] * Math.cos(angle) * radius + tangent[1] * Math.sin(angle) * radius + normal[1] * lift,
          blackHole.position[2] + radial[2] * Math.cos(angle) * radius + tangent[2] * Math.sin(angle) * radius + normal[2] * lift
        ];
      }
      particles.push({
        position,
        velocity: [
          this.velocity[0] + radial[0] * shear + (Math.random() * 2 - 1) * vOrb * perturbation,
          this.velocity[1] + radial[1] * shear + (Math.random() * 2 - 1) * vOrb * perturbation,
          this.velocity[2] + radial[2] * shear + (Math.random() * 2 - 1) * vOrb * perturbation
        ],
        mass: this.mass / n,
        renderRadius: visualSize,
        renderSize: visualSize
      });
    }
    return particles;
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

  updatePulsation(time) {
    const amp = 0.005;
    return 1.0 + amp * Math.sin(this.pulsationFreq * time + this.pulsationPhase);
  }
}
