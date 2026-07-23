export class PhysicsInfo {
  constructor() {
    this._el = null;
    this._fpsEl = null;
    this._frameCount = 0;
    this._data = {};
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.innerHTML = `
      <div><span class="ui-label">FPS: </span><span id="fps-val">0</span></div>
      <div><span class="ui-label">Bodies: </span><span id="body-count">0</span></div>
      <div><span class="ui-label">Gas: </span><span id="gas-count">0</span></div>
      <div><span class="ui-label">Matter: </span><span id="matter-count">0</span></div>
      <div><span class="ui-label">Jets: </span><span id="jet-count">N/A (no MHD)</span></div>
      <div><span class="ui-label">Time: </span><span id="sim-time">0.00s</span></div>
      <div><span class="ui-label">Accretion: </span><span id="accretion-rate">0</span></div>
      <div><span class="ui-label">Fallback: </span><span id="fallback-rate">0</span></div>
      <div><span class="ui-label">GW f: </span><span id="gw-freq">0 Hz</span></div>
      <div><span class="ui-label">GW h: </span><span id="gw-strain">0</span></div>
      <div id="selected-info" style="margin-top:4px;border-top:1px solid rgba(255,255,255,0.2);padding-top:4px;"></div>
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

  update(state) {
    if (!this._el) return;
    const bodyCount = state.bodies.filter(b => b.type !== 'debris').length;
    const gasCount = state.gasParticles.length;
    const matterCount = state.matterParticles?.length ?? 0;
    this._el.querySelector('#body-count').textContent = bodyCount;
    this._el.querySelector('#gas-count').textContent = gasCount;
    this._el.querySelector('#matter-count').textContent = matterCount;
    this._el.querySelector('#sim-time').textContent = state.simTime.toFixed(2) + 's';
    this._el.querySelector('#accretion-rate').textContent = state.accretionRate.toExponential(2);
    this._el.querySelector('#fallback-rate').textContent = (state.fallbackRate || 0).toExponential(2);
    this._el.querySelector('#gw-freq').textContent = state.gw.frequency.toFixed(1) + ' Hz';
    this._el.querySelector('#gw-strain').textContent = state.gw.strain.toExponential(2);
  }

  setSelectedBody(body) {
    const infoEl = this._el?.querySelector('#selected-info');
    if (!infoEl) return;
    if (!body) {
      infoEl.innerHTML = '';
      return;
    }
    const vel = Math.sqrt(body.velocity[0] ** 2 + body.velocity[1] ** 2 + body.velocity[2] ** 2);
    infoEl.innerHTML = `
      <div style="font-size:11px;color:#6af;">${body.name}</div>
      <div><span class="ui-label">Type: </span>${body.type}</div>
      <div><span class="ui-label">Mass: </span>${body.mass.toFixed(2)} M☉</div>
      <div><span class="ui-label">Vel: </span>${vel.toFixed(2)} km/s</div>
      ${body.spin ? `<div><span class="ui-label">Spin: </span>${body.spin.toFixed(3)}</div>` : ''}
    `;
  }
}
