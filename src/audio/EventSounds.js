export class EventSounds {
  constructor(audioEngine) {
    this.audioEngine = audioEngine;
    this.gainNode = null;
    this._active = false;
    this._disruptedBodies = new Set();
    this._mergedPairs = new Set();
    this._accretionActive = false;
    this._accretionGain = null;
    this._accretionSource = null;
  }

  start() {
    if (this._active) return;
    if (!this.audioEngine.ctx) return;
    
    const ctx = this.audioEngine.ctx;
    const layerGain = this.audioEngine.getLayerGain('events');
    
    this.gainNode = ctx.createGain();
    this.gainNode.gain.value = 1;
    this.gainNode.connect(layerGain);
    
    this._active = true;
  }

  stop() {
    if (!this._active) return;
    
    this._stopAccretion();
    
    if (this.gainNode) {
      this.gainNode.disconnect();
      this.gainNode = null;
    }
    
    this._active = false;
    this._disruptedBodies.clear();
    this._mergedPairs.clear();
  }

  update(dt, physicsState) {
    if (!this._active || !this.audioEngine.ctx) return;
    
    for (const body of physicsState.bodies) {
      if (body.disrupted && !this._disruptedBodies.has(body.id)) {
        this._disruptedBodies.add(body.id);
        this._playDisruptionCrackle();
      }
    }
    
    if (physicsState.bhPairs) {
      for (const pair of physicsState.bhPairs) {
        const pairKey = `${pair.a}-${pair.b}`;
        if (!this._mergedPairs.has(pairKey)) {
          const bhA = physicsState.bodies.filter(b => b.type === 'blackhole')[pair.a];
          const bhB = physicsState.bodies.filter(b => b.type === 'blackhole')[pair.b];
          if (bhA && bhB) {
            const rs = Math.max(bhA.rs || 1, bhB.rs || 1);
            if (pair.distance < rs * 5) {
              this._mergedPairs.add(pairKey);
              this._playMergerImpact();
            }
          }
        }
      }
    }
    
    const hasAccretion = physicsState.accretionRate > 0;
    if (hasAccretion && !this._accretionActive) {
      this._startAccretion(physicsState.accretionRate);
    } else if (!hasAccretion && this._accretionActive) {
      this._stopAccretion();
    } else if (this._accretionActive) {
      this._updateAccretion(physicsState.accretionRate);
    }
  }

  _playDisruptionCrackle() {
    const ctx = this.audioEngine.ctx;
    const now = ctx.currentTime;
    
    const noise = this.audioEngine.createWhiteNoise(1);
    const filter = this.audioEngine.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = 2000;
    filter.Q.value = 2;
    
    const gain = this.audioEngine.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.3, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 1);
    
    noise.connect(filter);
    filter.connect(gain);
    gain.connect(this.gainNode);
    
    noise.start(now);
    noise.stop(now + 1);
  }

  _playMergerImpact() {
    const ctx = this.audioEngine.ctx;
    const now = ctx.currentTime;
    
    const noise = this.audioEngine.createWhiteNoise(2);
    const filter = this.audioEngine.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 100;
    filter.Q.value = 1;
    
    const gain = this.audioEngine.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.5, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 2);
    
    const reverb = this.audioEngine.createBiquadFilter();
    reverb.type = 'lowpass';
    reverb.frequency.value = 500;
    
    noise.connect(filter);
    filter.connect(gain);
    gain.connect(reverb);
    reverb.connect(this.gainNode);
    
    noise.start(now);
    noise.stop(now + 2);
  }

  _startAccretion(rate) {
    const ctx = this.audioEngine.ctx;
    
    this._accretionSource = this.audioEngine.createWhiteNoise(10);
    this._accretionSource.loop = true;
    
    const filter = this.audioEngine.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 200;
    filter.Q.value = 1;
    
    this._accretionGain = this.audioEngine.createGain();
    this._accretionGain.gain.value = 0;
    
    this._accretionSource.connect(filter);
    filter.connect(this._accretionGain);
    this._accretionGain.connect(this.gainNode);
    
    this._accretionSource.start();
    this._accretionActive = true;
    
    this._updateAccretion(rate);
  }

  _updateAccretion(rate) {
    if (!this._accretionGain) return;
    
    const targetGain = Math.min(0.2, rate * 0.1);
    this._accretionGain.gain.setTargetAtTime(
      targetGain, 
      this.audioEngine.ctx.currentTime, 
      0.1
    );
  }

  _stopAccretion() {
    if (this._accretionSource) {
      this._accretionSource.stop();
      this._accretionSource.disconnect();
      this._accretionSource = null;
    }
    
    if (this._accretionGain) {
      this._accretionGain.disconnect();
      this._accretionGain = null;
    }
    
    this._accretionActive = false;
  }

  reset() {
    this._disruptedBodies.clear();
    this._mergedPairs.clear();
    this._stopAccretion();
  }
}