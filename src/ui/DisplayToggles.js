export class DisplayToggles {
  constructor(settings) {
    this.settings = settings;
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    const items = [
      ['lensing', 'Lensing'], ['particles', 'Particles'], ['stars', 'Stars'],
      ['bodies', 'Bodies'], ['postProcessing', 'Post-FX']
    ];
    items.forEach(([key, label]) => {
      const div = document.createElement('label');
      div.className = 'ui-toggle';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = this.settings[key];
      cb.addEventListener('change', () => { this.settings[key] = cb.checked; });
      const span = document.createElement('span');
      span.className = 'ui-label';
      span.textContent = label;
      div.appendChild(cb);
      div.appendChild(span);
      this._el.appendChild(div);
    });
    container.appendChild(this._el);
  }
}
