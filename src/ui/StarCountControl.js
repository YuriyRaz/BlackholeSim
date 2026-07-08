export class StarCountControl {
  constructor(quality) {
    this.quality = quality;
    this._el = null;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.style.marginTop = '8px';
    const label = document.createElement('div');
    label.className = 'ui-label';
    label.textContent = 'Stars';
    this._el.appendChild(label);

    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.alignItems = 'center';
    row.style.gap = '6px';
    row.style.marginTop = '4px';

    this._slider = document.createElement('input');
    this._slider.type = 'range';
    this._slider.min = '1000';
    this._slider.max = '5000';
    this._slider.value = String(this.quality.starCount);
    this._slider.style.cssText = 'width: 80px; accent-color: #6af;';
    this._slider.addEventListener('input', () => {
      this.quality.starCount = parseInt(this._slider.value, 10);
      this._valueEl.textContent = this.quality.starCount;
    });

    this._valueEl = document.createElement('span');
    this._valueEl.style.cssText = 'font-size: 11px; min-width: 30px;';
    this._valueEl.textContent = this.quality.starCount;

    row.appendChild(this._slider);
    row.appendChild(this._valueEl);
    this._el.appendChild(row);
    container.appendChild(this._el);
  }
}
