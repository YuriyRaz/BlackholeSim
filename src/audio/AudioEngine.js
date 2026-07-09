export class AudioEngine {
  constructor() {
    this.ctx = null;
    this.masterGain = null;
    this.compressor = null;
    this.layers = {
      hum: { gain: null, muted: false, volume: 1.0 },
      gw: { gain: null, muted: false, volume: 1.0 },
      events: { gain: null, muted: false, volume: 1.0 }
    };
    this._initialized = false;
    this._muted = true;
    this._volume = 1.0;
    this._loadMuteState();
  }

  _loadMuteState() {
    const saved = localStorage.getItem('blackhole-audio-muted');
    if (saved !== null) {
      this._muted = saved === 'true';
    }
  }

  _saveMuteState() {
    localStorage.setItem('blackhole-audio-muted', this._muted.toString());
  }

  init() {
    if (this._initialized) return;
    
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.ctx.suspend();
    
    this.compressor = this.ctx.createDynamicsCompressor();
    this.compressor.threshold.value = -24;
    this.compressor.knee.value = 30;
    this.compressor.ratio.value = 12;
    this.compressor.attack.value = 0.003;
    this.compressor.release.value = 0.25;
    
    this.masterGain = this.ctx.createGain();
    this.masterGain.gain.value = this._muted ? 0 : this._volume;
    
    this.compressor.connect(this.masterGain);
    this.masterGain.connect(this.ctx.destination);
    
    for (const [name, layer] of Object.entries(this.layers)) {
      layer.gain = this.ctx.createGain();
      layer.gain.gain.value = layer.muted ? 0 : layer.volume;
      layer.gain.connect(this.compressor);
    }
    
    this._initialized = true;
  }

  resume() {
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  suspend() {
    if (this.ctx && this.ctx.state === 'running') {
      this.ctx.suspend();
    }
  }

  get muted() { return this._muted; }
  set muted(val) {
    this._muted = val;
    this._saveMuteState();
    if (this.masterGain) {
      this.masterGain.gain.setTargetAtTime(
        val ? 0 : this._volume, 
        this.ctx.currentTime, 
        0.05
      );
    }
  }

  get volume() { return this._volume; }
  set volume(val) {
    this._volume = Math.max(0, Math.min(1, val));
    if (this.masterGain && !this._muted) {
      this.masterGain.gain.setTargetAtTime(
        this._volume, 
        this.ctx.currentTime, 
        0.05
      );
    }
  }

  setLayerVolume(layerName, volume) {
    const layer = this.layers[layerName];
    if (!layer) return;
    layer.volume = Math.max(0, Math.min(1, volume));
    if (layer.gain && !layer.muted) {
      layer.gain.gain.setTargetAtTime(
        layer.volume, 
        this.ctx.currentTime, 
        0.05
      );
    }
  }

  setLayerMuted(layerName, muted) {
    const layer = this.layers[layerName];
    if (!layer) return;
    layer.muted = muted;
    if (layer.gain) {
      layer.gain.gain.setTargetAtTime(
        muted ? 0 : layer.volume, 
        this.ctx.currentTime, 
        0.05
      );
    }
  }

  getLayerGain(layerName) {
    return this.layers[layerName]?.gain;
  }

  createOscillator(type = 'sine') {
    if (!this.ctx) return null;
    return this.ctx.createOscillator();
  }

  createGain() {
    if (!this.ctx) return null;
    return this.ctx.createGain();
  }

  createBiquadFilter() {
    if (!this.ctx) return null;
    return this.ctx.createBiquadFilter();
  }

  createBufferSource() {
    if (!this.ctx) return null;
    return this.ctx.createBufferSource();
  }

  createPanner() {
    if (!this.ctx) return null;
    const panner = this.ctx.createPanner();
    panner.panningModel = 'HRTF';
    panner.distanceModel = 'inverse';
    panner.refDistance = 1;
    panner.maxDistance = 1000;
    panner.rolloffFactor = 1;
    panner.coneInnerAngle = 360;
    panner.coneOuterAngle = 0;
    panner.coneOuterGain = 0;
    return panner;
  }

  createWhiteNoise(duration = 1) {
    if (!this.ctx) return null;
    const sampleRate = this.ctx.sampleRate;
    const length = sampleRate * duration;
    const buffer = this.ctx.createBuffer(1, length, sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) {
      data[i] = Math.random() * 2 - 1;
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    return source;
  }

  reset() {
    for (const layer of Object.values(this.layers)) {
      if (layer.gain) {
        layer.gain.gain.cancelScheduledValues(this.ctx.currentTime);
        layer.gain.gain.setValueAtTime(0, this.ctx.currentTime);
      }
    }
  }

  destroy() {
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
    }
    this._initialized = false;
  }
}