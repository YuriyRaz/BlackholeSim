export class PhysicsInfo {
  constructor() {
    this._el = null;
    this._fpsEl = null;
    this._frameCount = 0;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.innerHTML = `
      <div><span class="ui-label">FPS: </span><span id="fps-val">0</span></div>
      <div><span class="ui-label">Particles: </span><span id="particle-count">0</span></div>
      <div><span class="ui-label">Mass: </span><span>10 M☉</span></div>
      <div><span class="ui-label">Spin: </span><span>0.7</span></div>
    `;
    this._fpsEl = this._el.querySelector('#fps-val');
    container.appendChild(this._el);
  }

  updateFPS(fps) {
    this._frameCount++;
    if (this._frameCount % 10 === 0 && this._fpsEl) {
      this._fpsEl.textContent = Math.round(fps);
    }
  }
}
