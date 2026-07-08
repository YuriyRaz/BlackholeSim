import { Star } from './Star.js';

export class NeutronStar extends Star {
  constructor(options = {}) {
    super({ ...options, type: 'neutronstar' });
    this.magneticField = options.magneticField || 1e8;
    this.rotationRate = options.rotationRate || 100;
    this.pulsarBeams = options.pulsarBeams !== undefined ? options.pulsarBeams : true;
    this.starRadius = options.radius || 0.00001;
  }

  get radius() {
    return 0.003;
  }

  get color() {
    return [0.7, 0.8, 1.0];
  }
}
