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

  generateDisruptionParticles() {
    const n = Math.max(
      Constants.minStarParticles,
      Math.min(
        Constants.maxStarParticles,
        Math.floor(this.mass / Constants.starParticleMassFraction)
      )
    );
    const particles = [];
    const r = this.starRadius * Constants.R_sun;
    for (let i = 0; i < n; i++) {
      let px, py, pz;
      do {
        px = (Math.random() * 2 - 1) * r;
        py = (Math.random() * 2 - 1) * r;
        pz = (Math.random() * 2 - 1) * r;
      } while (px * px + py * py + pz * pz > r * r);
      const perturbation = 0.1;
      const vOrb = Math.sqrt(Constants.G * this.mass * Constants.M_sun / (r || 1));
      particles.push({
        position: [
          this.position[0] + px,
          this.position[1] + py,
          this.position[2] + pz
        ],
        velocity: [
          this.velocity[0] + (Math.random() * 2 - 1) * vOrb * perturbation,
          this.velocity[1] + (Math.random() * 2 - 1) * vOrb * perturbation,
          this.velocity[2] + (Math.random() * 2 - 1) * vOrb * perturbation
        ],
        mass: this.mass / n
      });
    }
    return particles;
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
