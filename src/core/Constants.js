export const Constants = {
  G: 6.674e-11,
  c: 2.998e8,
  M_sun: 1.989e30,
  R_sun: 6.957e8,
  PI: Math.PI,
  TWO_PI: 2 * Math.PI,
  DEG_TO_RAD: Math.PI / 180,

  schwarzschildRadius(massSolar) {
    const massKg = massSolar * this.M_sun;
    return (2 * this.G * massKg) / (this.c * this.c);
  },

  schwarzschildRadiusKm(massSolar) {
    return 2.95 * massSolar;
  },

  iscoRadius(a) {
    const z1 = 1 + Math.pow(1 - a * a, 1 / 3) * (Math.pow(1 + a, 1 / 3) + Math.pow(1 - a, 1 / 3));
    const z2 = Math.sqrt(3 * a * a + z1 * z1);
    return 3 + z2 - Math.sqrt((3 - z1) * (3 + z1 + 2 * z2));
  },

  ergosphereRadius(a, theta) {
    const Rs = 1;
    return Rs * (1 + Math.sqrt(1 - a * a * Math.cos(theta) * Math.cos(theta)));
  },

  orbitalVelocity(M, r) {
    return Math.sqrt(this.G * M * this.M_sun / r);
  },

  orbitalPeriod(M, r) {
    return this.TWO_PI * Math.sqrt(Math.pow(r, 3) / (this.G * M * this.M_sun));
  },

  tidalDisruptionRadius(M_bh, R_star, M_star) {
    return R_star * this.R_sun * Math.pow(M_bh * this.M_sun / (M_star * this.M_sun), 1 / 3);
  },

  chirpMass(m1, m2) {
    return Math.pow(m1 * m2, 0.6) / Math.pow(m1 + m2, 0.2);
  },

  softening: 0.01,
  dt_min: 0.0001,
  dt_max: 0.01,
  dt_factor: 0.01,
  barnesHutTheta: 0.5,
  barnesHutThreshold: 100,

  alpha_visc: 0.1,
  jetMaxParticles: 2000,
  jetMaxDistance: 200,
  trailMaxPoints: 200,

  snapshotInterval: 10,
  maxSnapshots: 600,
  maxRecomputeSteps: 100,

  gasMinRadius: 10,
  gasMaxRadius: 50,
  gasDiskThickness: 0.1,

  minStarParticles: 50,
  maxStarParticles: 500,
  starParticleMassFraction: 0.1
};
