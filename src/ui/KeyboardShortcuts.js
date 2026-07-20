export class KeyboardShortcuts {
  constructor() {
    this._visible = false;
    this._el = null;
    this._create();
    window.addEventListener('keydown', (e) => {
      if (e.key.toLowerCase() === 'h' && !e.target.closest('input')) this._toggle();
    });
  }

  _create() {
    this._el = document.createElement('div');
    this._el.className = 'ui-panel';
    this._el.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:100;transition:opacity 0.5s;pointer-events:none;opacity:0;';
    this._el.innerHTML = `
      <div style="text-align:center;">
        <div style="font-size:14px;font-weight:bold;margin-bottom:8px;">Keyboard Shortcuts</div>
        <div>Left drag — Orbit</div>
        <div>Right drag — Pan</div>
        <div>Scroll — Zoom</div>
        <div>WASD/QE — Move camera</div>
        <div>R — Reset camera</div>
        <div>C — Toggle cinematic</div>
        <div>Space — Play/Pause</div>
        <div>[ / ] — Speed down/up</div>
        <div>H — Toggle this overlay</div>
      </div>
    `;
    document.getElementById('app').appendChild(this._el);
  }

  _fadeOut() { this._el.style.opacity = '0'; this._visible = false; }
  _fadeIn() { this._el.style.opacity = '1'; this._visible = true; }
  _toggle() { this._visible ? this._fadeOut() : this._fadeIn(); }
}
