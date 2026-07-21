export class RNG {
  constructor(seed = 42) {
    this._state = seed >>> 0;
  }

  next() {
    let t = this._state += 0x6D2B79F5;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }

  nextFloat(min = 0, max = 1) {
    return min + this.next() * (max - min);
  }

  nextInt(min, max) {
    return Math.floor(this.nextFloat(min, max + 1));
  }

  nextGaussian(mean = 0, std = 1) {
    const u1 = this.next();
    const u2 = this.next();
    const z = Math.sqrt(-2 * Math.log(u1 + 1e-15)) * Math.cos(2 * Math.PI * u2);
    return mean + z * std;
  }

  shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
      const j = this.nextInt(0, i);
      const tmp = array[i];
      array[i] = array[j];
      array[j] = tmp;
    }
    return array;
  }
}
