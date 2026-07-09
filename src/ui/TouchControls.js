export class TouchControls {
  constructor(canvas, cameraManager) {
    this.canvas = canvas;
    this.cameraManager = cameraManager;
    this._active = false;
    this._touches = new Map();
    this._lastTapTime = 0;
    this._lastTapPos = null;
    this._pinchStartDist = 0;
    this._pinchStartZoom = 0;
    this._panStartPos = null;
    this._orbitStartPos = null;
    this._feedbackElement = null;
    
    this._setupEventListeners();
  }

  _setupEventListeners() {
    this.canvas.style.touchAction = 'none';
    
    this.canvas.addEventListener('touchstart', this._onTouchStart.bind(this), { passive: false });
    this.canvas.addEventListener('touchmove', this._onTouchMove.bind(this), { passive: false });
    this.canvas.addEventListener('touchend', this._onTouchEnd.bind(this), { passive: false });
    this.canvas.addEventListener('touchcancel', this._onTouchEnd.bind(this), { passive: false });
    
    this._createFeedbackElement();
  }

  _createFeedbackElement() {
    this._feedbackElement = document.createElement('div');
    this._feedbackElement.style.cssText = `
      position: fixed;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.3);
      pointer-events: none;
      z-index: 1000;
      opacity: 0;
      transition: opacity 0.2s;
      transform: translate(-50%, -50%);
    `;
    document.body.appendChild(this._feedbackElement);
  }

  _showFeedback(x, y) {
    this._feedbackElement.style.left = `${x}px`;
    this._feedbackElement.style.top = `${y}px`;
    this._feedbackElement.style.opacity = '1';
    
    setTimeout(() => {
      this._feedbackElement.style.opacity = '0';
    }, 200);
  }

  _onTouchStart(e) {
    e.preventDefault();
    
    for (const touch of e.changedTouches) {
      this._touches.set(touch.identifier, {
        x: touch.clientX,
        y: touch.clientY,
        startX: touch.clientX,
        startY: touch.clientY,
        timestamp: Date.now()
      });
    }
    
    if (this._touches.size === 1) {
      const touch = e.changedTouches[0];
      this._showFeedback(touch.clientX, touch.clientY);
      this._orbitStartPos = { x: touch.clientX, y: touch.clientY };
    }
    
    if (this._touches.size === 2) {
      const touches = Array.from(this._touches.values());
      this._pinchStartDist = this._getDistance(touches[0], touches[1]);
      this._panStartPos = {
        x: (touches[0].x + touches[1].x) / 2,
        y: (touches[0].y + touches[1].y) / 2
      };
    }
  }

  _onTouchMove(e) {
    e.preventDefault();
    
    for (const touch of e.changedTouches) {
      const prev = this._touches.get(touch.identifier);
      if (prev) {
        this._touches.set(touch.identifier, {
          ...prev,
          x: touch.clientX,
          y: touch.clientY
        });
      }
    }
    
    if (this._touches.size === 1 && this._orbitStartPos) {
      const touch = Array.from(this._touches.values())[0];
      const dx = touch.x - this._orbitStartPos.x;
      const dy = touch.y - this._orbitStartPos.y;
      
      this.cameraManager.free.theta -= dx * 0.005;
      this.cameraManager.free.phi = Math.max(
        -Math.PI / 2 + 0.1, 
        Math.min(Math.PI / 2 - 0.1, this.cameraManager.free.phi - dy * 0.005)
      );
      
      this._orbitStartPos = { x: touch.x, y: touch.y };
    }
    
    if (this._touches.size === 2 && this._panStartPos) {
      const touches = Array.from(this._touches.values());
      const currentDist = this._getDistance(touches[0], touches[1]);
      const currentMid = {
        x: (touches[0].x + touches[1].x) / 2,
        y: (touches[0].y + touches[1].y) / 2
      };
      
      const pinchDelta = currentDist / this._pinchStartDist;
      this.cameraManager.free.targetDistance /= pinchDelta;
      this._pinchStartDist = currentDist;
      
      const panDx = currentMid.x - this._panStartPos.x;
      const panDy = currentMid.y - this._panStartPos.y;
      
      const panSpeed = this.cameraManager.free.distance * 0.001;
      this.cameraManager.free.targetFocus[0] -= panDx * panSpeed;
      this.cameraManager.free.targetFocus[1] += panDy * panSpeed;
      
      this._panStartPos = currentMid;
    }
  }

  _onTouchEnd(e) {
    for (const touch of e.changedTouches) {
      const touchData = this._touches.get(touch.identifier);
      if (touchData) {
        const timeSinceStart = Date.now() - touchData.timestamp;
        const distance = this._getDistance(
          { x: touchData.startX, y: touchData.startY },
          { x: touch.clientX, y: touch.clientY }
        );
        
        if (timeSinceStart < 300 && distance < 10) {
          const now = Date.now();
          const timeSinceLastTap = now - this._lastTapTime;
          
          if (timeSinceLastTap < 300 && this._lastTapPos) {
            const tapDistance = this._getDistance(
              this._lastTapPos,
              { x: touch.clientX, y: touch.clientY }
            );
            
            if (tapDistance < 50) {
              this._handleDoubleTap(touch.clientX, touch.clientY);
            }
          }
          
          this._lastTapTime = now;
          this._lastTapPos = { x: touch.clientX, y: touch.clientY };
        }
        
        this._touches.delete(touch.identifier);
      }
    }
    
    if (this._touches.size === 0) {
      this._orbitStartPos = null;
      this._panStartPos = null;
    }
  }

  _handleDoubleTap(x, y) {
    const rect = this.canvas.getBoundingClientRect();
    const screenX = (x - rect.left) / rect.width;
    const screenY = (y - rect.top) / rect.height;
    
    const ray = this.cameraManager.screenToWorldRay(screenX, screenY);
    const state = { bodies: [] };
    
    const hit = this.cameraManager.pickObject(ray, state.bodies);
    
    if (hit) {
      this.cameraManager.transitionTo(
        this.cameraManager.free.theta,
        this.cameraManager.free.phi,
        hit.radius * 15,
        [...hit.position]
      );
    }
  }

  _getDistance(touch1, touch2) {
    const dx = touch1.x - touch2.x;
    const dy = touch1.y - touch2.y;
    return Math.sqrt(dx * dx + dy * dy);
  }

  destroy() {
    this.canvas.removeEventListener('touchstart', this._onTouchStart);
    this.canvas.removeEventListener('touchmove', this._onTouchMove);
    this.canvas.removeEventListener('touchend', this._onTouchEnd);
    this.canvas.removeEventListener('touchcancel', this._onTouchEnd);
    
    if (this._feedbackElement) {
      this._feedbackElement.remove();
    }
  }
}