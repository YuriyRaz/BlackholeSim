const QUALITY_LEVELS = {
  Minimum: { lensingResolution: 'half', lensingSteps: 10, particleBudget: 6000, bloom: false, tonemap: true, fxaa: false, vignette: false },
  Low: { lensingResolution: 'half', lensingSteps: 15, particleBudget: 12000, bloom: true, tonemap: true, fxaa: false, vignette: true },
  Medium: { lensingResolution: 'half', lensingSteps: 20, particleBudget: 20000, bloom: true, tonemap: true, fxaa: true, vignette: true },
  High: { lensingResolution: 'full', lensingSteps: 30, particleBudget: 35000, bloom: true, tonemap: true, fxaa: true, vignette: true }
};

export class AdaptiveQuality {
  constructor(profiler) {
    this.profiler = profiler;
    this._mode = 'Auto';
    this._currentLevel = 'Medium';
    this._lowFrames = 0;
    this._highFrames = 0;
    this._cooldown = 0;
    this._frameSkip = false;
    this._skipFrames = 0;
    this._starCount = 2000;
  }

  get starCount() { return this._starCount; }
  set starCount(v) { this._starCount = Math.max(1000, Math.min(5000, Math.round(v))); }

  get mode() { return this._mode; }
  get level() { return this._mode === 'Auto' ? `Auto (${this._currentLevel})` : this._currentLevel; }

  setMode(mode) {
    this._mode = mode;
    if (mode !== 'Auto') {
      this._currentLevel = mode;
    }
  }

  getSettings() {
    const s = QUALITY_LEVELS[this._currentLevel];
    return {
      ...s,
      starCount: this._starCount,
      frameSkip: this._frameSkip
    };
  }

  update() {
    const fps = this.profiler.fps;
    if (this._mode !== 'Auto') return;

    if (this._cooldown > 0) { this._cooldown--; return; }

    if (fps < 28) {
      this._lowFrames++;
      this._highFrames = 0;
    } else if (fps > 55) {
      this._highFrames++;
      this._lowFrames = 0;
    } else {
      this._lowFrames = 0;
      this._highFrames = 0;
    }

    if (this._lowFrames >= 120) {
      this._downgrade();
      this._lowFrames = 0;
      this._cooldown = 120;
    } else if (this._highFrames >= 120) {
      this._upgrade();
      this._highFrames = 0;
      this._cooldown = 120;
    }

    if (this._currentLevel === 'Minimum' && fps < 20) {
      this._skipFrames++;
      if (this._skipFrames >= 60) this._frameSkip = true;
    } else if (this._frameSkip && fps > 25) {
      this._skipFrames++;
      if (this._skipFrames >= 60) { this._frameSkip = false; this._skipFrames = 0; }
    }
  }

  _downgrade() {
    const order = ['High', 'Medium', 'Low', 'Minimum'];
    const idx = order.indexOf(this._currentLevel);
    if (idx < order.length - 1) {
      this._currentLevel = order[idx + 1];
      this._skipFrames = 0;
      this._frameSkip = false;
    }
  }

  _upgrade() {
    const order = ['High', 'Medium', 'Low', 'Minimum'];
    const idx = order.indexOf(this._currentLevel);
    if (idx > 0) {
      this._currentLevel = order[idx - 1];
      this._skipFrames = 0;
      this._frameSkip = false;
    }
  }
}
