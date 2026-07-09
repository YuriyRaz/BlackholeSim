export class LoadingScreen {
  constructor() {
    this._element = null;
    this._progressBar = null;
    this._textElement = null;
    this._previewElement = null;
    this._errorElement = null;
    this._retryButton = null;
    this._visible = false;
    this._progress = 0;
    this._phase = 'textures';
    
    this._create();
  }

  _create() {
    this._element = document.createElement('div');
    this._element.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: #000;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      transition: opacity 0.5s;
    `;
    
    this._previewElement = document.createElement('div');
    this._previewElement.style.cssText = `
      color: #fff;
      font-family: monospace;
      font-size: 32px;
      margin-bottom: 40px;
      text-align: center;
    `;
    this._previewElement.textContent = 'Black Hole Simulator';
    this._element.appendChild(this._previewElement);
    
    const progressContainer = document.createElement('div');
    progressContainer.style.cssText = `
      width: 300px;
      height: 4px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 2px;
      overflow: hidden;
      margin-bottom: 20px;
    `;
    
    this._progressBar = document.createElement('div');
    this._progressBar.style.cssText = `
      width: 0%;
      height: 100%;
      background: #4a9eff;
      transition: width 0.3s;
    `;
    progressContainer.appendChild(this._progressBar);
    this._element.appendChild(progressContainer);
    
    this._textElement = document.createElement('div');
    this._textElement.style.cssText = `
      color: rgba(255, 255, 255, 0.7);
      font-family: monospace;
      font-size: 14px;
    `;
    this._textElement.textContent = 'Loading textures...';
    this._element.appendChild(this._textElement);
    
    this._errorElement = document.createElement('div');
    this._errorElement.style.cssText = `
      color: #ff6b6b;
      font-family: monospace;
      font-size: 14px;
      margin-top: 20px;
      text-align: center;
      display: none;
    `;
    this._element.appendChild(this._errorElement);
    
    this._retryButton = document.createElement('button');
    this._retryButton.style.cssText = `
      margin-top: 10px;
      padding: 8px 16px;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.3);
      color: #fff;
      font-family: monospace;
      cursor: pointer;
      border-radius: 4px;
      display: none;
    `;
    this._retryButton.textContent = 'Retry';
    this._element.appendChild(this._retryButton);
    
    document.body.appendChild(this._element);
  }

  show() {
    this._visible = true;
    this._element.style.display = 'flex';
    this._element.style.opacity = '1';
    this._progress = 0;
    this._updateProgress();
  }

  hide() {
    this._element.style.opacity = '0';
    setTimeout(() => {
      this._element.style.display = 'none';
      this._visible = false;
    }, 500);
  }

  setProgress(progress, phase = null) {
    this._progress = Math.max(0, Math.min(1, progress));
    
    if (phase) {
      this._phase = phase;
    }
    
    this._updateProgress();
  }

  _updateProgress() {
    const percentage = Math.round(this._progress * 100);
    this._progressBar.style.width = `${percentage}%`;
    
    if (this._phase === 'textures') {
      this._textElement.textContent = `Loading textures... ${percentage}%`;
    } else if (this._phase === 'shaders') {
      this._textElement.textContent = `Compiling shaders... ${percentage}%`;
    }
  }

  showError(message, onRetry = null) {
    this._errorElement.textContent = message;
    this._errorElement.style.display = 'block';
    this._retryButton.style.display = 'block';
    
    if (onRetry) {
      this._retryButton.onclick = () => {
        this.hideError();
        onRetry();
      };
    }
  }

  hideError() {
    this._errorElement.style.display = 'none';
    this._retryButton.style.display = 'none';
  }

  get visible() {
    return this._visible;
  }

  destroy() {
    if (this._element && this._element.parentNode) {
      this._element.parentNode.removeChild(this._element);
    }
  }
}