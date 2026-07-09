import { PresetSelector } from './PresetSelector.js';
import { PhysicsInfo } from './PhysicsInfo.js';
import { DisplayToggles } from './DisplayToggles.js';
import { QualitySelector } from './QualitySelector.js';
import { KeyboardShortcuts } from './KeyboardShortcuts.js';
import { PhaseIndicator } from './PhaseIndicator.js';
import { CameraModeToggle } from './CameraModeToggle.js';
import { StarCountControl } from './StarCountControl.js';
import { TimeControl } from './TimeControl.js';
import { ObjectList } from './ObjectList.js';

export class UIManager {
  constructor({ cameraManager, quality, profiler, physicsEngine }) {
    this.cameraManager = cameraManager;
    this.quality = quality;
    this.profiler = profiler;
    this.physics = physicsEngine;
    this._selectedBody = null;
    this._displaySettings = {
      lensing: true, particles: true, stars: true, bodies: true,
      jets: true, gwRipples: true, trails: true, postProcessing: true
    };

    this._presetSelector = new PresetSelector(cameraManager, physicsEngine);
    this._physicsInfo = new PhysicsInfo();
    this._displayToggles = new DisplayToggles(this._displaySettings);
    this._qualitySelector = new QualitySelector(quality);
    this._keyboardShortcuts = new KeyboardShortcuts();
    this._phaseIndicator = new PhaseIndicator();
    this._cameraModeToggle = new CameraModeToggle(cameraManager);
    this._starCountControl = new StarCountControl(quality);
    this._timeControl = new TimeControl(physicsEngine);
    this._objectList = new ObjectList(cameraManager);

    this._createCSS();
    this._createLayout();
    this._createMuteButton();
    this._setupClickHandler();
  }

  _createCSS() {
    const style = document.createElement('style');
    style.textContent = `
      .ui-panel { position: absolute; color: #eee; font-family: monospace; font-size: 12px;
        background: rgba(0,0,0,0.7); border-radius: 6px; padding: 8px 12px; pointer-events: auto; }
      .ui-top { top: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
      .ui-left { top: 60px; left: 10px; }
      .ui-right { top: 60px; right: 10px; }
      .ui-bottom { bottom: 10px; left: 10px; right: 10px; }
      .ui-btn { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
        color: #eee; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-family: monospace; font-size: 11px; }
      .ui-btn:hover { background: rgba(255,255,255,0.2); }
      .ui-btn.active { background: rgba(100,150,255,0.4); border-color: rgba(100,150,255,0.8); }
      .ui-toggle { display: flex; align-items: center; gap: 6px; margin: 3px 0; cursor: pointer; }
      .ui-toggle input { accent-color: #6af; }
      .ui-label { font-size: 11px; color: #aaa; }
      .mute-btn { position: absolute; bottom: 60px; left: 10px; }
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
    this._objectList.mount(this._leftPanel);
    this._phaseIndicator.mount(this._leftPanel);
    this._displayToggles.mount(this._rightPanel);
    this._qualitySelector.mount(this._rightPanel);
    this._starCountControl.mount(this._rightPanel);
    this._cameraModeToggle.mount(this._rightPanel);
    this._timeControl.mount(this._bottomPanel);

    this._objectList.onSelect = (body) => {
      this._selectedBody = body;
      this._physicsInfo.setSelectedBody(body);
      this.cameraManager.transitionTo(
        this.cameraManager.free.theta,
        this.cameraManager.free.phi,
        body.radius * 15,
        [...body.position]
      );
    };
  }

  _createMuteButton() {
    const app = document.getElementById('app');
    const btn = document.createElement('button');
    btn.className = 'ui-btn mute-btn';
    btn.textContent = '🔊';
    btn.title = 'Mute (audio not implemented)';
    app.appendChild(btn);
  }

  _setupClickHandler() {
    const canvas = document.getElementById('viewport');
    if (!canvas) return;
    let hoverTimeout = null;
    let tooltip = null;

    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const screenX = (e.clientX - rect.left) / rect.width;
      const screenY = (e.clientY - rect.top) / rect.height;
      const ray = this.cameraManager.screenToWorldRay(screenX, screenY);
      const state = this.physics.getState();
      const hit = this.cameraManager.pickObject(ray, state.bodies);
      
      for (const body of this.physics.bodies) {
        body.selected = false;
      }
      
      if (hit) {
        this._selectedBody = hit;
        const body = this.physics.bodies.find(b => b.id === hit.id);
        if (body) body.selected = true;
        this._physicsInfo.setSelectedBody(hit);
        this.cameraManager.transitionTo(
          this.cameraManager.free.theta,
          this.cameraManager.free.phi,
          hit.radius * 15,
          [...hit.position]
        );
      } else {
        this._selectedBody = null;
        this._physicsInfo.setSelectedBody(null);
        this._objectList.deselect();
      }
    });

    canvas.addEventListener('mousemove', (e) => {
      if (hoverTimeout) clearTimeout(hoverTimeout);
      if (tooltip) { tooltip.remove(); tooltip = null; }
      hoverTimeout = setTimeout(() => {
        const rect = canvas.getBoundingClientRect();
        const screenX = (e.clientX - rect.left) / rect.width;
        const screenY = (e.clientY - rect.top) / rect.height;
        const ray = this.cameraManager.screenToWorldRay(screenX, screenY);
        const state = this.physics.getState();
        const hit = this.cameraManager.pickObject(ray, state.bodies);
        if (hit) {
          tooltip = document.createElement('div');
          tooltip.style.cssText = `position:fixed;left:${e.clientX + 10}px;top:${e.clientY - 30}px;background:rgba(0,0,0,0.85);color:#eee;padding:4px 8px;border-radius:4px;font:11px monospace;pointer-events:none;z-index:1000;`;
          tooltip.innerHTML = `<b>${hit.name}</b><br>${hit.type} | ${hit.mass.toFixed(2)} M☉`;
          document.body.appendChild(tooltip);
        }
      }, 500);
    });

    canvas.addEventListener('mouseleave', () => {
      if (hoverTimeout) clearTimeout(hoverTimeout);
      if (tooltip) { tooltip.remove(); tooltip = null; }
    });
  }

  getDisplaySettings() { return this._displaySettings; }
  getSelectedBody() { return this._selectedBody; }

  updateFPS(fps) {
    this._physicsInfo.updateFPS(fps);
  }

  update(state) {
    this._physicsInfo.update(state);
    this._timeControl.update();
    this._objectList.update(state.bodies);
  }

  derivePhase(state) {
    this._phaseIndicator.derivePhase(state);
  }

  setPhase(phase) {
    this._phaseIndicator.setPhase(phase);
  }
}
