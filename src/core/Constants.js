export const Constants = {
  G: 6.674e-11,
  c: 2.998e8,
  M_sun: 1.989e30,
  R_sun: 6.957e8,
  PI: Math.PI,
  TWO_PI: 2 * Math.PI,

  schwarzschildRadius(mass) {
    return (2 * this.G * mass) / (this.c * this.c);
  }
};
