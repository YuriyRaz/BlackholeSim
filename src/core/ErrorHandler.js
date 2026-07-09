export class ErrorHandler {
  constructor() {
    this._errorDisplay = null;
    this._contextLost = false;
    this._onContextLost = null;
    this._onContextRestored = null;
    this._createErrorDisplay();
  }

  _createErrorDisplay() {
    this._errorDisplay = document.createElement('div');
    this._errorDisplay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      background: rgba(180, 40, 40, 0.95);
      color: #fff;
      padding: 12px 20px;
      font-family: monospace;
      font-size: 14px;
      z-index: 10001;
      display: none;
      flex-direction: column;
      gap: 8px;
    `;
    document.body.appendChild(this._errorDisplay);
  }

  setupWebGLContextLoss(canvas, renderer) {
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      this._contextLost = true;
      this.showError('WebGL context lost. Attempting to restore...');
      
      if (this._onContextLost) {
        this._onContextLost();
      }
    });
    
    canvas.addEventListener('webglcontextrestored', () => {
      this._contextLost = false;
      this.hideError();
      
      if (this._onContextRestored) {
        this._onContextRestored();
      }
    });
  }

  handleShaderCompilationError(error, shaderSource) {
    const lines = shaderSource.split('\n');
    const errorMatch = error.match(/ERROR: (\d+):(\d+): (.+)/);
    
    let errorMessage = `Shader compilation error:\n${error}`;
    
    if (errorMatch) {
      const lineNum = parseInt(errorMatch[2]);
      const start = Math.max(0, lineNum - 3);
      const end = Math.min(lines.length, lineNum + 2);
      
      errorMessage += '\n\nContext:\n';
      for (let i = start; i < end; i++) {
        const prefix = i === lineNum - 1 ? '>>>' : '   ';
        errorMessage += `${prefix} ${i + 1}: ${lines[i]}\n`;
      }
    }
    
    this.showError(errorMessage);
    console.error(errorMessage);
  }

  handleGracefulDegradation(feature) {
    const warnings = {
      'webgl2': 'WebGL 2.0 not available. Using fallback rendering.',
      'hrtf': 'HRTF not supported. Using stereo panning.',
      'float16': 'Half-float textures not supported. Using lower precision.',
      'instancing': 'Instanced rendering not supported. Using fewer particles.'
    };
    
    const message = warnings[feature] || `Feature "${feature}" not supported.`;
    console.warn(message);
  }

  showError(message) {
    this._errorDisplay.innerHTML = message.replace(/\n/g, '<br>');
    this._errorDisplay.style.display = 'flex';
  }

  hideError() {
    this._errorDisplay.style.display = 'none';
  }

  get contextLost() {
    return this._contextLost;
  }

  set onContextLost(callback) {
    this._onContextLost = callback;
  }

  set onContextRestored(callback) {
    this._onContextRestored = callback;
  }

  destroy() {
    if (this._errorDisplay && this._errorDisplay.parentNode) {
      this._errorDisplay.parentNode.removeChild(this._errorDisplay);
    }
  }
}