export class PhaseIndicator {
  constructor() {
    this._el = null;
    this._phase = 'idle';
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.marginTop = '8px';
    const label = document.createElement('div');
    label.className = 'ui-label';
    label.textContent = 'Phase';
    this._el.appendChild(label);

    this._phaseEl = document.createElement('div');
    this._phaseEl.style.cssText = 'color: #8f8; font-weight: bold; margin-top: 2px;';
    this._phaseEl.textContent = 'Idle';
    this._el.appendChild(this._phaseEl);
    container.appendChild(this._el);
  }

  setPhase(phase) {
    this._phase = phase;
    if (this._phaseEl) {
      const labels = {
        idle: 'Idle',
        inspiral: 'Inspiral',
        merger: 'Merger',
        ringdown: 'Ringdown',
        accretion: 'Accretion',
        collision: 'Collision'
      };
      this._phaseEl.textContent = labels[phase] || phase;
    }
  }
}
