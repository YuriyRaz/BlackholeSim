export class Profiler {
  constructor() {
    this._frames = new Float64Array(60);
    this._index = 0;
    this._count = 0;
    this._fps = 0;
    this._dt = 0;
  }

  update(dt) {
    this._dt = dt;
    this._frames[this._index] = dt;
    this._index = (this._index + 1) % 60;
    if (this._count < 60) this._count++;
    let sum = 0;
    for (let i = 0; i < this._count; i++) sum += this._frames[i];
    this._fps = sum > 0 ? this._count / sum : 0;
  }

  get fps() { return this._fps; }
  get frameTime() { return this._dt * 1000; }
}
