export class SpatialAudio {
  constructor(audioEngine) {
    this.audioEngine = audioEngine;
    this.panners = new Map();
    this._active = false;
    this._listenerPosition = [0, 0, 0];
    this._listenerVelocity = [0, 0, 0];
    this._dopplerFactor = 0.05;
  }

  start() {
    if (this._active) return;
    this._active = true;
  }

  stop() {
    this._active = false;
    this.clearPanners();
  }

  clearPanners() {
    for (const panner of this.panners.values()) {
      if (panner.node) {
        panner.node.disconnect();
      }
    }
    this.panners.clear();
  }

  createPannerForBody(bodyId) {
    if (!this.audioEngine.ctx) return null;
    
    const existing = this.panners.get(bodyId);
    if (existing) return existing.node;
    
    const panner = this.audioEngine.createPanner();
    const gainNode = this.audioEngine.createGain();
    
    panner.connect(gainNode);
    gainNode.connect(this.audioEngine.compressor);
    
    this.panners.set(bodyId, {
      node: panner,
      gain: gainNode,
      lastPosition: [0, 0, 0],
      lastVelocity: [0, 0, 0]
    });
    
    return panner;
  }

  removePannerForBody(bodyId) {
    const panner = this.panners.get(bodyId);
    if (panner) {
      if (panner.node) panner.node.disconnect();
      if (panner.gain) panner.gain.disconnect();
      this.panners.delete(bodyId);
    }
  }

  update(dt, cameraPosition, cameraVelocity, bodies) {
    if (!this._active || !this.audioEngine.ctx) return;
    
    this._listenerPosition = [...cameraPosition];
    this._listenerVelocity = [...cameraVelocity];
    
    if (this.audioEngine.ctx.listener.positionX) {
      this.audioEngine.ctx.listener.positionX.value = cameraPosition[0];
      this.audioEngine.ctx.listener.positionY.value = cameraPosition[1];
      this.audioEngine.ctx.listener.positionZ.value = cameraPosition[2];
    } else {
      this.audioEngine.ctx.listener.setPosition(
        cameraPosition[0], 
        cameraPosition[1], 
        cameraPosition[2]
      );
    }
    
    for (const body of bodies) {
      if (body.type !== 'blackhole') continue;
      
      let pannerData = this.panners.get(body.id);
      if (!pannerData) {
        this.createPannerForBody(body.id);
        pannerData = this.panners.get(body.id);
        if (!pannerData) continue;
      }
      
      const panner = pannerData.node;
      
      if (panner.positionX) {
        panner.positionX.value = body.position[0];
        panner.positionY.value = body.position[1];
        panner.positionZ.value = body.position[2];
      } else {
        panner.setPosition(
          body.position[0], 
          body.position[1], 
          body.position[2]
        );
      }
      
      const dx = body.position[0] - cameraPosition[0];
      const dy = body.position[1] - cameraPosition[1];
      const dz = body.position[2] - cameraPosition[2];
      const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
      
      const gain = 1 / (1 + distance * distance);
      pannerData.gain.gain.setTargetAtTime(
        Math.min(1, gain), 
        this.audioEngine.ctx.currentTime, 
        0.1
      );
      
      const vx = body.velocity ? body.velocity[0] : 0;
      const vy = body.velocity ? body.velocity[1] : 0;
      const vz = body.velocity ? body.velocity[2] : 0;
      
      const relVx = vx - cameraVelocity[0];
      const relVy = vy - cameraVelocity[1];
      const relVz = vz - cameraVelocity[2];
      
      const approachSpeed = -(relVx * dx + relVy * dy + relVz * dz) / (distance || 1);
      const dopplerShift = 1 + approachSpeed * this._dopplerFactor;
      
      pannerData.lastPosition = [...body.position];
      pannerData.lastVelocity = [vx, vy, vz];
    }
  }

  setDopplerFactor(factor) {
    this._dopplerFactor = factor;
  }

  reset() {
    this.clearPanners();
  }
}