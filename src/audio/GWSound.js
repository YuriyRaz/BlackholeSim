export class GWSound {
  constructor(audioEngine) {
    this.audioEngine = audioEngine;
    this.oscillatorA = null;
    this.oscillatorB = null;
    this.gainNode = null;
    this._active = false;
    this._currentFreq = 0;
    this._targetFreq = 0;
    this._currentStrain = 0;
    this._targetStrain = 0;
    this._inRingdown = false;
    this._ringdownStart = 0;
    this._ringdownDuration = 0.5;
    this._qnmFreq = 250;
    this._minAudibleFreq = 20;
    this._maxAudibleFreq = 500;
    this._detuneOffset = 0.5;
  }

  start() {
    if (this._active) return;
    if (!this.audioEngine.ctx) return;
    
    const ctx = this.audioEngine.ctx;
    const layerGain = this.audioEngine.getLayerGain('gw');
    
    this.gainNode = ctx.createGain();
    this.gainNode.gain.value = 0;
    this.gainNode.connect(layerGain);
    
    this.oscillatorA = ctx.createOscillator();
    this.oscillatorA.type = 'sine';
    this.oscillatorA.frequency.value = this._minAudibleFreq;
    
    this.oscillatorB = ctx.createOscillator();
    this.oscillatorB.type = 'sine';
    this.oscillatorB.frequency.value = this._minAudibleFreq + this._detuneOffset;
    
    this.oscillatorA.connect(this.gainNode);
    this.oscillatorB.connect(this.gainNode);
    
    this.oscillatorA.start();
    this.oscillatorB.start();
    
    this._active = true;
    this._inRingdown = false;
  }

  stop() {
    if (!this._active) return;
    
    if (this.oscillatorA) {
      this.oscillatorA.stop();
      this.oscillatorA.disconnect();
      this.oscillatorA = null;
    }
    
    if (this.oscillatorB) {
      this.oscillatorB.stop();
      this.oscillatorB.disconnect();
      this.oscillatorB = null;
    }
    
    if (this.gainNode) {
      this.gainNode.disconnect();
      this.gainNode = null;
    }
    
    this._active = false;
    this._inRingdown = false;
  }

  update(dt, gwFrequency, gwStrain, bhPairs) {
    if (!this._active || !this.audioEngine.ctx) return;
    
    const hasBinary = bhPairs && bhPairs.length > 0;
    
    if (!hasBinary) {
      this._targetFreq = 0;
      this._targetStrain = 0;
    } else {
      if (this._inRingdown) {
        const elapsed = this.audioEngine.ctx.currentTime - this._ringdownStart;
        const progress = elapsed / this._ringdownDuration;
        
        if (progress >= 1) {
          this._targetFreq = 0;
          this._targetStrain = 0;
          this._inRingdown = false;
        } else {
          this._targetFreq = this._qnmFreq;
          this._targetStrain = this._currentStrain * (1 - progress);
        }
      } else {
        this._targetFreq = this._mapFrequency(gwFrequency);
        this._targetStrain = Math.min(1, gwStrain * 10);
        
        if (gwFrequency > 0 && gwStrain > 0.8) {
          this._inRingdown = true;
          this._ringdownStart = this.audioEngine.ctx.currentTime;
          this._currentStrain = this._targetStrain;
        }
      }
    }
    
    this._currentFreq += (this._targetFreq - this._currentFreq) * Math.min(1, dt * 5);
    this._currentStrain += (this._targetStrain - this._currentStrain) * Math.min(1, dt * 5);
    
    if (this.oscillatorA) {
      this.oscillatorA.frequency.setTargetAtTime(
        this._currentFreq, 
        this.audioEngine.ctx.currentTime, 
        0.05
      );
      this.oscillatorB.frequency.setTargetAtTime(
        this._currentFreq + this._detuneOffset, 
        this.audioEngine.ctx.currentTime, 
        0.05
      );
    }
    
    if (this.gainNode) {
      this.gainNode.gain.setTargetAtTime(
        this._currentStrain, 
        this.audioEngine.ctx.currentTime, 
        0.05
      );
    }
  }

  _mapFrequency(gwFreq) {
    if (gwFreq <= 0) return this._minAudibleFreq;
    
    const logMin = Math.log(this._minAudibleFreq);
    const logMax = Math.log(this._maxAudibleFreq);
    const logFreq = Math.log(Math.max(this._minAudibleFreq, gwFreq));
    
    return Math.exp(logMin + (logFreq - logMin) / (logMax - logMin) * (logMax - logMin));
  }

  reset() {
    this._currentFreq = 0;
    this._targetFreq = 0;
    this._currentStrain = 0;
    this._targetStrain = 0;
    this._inRingdown = false;
  }
}