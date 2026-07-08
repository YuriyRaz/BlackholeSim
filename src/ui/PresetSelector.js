export class PresetSelector {
  constructor(cameraManager) {
    this.cameraManager = cameraManager;
    this._presets = ['cinematic', 'topdown', 'edgeon', 'closeup', 'system'];
    this._labels = ['Cinematic', 'Top-down', 'Edge-on', 'Close-up', 'System'];
    this._active = 'cinematic';
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.display = 'flex';
    this._el.style.gap = '4px';
    this._presets.forEach((preset, i) => {
      const btn = document.createElement('button');
      btn.className = 'ui-btn' + (preset === this._active ? ' active' : '');
      btn.textContent = this._labels[i];
      btn.addEventListener('click', () => this._select(preset, btn));
      this._el.appendChild(btn);
    });
    container.appendChild(this._el);
  }

  _select(preset) {
    this._active = preset;
    this.cameraManager.setPreset(preset);
    this._el.querySelectorAll('.ui-btn').forEach((btn, i) => {
      btn.classList.toggle('active', this._presets[i] === preset);
    });
  }
}
