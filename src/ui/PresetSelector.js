import { PRESETS } from '../presets/presets.js';

export class PresetSelector {
  constructor(cameraManager, physicsEngine) {
    this.cameraManager = cameraManager;
    this.physics = physicsEngine;
    this._presetKeys = Object.keys(PRESETS);
    this._labels = this._presetKeys.map(k => PRESETS[k].name);
    this._active = this._presetKeys[0];
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.display = 'flex';
    this._el.style.gap = '4px';
    this._presetKeys.forEach((key, i) => {
      const btn = document.createElement('button');
      btn.className = 'ui-btn' + (key === this._active ? ' active' : '');
      btn.textContent = this._labels[i];
      btn.addEventListener('click', () => this._select(key, btn));
      this._el.appendChild(btn);
    });
    container.appendChild(this._el);
    this._loadPreset(this._active);
  }

  _select(key) {
    this._active = key;
    this._loadPreset(key);
    this._el.querySelectorAll('.ui-btn').forEach((btn, i) => {
      btn.classList.toggle('active', this._presetKeys[i] === key);
    });
  }

  _loadPreset(key) {
    const preset = PRESETS[key];
    if (!preset) return;
    const data = preset.fn();
    this.physics.loadPreset(data);
    if (data.camera) {
      this.cameraManager.transitionTo(
        data.camera.theta,
        data.camera.phi,
        data.camera.distance,
        data.camera.focus
      );
    }
  }
}
