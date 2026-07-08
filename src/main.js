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

const canvas = document.getElementById('viewport');
const clock = new Clock();

const renderer = await Renderer.create(canvas);
if (!renderer) {
  document.body.innerHTML = '<div style="color:#fff;font-size:24px;text-align:center;margin-top:40vh">WebGPU and WebGL 2.0 are not supported in this browser.</div>';
  throw new Error('No GPU backend available');
}

const profiler = new Profiler();
const quality = new AdaptiveQuality(profiler);
const cameraManager = new CameraManager(canvas);
const shaderModule = new ShaderModule(renderer);

const lensingPass = new LensingPass(renderer, shaderModule);
const backgroundPass = new BackgroundPass(renderer, shaderModule);
const particleRenderer = new ParticleRenderer(renderer, shaderModule);
const bodyRenderer = new BodyRenderer(renderer, shaderModule);
const postProcessor = new PostProcessor(renderer, shaderModule);

const ui = new UIManager({ cameraManager, quality, profiler });

renderer.onResize((w, h) => {
  cameraManager.resize(w, h);
  lensingPass.resize(w, h);
  backgroundPass.resize(w, h);
  particleRenderer.resize(w, h);
  bodyRenderer.resize(w, h);
  postProcessor.resize(w, h);
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) clock.reset();
});

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.update();
  if (dt <= 0) return;

  profiler.update(dt);
  quality.update();
  cameraManager.update(dt);

  const camState = cameraManager.getState();
  const settings = quality.getSettings();
  const display = ui.getDisplaySettings();

  renderer.beginFrame();

  if (display.stars) backgroundPass.render(camState, settings, clock.elapsed);
  if (display.lensing) {
    lensingPass.render(camState, settings, backgroundPass.texture, clock.elapsed);
  }
  if (display.particles) particleRenderer.render(camState, settings);
  if (display.bodies) bodyRenderer.render(camState, settings);

  if (display.postProcessing) {
    postProcessor.render(settings);
  }

  renderer.endFrame();
  ui.updateFPS(profiler.fps);
}

animate();
