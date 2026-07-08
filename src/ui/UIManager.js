import { PresetSelector } from './PresetSelector.js';
import { PhysicsInfo } from './PhysicsInfo.js';
import { DisplayToggles } from './DisplayToggles.js';
import { QualitySelector } from './QualitySelector.js';
import { KeyboardShortcuts } from './KeyboardShortcuts.js';
import { PhaseIndicator } from './PhaseIndicator.js';
import { CameraModeToggle } from './CameraModeToggle.js';
import { StarCountControl } from './StarCountControl.js';

export class UIManager {
  constructor({ cameraManager, quality, profiler }) {
    this.cameraManager = cameraManager;
    this.quality = quality;
    this.profiler = profiler;
    this._displaySettings = {
      lensing: true, particles: true, stars: true, bodies: true,
      jets: true, gwRipples: true, trails: true, postProcessing: true
    };

    this._presetSelector = new PresetSelector(cameraManager);
    this._physicsInfo = new PhysicsInfo();
    this._displayToggles = new DisplayToggles(this._displaySettings);
    this._qualitySelector = new QualitySelector(quality);
    this._keyboardShortcuts = new KeyboardShortcuts();
    this._phaseIndicator = new PhaseIndicator();
    this._cameraModeToggle = new CameraModeToggle(cameraManager);
    this._starCountControl = new StarCountControl(quality);

    this._createCSS();
    this._createLayout();
    this._createMuteButton();
  }

  _createCSS() {
    const style = document.createElement('style');
    style.textContent = `
      .ui-panel { position: absolute; color: #eee; font-family: monospace; font-size: 12px;
        background: rgba(0,0,0,0.7); border-radius: 6px; padding: 8px 12px; pointer-events: auto; }
      .ui-top { top: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
      .ui-left { top: 60px; left: 10px; }
      .ui-right { top: 60px; right: 10px; }
      .ui-bottom { bottom: 10px; right: 10px; }
      .ui-btn { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
        color: #eee; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-family: monospace; font-size: 11px; }
      .ui-btn:hover { background: rgba(255,255,255,0.2); }
      .ui-btn.active { background: rgba(100,150,255,0.4); border-color: rgba(100,150,255,0.8); }
      .ui-toggle { display: flex; align-items: center; gap: 6px; margin: 3px 0; cursor: pointer; }
      .ui-toggle input { accent-color: #6af; }
      .ui-label { font-size: 11px; color: #aaa; }
      .mute-btn { position: absolute; bottom: 10px; left: 10px; }
      @media (max-width: 1024px) {
        .ui-btn { padding: 4px 6px; font-size: 10px; }
        .ui-label { display: none; }
      }
    `;
    document.head.appendChild(style);
  }

  _createLayout() {
    const app = document.getElementById('app');
    this._topPanel = document.createElement('div');
    this._topPanel.className = 'ui-panel ui-top';
    app.appendChild(this._topPanel);

    this._leftPanel = document.createElement('div');
    this._leftPanel.className = 'ui-panel ui-left';
    app.appendChild(this._leftPanel);

    this._rightPanel = document.createElement('div');
    this._rightPanel.className = 'ui-panel ui-right';
    app.appendChild(this._rightPanel);

    this._bottomPanel = document.createElement('div');
    this._bottomPanel.className = 'ui-panel ui-bottom';
    app.appendChild(this._bottomPanel);

    this._presetSelector.mount(this._topPanel);
    this._physicsInfo.mount(this._leftPanel);
    this._phaseIndicator.mount(this._leftPanel);
    this._displayToggles.mount(this._rightPanel);
    this._qualitySelector.mount(this._rightPanel);
    this._starCountControl.mount(this._rightPanel);
    this._cameraModeToggle.mount(this._rightPanel);
  }

  _createMuteButton() {
    const app = document.getElementById('app');
    const btn = document.createElement('button');
    btn.className = 'ui-btn mute-btn';
    btn.textContent = '🔊';
    btn.title = 'Mute (audio not implemented)';
    app.appendChild(btn);
  }

  getDisplaySettings() { return this._displaySettings; }

  updateFPS(fps) {
    this._physicsInfo.updateFPS(fps);
  }

  setPhase(phase) {
    this._phaseIndicator.setPhase(phase);
  }
}
