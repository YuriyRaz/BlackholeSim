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

  derivePhase(state) {
    const bhs = state.bodies.filter(b => b.type === 'blackhole');
    const hasAccretion = state.accretionRate > 0;
    const hasDisruption = state.bodies.some(b => b.disrupted);

    let phaseText = '';

    if (bhs.length >= 2) {
      const dx = bhs[1].position[0] - bhs[0].position[0];
      const dy = bhs[1].position[1] - bhs[0].position[1];
      const dz = bhs[1].position[2] - bhs[0].position[2];
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const rs0 = bhs[0].rs || 1;
      const separationRatio = dist / rs0;

      if (separationRatio < 5) {
        phaseText = 'Merger';
      } else {
        phaseText = `Inspiral \u2014 ${separationRatio.toFixed(1)}\u00d7Rs`;
      }
    } else if (bhs.length === 1) {
      phaseText = 'Remnant';
    }

    if (hasDisruption) {
      phaseText += (phaseText ? ' | ' : '') + 'Tidal disruption';
    }
    const hasFallback = (state.fallbackRate || 0) > 0;
    if (hasFallback) {
      phaseText += (phaseText ? ' | ' : '') + `Fallback \u2014 dM/dt = ${state.fallbackRate.toExponential(2)} M\u2609/yr`;
    }
    if (hasAccretion) {
      phaseText += (phaseText ? ' | ' : '') + `Accretion \u2014 dM/dt = ${state.accretionRate.toExponential(2)} M\u2609/yr`;
    } else if (state.gasParticles.length > 0 || (state.matterParticles?.length ?? 0) > 0) {
      phaseText += (phaseText ? ' | ' : '') + 'Quiescent';
    }
    phaseText += (phaseText ? ' | ' : '') + 'No MHD jet model';

    this.setPhase(phaseText || 'Idle');
  }

  setPhase(phase) {
    this._phase = phase;
    if (this._phaseEl) {
      this._phaseEl.textContent = phase;
    }
  }
}
