import { Clock } from './core/Clock.js';
import { Renderer } from './renderer/Renderer.js';
import { ShaderModule } from './renderer/ShaderModule.js';
import { PostProcessor } from './renderer/PostProcessor.js';
import { CameraManager } from './camera/CameraManager.js';
import { UIManager } from './ui/UIManager.js';
import { AdaptiveQuality } from './utils/AdaptiveQuality.js';
import { Profiler } from './utils/Profiler.js';
import { ParticleRenderer } from './renderer/ParticleRenderer.js';
import { BodyRenderer } from './objects/BodyRenderer.js';
import { LensingPass } from './renderer/LensingPass.js';
import { BackgroundPass } from './renderer/BackgroundPass.js';
import { PhysicsEngine } from './physics/PhysicsEngine.js';
import { TrailRenderer } from './renderer/TrailRenderer.js';
import { AudioEngine } from './audio/AudioEngine.js';
import { SpacetimeHum } from './audio/SpacetimeHum.js';
import { GWSound } from './audio/GWSound.js';
import { EventSounds } from './audio/EventSounds.js';
import { SpatialAudio } from './audio/SpatialAudio.js';
import { TouchControls } from './ui/TouchControls.js';
import { LoadingScreen } from './ui/LoadingScreen.js';
import { ErrorHandler } from './core/ErrorHandler.js';
import { AccessibilityManager } from './ui/AccessibilityManager.js';
import { CinematicPostProcess } from './renderer/CinematicPostProcess.js';

const canvas = document.getElementById('viewport');
const clock = new Clock();
const physics = new PhysicsEngine();

const loadingScreen = new LoadingScreen();
loadingScreen.show();

const errorHandler = new ErrorHandler();

let renderer;
try {
  renderer = await Renderer.create(canvas);
  if (!renderer) {
    loadingScreen.showError('WebGPU and WebGL 2.0 are not supported in this browser.', () => {
      window.location.reload();
    });
    throw new Error('No GPU backend available');
  }
} catch (error) {
  loadingScreen.showError(`Failed to initialize renderer: ${error.message}`, () => {
    window.location.reload();
  });
  throw error;
}

if (renderer.backend === 'webgl2') {
  const fallback = document.createElement('div');
  fallback.style.cssText = 'position:fixed;bottom:10px;left:10px;background:rgba(255,165,0,0.85);color:#fff;padding:8px 14px;z-index:9999;font-size:13px;border-radius:6px;pointer-events:none';
  fallback.textContent = 'WebGPU not available — using WebGL 2.0 fallback.';
  document.body.appendChild(fallback);
  setTimeout(() => fallback.style.opacity = '0', 5000);
}

errorHandler.setupWebGLContextLoss(canvas, renderer);

const profiler = new Profiler();
const quality = new AdaptiveQuality(profiler);
const cameraManager = new CameraManager(canvas);
const shaderModule = new ShaderModule(renderer);

loadingScreen.setProgress(0.3, 'textures');

const lensingPass = new LensingPass(renderer, shaderModule);
const backgroundPass = new BackgroundPass(renderer, shaderModule);
const particleRenderer = new ParticleRenderer(renderer, shaderModule);
const bodyRenderer = new BodyRenderer(renderer, shaderModule);
const trailRenderer = new TrailRenderer(renderer, shaderModule);
const postProcessor = new PostProcessor(renderer, shaderModule);
const cinematicPostProcess = new CinematicPostProcess(renderer, shaderModule);

loadingScreen.setProgress(0.6, 'shaders');

const audioEngine = new AudioEngine();
const spacetimeHum = new SpacetimeHum(audioEngine);
const gwSound = new GWSound(audioEngine);
const eventSounds = new EventSounds(audioEngine);
const spatialAudio = new SpatialAudio(audioEngine);

const touchControls = new TouchControls(canvas, cameraManager);
const accessibilityManager = new AccessibilityManager();

loadingScreen.setProgress(1.0, 'shaders');

const ui = new UIManager({ 
  cameraManager, 
  quality, 
  profiler, 
  physicsEngine: physics,
  audioEngine,
  touchControls,
  accessibilityManager
});

