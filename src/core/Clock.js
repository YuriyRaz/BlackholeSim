export class Clock {
  constructor() {
    this._last = performance.now();
    this._delta = 0;
    this._elapsed = 0;
  }

  update() {
    const now = performance.now();
    this._delta = (now - this._last) / 1000;
    this._last = now;
    this._elapsed += this._delta;
    return this._delta;
  }

  reset() {
    this._delta = 0;
    this._last = performance.now();
  }

  get delta() { return this._delta; }
  get elapsed() { return this._elapsed; }
}
