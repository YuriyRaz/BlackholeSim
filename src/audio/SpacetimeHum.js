export class SpacetimeHum {
  constructor(audioEngine) {
    this.audioEngine = audioEngine;
    this.oscillators = [];
    this.gainNode = null;
    this.lfo = null;
    this.lfoGain = null;
    this._active = false;
    this._baseFreq = 40;
    this._harmonics = [
      { freq: 40, amplitude: 1.0 },
      { freq: 80, amplitude: 0.5 },
      { freq: 120, amplitude: 0.3 },
      { freq: 160, amplitude: 0.2 }
    ];
    this._lfoFreq = 0.5;
    this._lfoDepth = 0.1;
    this._currentVolume = 0;
    this._targetVolume = 0;
    this._pitchShift = 0;
  }

  start() {
    if (this._active) return;
    if (!this.audioEngine.ctx) return;
    
    const ctx = this.audioEngine.ctx;
    const layerGain = this.audioEngine.getLayerGain('hum');
    
    this.gainNode = ctx.createGain();
    this.gainNode.gain.value = 0;
    this.gainNode.connect(layerGain);
    
    this.lfo = ctx.createOscillator();
    this.lfo.type = 'sine';
    this.lfo.frequency.value = this._lfoFreq;
    
    this.lfoGain = ctx.createGain();
    this.lfoGain.gain.value = this._lfoDepth;
    
    this.lfo.connect(this.lfoGain);
    
    for (const harmonic of this._harmonics) {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = harmonic.freq;
      
      const oscGain = ctx.createGain();
      oscGain.gain.value = harmonic.amplitude;
      
      this.lfoGain.connect(oscGain.gain);
      
      osc.connect(oscGain);
      oscGain.connect(this.gainNode);
      
      this.oscillators.push({ osc, gain: oscGain, baseFreq: harmonic.freq });
      osc.start();
    }
    
    this.lfo.start();
    this._active = true;
  }

  stop() {
    if (!this._active) return;
    
    for (const { osc } of this.oscillators) {
      osc.stop();
      osc.disconnect();
    }
    this.oscillators = [];
    
    if (this.lfo) {
      this.lfo.stop();
      this.lfo.disconnect();
      this.lfo = null;
    }
    
    if (this.lfoGain) {
      this.lfoGain.disconnect();
      this.lfoGain = null;
    }
    
    if (this.gainNode) {
      this.gainNode.disconnect();
      this.gainNode = null;
    }
    
    this._active = false;
  }

  update(dt, cameraPosition, bodies) {
    if (!this._active || !this.audioEngine.ctx) return;
    
    let minDist = Infinity;
    let nearestBH = null;
    
    for (const body of bodies) {
      if (body.type === 'blackhole') {
        const dx = body.position[0] - cameraPosition[0];
        const dy = body.position[1] - cameraPosition[1];
        const dz = body.position[2] - cameraPosition[2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const rs = body.rs || 1;
        const scaledDist = dist / rs;
        
        if (scaledDist < minDist) {
          minDist = scaledDist;
          nearestBH = body;
        }
      }
    }
    
    if (minDist === Infinity) {
      this._targetVolume = 0;
      this._pitchShift = 0;
    } else {
      const volumeCurve = Math.max(0, 1 - (minDist - 10) / 90);
      this._targetVolume = Math.pow(volumeCurve, 2);
      
      if (minDist < 10) {
        this._pitchShift = 0.2;
      } else if (minDist < 100) {
        this._pitchShift = 0.2 * (1 - (minDist - 10) / 90);
      } else {
        this._pitchShift = 0;
      }
    }
    
    this._currentVolume += (this._targetVolume - this._currentVolume) * Math.min(1, dt * 2);
    
    if (this.gainNode) {
      this.gainNode.gain.setTargetAtTime(
        this._currentVolume, 
        this.audioEngine.ctx.currentTime, 
        0.1
      );
    }
    
    const pitchFactor = 1 + this._pitchShift;
    for (const { osc, baseFreq } of this.oscillators) {
      osc.frequency.setTargetAtTime(
        baseFreq * pitchFactor, 
        this.audioEngine.ctx.currentTime, 
        0.1
      );
    }
  }

  setDissonance(bhCount, bhIndex) {
    if (!this._active || bhCount <= 1) return;
    
    const detune = (bhIndex - (bhCount - 1) / 2) * 2;
    for (const { osc, baseFreq } of this.oscillators) {
      osc.detune.setValueAtTime(detune * 100, this.audioEngine.ctx.currentTime);
    }
  }

  reset() {
    this._currentVolume = 0;
    this._targetVolume = 0;
    this._pitchShift = 0;
  }
}