renderer.onResize((w, h) => {
  cameraManager.resize(w, h);
  lensingPass.resize(w, h);
  backgroundPass.resize(w, h);
  particleRenderer.resize(w, h);
  bodyRenderer.resize(w, h);
  trailRenderer.resize(w, h);
  postProcessor.resize(w, h);
  cinematicPostProcess.resize(w, h);
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) clock.reset();
});

function initAudio() {
  if (audioEngine._initialized) return;
  
  audioEngine.init();
  spacetimeHum.start();
  gwSound.start();
  eventSounds.start();
  spatialAudio.start();
  
  audioEngine.muted = false;
  
  ui.updateMuteButton();
}

canvas.addEventListener('click', initAudio, { once: true });
canvas.addEventListener('touchstart', initAudio, { once: true });

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.update();
  if (dt <= 0) return;

  profiler.update(dt);
  quality.update();
  cameraManager.update(dt);
  physics.step(dt);

  const camState = cameraManager.getState();
  const settings = quality.getSettings();
  const display = ui.getDisplaySettings();
  const physState = physics.getState();

  camState.bodies = physState.bodies;
  camState.blackHoles = physState.bodies.filter(b => b.type === 'blackhole');
  camState.time = clock.elapsed;
  camState.gw = physState.gw;
  camState.gwSourcePosition = physState.bodies.filter(b => b.type === 'blackhole')[0]?.position || [0,0,0];
  camState.particleTrails = display.trails ? physState.particleTrails : null;
  camState.particles = physState.gasParticles;

  if (audioEngine._initialized && !audioEngine.muted) {
    try {
      const camPosition = cameraManager.free.getPosition();
      const camVelocity = [0, 0, 0];
      
      spacetimeHum.update(dt, camPosition, physState.bodies);
      gwSound.update(dt, physState.gw.frequency, physState.gw.strain, physState.bhPairs);
      eventSounds.update(dt, physState);
      spatialAudio.update(dt, camPosition, camVelocity, physState.bodies);
    } catch (e) {
      // Audio errors should not break the render loop
    }
  }

  const mergerFlash = computeMergerFlash(physState.bhPairs, physState.bodies);
  postProcessor.setFlashIntensity(mergerFlash);
  postProcessor.updateFlash(dt);

  lensingPass._gwRipplesEnabled = display.gwRipples;

  renderer.beginFrame();

  if (display.stars) backgroundPass.render(camState, settings, clock.elapsed);
  if (display.lensing) {
    lensingPass.render(camState, settings, backgroundPass.texture, clock.elapsed);
  }
  if (display.particles) particleRenderer.render(camState, settings);
  if (display.bodies) bodyRenderer.render(camState, settings);
  if (display.trails) trailRenderer.render(camState, settings);

  if (display.postProcessing) {
    postProcessor.render(settings);
    cinematicPostProcess.render();
  }

  renderer.endFrame();
  ui.updateFPS(profiler.fps);
  ui.update(physState);
  ui.derivePhase(physState);
}

function computeMergerFlash(bhPairs, bodies) {
  if (!bhPairs || bhPairs.length === 0) return 0;
  let maxFlash = 0;
  for (const pair of bhPairs) {
    const bhA = bodies.filter(b => b.type === 'blackhole')[pair.a];
    const bhB = bodies.filter(b => b.type === 'blackhole')[pair.b];
    if (!bhA || !bhB) continue;
    const rs = Math.max(bhA.rs || 1, bhB.rs || 1);
    const threshold = rs * 5;
    if (pair.distance < threshold) {
      const linear = Math.min(1, (threshold - pair.distance) / threshold);
      const flash = linear * linear;
      maxFlash = Math.max(maxFlash, flash);
    }
  }
  return maxFlash;
}

window.addEventListener('beforeunload', () => {
  audioEngine.destroy();
  spacetimeHum.stop();
  gwSound.stop();
  eventSounds.stop();
  spatialAudio.stop();
  touchControls.destroy();
  errorHandler.destroy();
  accessibilityManager.destroy();
  cinematicPostProcess.destroy();
  renderer.destroy();
});

loadingScreen.hide();
clock.reset();
animate();
