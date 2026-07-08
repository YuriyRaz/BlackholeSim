export class CameraModeToggle {
  constructor(cameraManager) {
    this.cameraManager = cameraManager;
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.marginTop = '8px';
    const label = document.createElement('div');
    label.className = 'ui-label';
    label.textContent = 'Camera';
    this._el.appendChild(label);

    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.gap = '4px';
    row.style.marginTop = '4px';

    this._freeBtn = document.createElement('button');
    this._freeBtn.className = 'ui-btn active';
    this._freeBtn.textContent = 'Free';
    this._freeBtn.addEventListener('click', () => {
      this.cameraManager.setMode('free');
      this._freeBtn.classList.add('active');
      this._cinematicBtn.classList.remove('active');
    });

    this._cinematicBtn = document.createElement('button');
    this._cinematicBtn.className = 'ui-btn';
    this._cinematicBtn.textContent = 'Cine';
    this._cinematicBtn.title = 'Cinematic auto-orbit';
    this._cinematicBtn.addEventListener('click', () => {
      this.cameraManager.setMode('cinematic');
      this._cinematicBtn.classList.add('active');
      this._freeBtn.classList.remove('active');
    });

    row.appendChild(this._freeBtn);
    row.appendChild(this._cinematicBtn);
    this._el.appendChild(row);
    container.appendChild(this._el);
  }
}
