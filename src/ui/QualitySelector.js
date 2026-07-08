export class QualitySelector {
  constructor(quality) {
    this.quality = quality;
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.marginTop = '8px';
    const label = document.createElement('div');
    label.className = 'ui-label';
    label.textContent = 'Quality';
    this._el.appendChild(label);

    const modes = ['Minimum', 'Low', 'Medium', 'High', 'Auto'];
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.gap = '4px';
    row.style.marginTop = '4px';
    modes.forEach(m => {
      const btn = document.createElement('button');
      btn.className = 'ui-btn';
      btn.textContent = m.charAt(0);
      btn.title = m;
      btn.addEventListener('click', () => {
        this.quality.setMode(m);
        row.querySelectorAll('.ui-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
      if (m === 'Auto') btn.classList.add('active');
      row.appendChild(btn);
    });
    this._el.appendChild(row);
    container.appendChild(this._el);
  }
}
