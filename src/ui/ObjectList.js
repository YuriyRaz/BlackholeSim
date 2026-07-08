export class ObjectList {
  constructor(cameraManager) {
    this.cameraManager = cameraManager;
    this._el = null;
    this._listEl = null;
    this._selectedId = null;
    this._bodies = [];
    this._onSelect = null;
  }

  set onSelect(fn) { this._onSelect = fn; }

  mount(container) {
    this._el = document.createElement('div');
    this._el.innerHTML = `
      <div class="ui-label">Objects</div>
      <div id="object-list" style="max-height:200px;overflow-y:auto;"></div>
    `;
    container.appendChild(this._el);
    this._listEl = this._el.querySelector('#object-list');
  }

  update(bodies) {
    this._bodies = bodies;
    this._listEl.innerHTML = '';
    const typeIcons = { blackhole: '⬤', star: '★', neutronstar: '⊕', debris: '·' };
    const typeColors = { blackhole: '#333', star: '#fd3', neutronstar: '#8af', debris: '#aaa' };

    for (const body of bodies) {
      if (body.type === 'debris') continue;
      const item = document.createElement('div');
      item.style.cssText = `cursor:pointer;padding:2px 4px;font-size:11px;display:flex;align-items:center;gap:4px;border-radius:3px;${body.id === this._selectedId ? 'background:rgba(100,150,255,0.3);' : ''}`;
      item.innerHTML = `<span style="color:${typeColors[body.type] || '#fff'}">${typeIcons[body.type] || '?'}</span><span>${body.name}</span><span style="color:#888;margin-left:auto">${body.mass.toFixed(1)}M☉</span>`;
      item.addEventListener('click', () => this._select(body));
      item.addEventListener('mouseenter', () => { item.style.background = 'rgba(255,255,255,0.1)'; });
      item.addEventListener('mouseleave', () => { item.style.background = body.id === this._selectedId ? 'rgba(100,150,255,0.3)' : ''; });
      this._listEl.appendChild(item);
    }
  }

  _select(body) {
    this._selectedId = body.id;
    if (this._onSelect) this._onSelect(body);
    this.update(this._bodies);
  }

  deselect() {
    this._selectedId = null;
    this.update(this._bodies);
  }
}
