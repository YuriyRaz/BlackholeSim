export const SimUnits = {
  length: { unit: 'km', label: 'kilometre' },
  velocity: { unit: 'km/s', label: 'km per second' },
  mass: { unit: 'M_sun', label: 'solar masses', kg: 1.989e30 },
  time: { unit: 's', label: 'second' },
  density: { unit: 'M_sun / km^3', label: 'solar masses per cubic km' },
  pressure: { unit: 'M_sun / (km * s^2)', label: 'internal pressure units' },
  energy: { unit: 'M_sun * km^2 / s^2', label: 'specific energy units' },
  temperature: { unit: 'K', label: 'Kelvin' },

  G: 6.674e-11 * 1.989e30 / 1e9,

  gravitationalPotential: 'pseudo-newtonian',

  describe() {
    return {
      length: `${this.length.label} (${this.length.unit})`,
      velocity: `${this.velocity.label} (${this.velocity.unit})`,
      mass: `${this.mass.label} (${this.mass.unit})`,
      time: `${this.time.label} (${this.time.unit})`,
      density: `${this.density.label} (${this.density.unit})`,
      gravitationalPotential: this.gravitationalPotential,
    };
  },
};
