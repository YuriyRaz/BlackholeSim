import { describe, expect, it } from 'vitest';
import { BinaryBHPreset, KerrPreset, TDEPreset } from '../src/presets/presets.js';
import { PhysicsEngine } from '../src/physics/PhysicsEngine.js';
import { Constants } from '../src/core/Constants.js';

function normalize(v) {
  const length = Math.hypot(...v);
  return v.map(component => component / length);
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function isBodyInPresetCameraView(body, camera, aspect = 16 / 9) {
  const cosPhi = Math.cos(camera.phi);
  const eye = [
    camera.focus[0] + camera.distance * cosPhi * Math.sin(camera.theta),
    camera.focus[1] + camera.distance * Math.sin(camera.phi),
    camera.focus[2] + camera.distance * cosPhi * Math.cos(camera.theta)
  ];
  const forward = normalize([
    camera.focus[0] - eye[0],
    camera.focus[1] - eye[1],
    camera.focus[2] - eye[2]
  ]);
  const right = normalize(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  const toBody = [
    body.position[0] - eye[0],
    body.position[1] - eye[1],
    body.position[2] - eye[2]
  ];
  const depth = dot(toBody, forward);
  const fovY = 60 * Math.PI / 180;
  const halfHeight = Math.tan(fovY / 2);
  const halfWidth = halfHeight * aspect;
  const radiusMargin = (body.radius || 1) / Math.max(depth, 1);

  const far = Math.max(1e6, camera.distance * 10);

  return depth > 0.1 &&
    depth < far &&
    Math.abs(dot(toBody, right) / depth) <= halfWidth + radiusMargin &&
    Math.abs(dot(toBody, up) / depth) <= halfHeight + radiusMargin;
}

function projectedRadiusPixels(body, camera, viewportHeight = 720) {
  const cosPhi = Math.cos(camera.phi);
  const eye = [
    camera.focus[0] + camera.distance * cosPhi * Math.sin(camera.theta),
    camera.focus[1] + camera.distance * Math.sin(camera.phi),
    camera.focus[2] + camera.distance * cosPhi * Math.cos(camera.theta)
  ];
  const forward = normalize([
    camera.focus[0] - eye[0],
    camera.focus[1] - eye[1],
    camera.focus[2] - eye[2]
  ]);
  const toBody = [
    body.position[0] - eye[0],
    body.position[1] - eye[1],
    body.position[2] - eye[2]
  ];
  const depth = dot(toBody, forward);
  const fovY = 60 * Math.PI / 180;

  return ((body.renderRadius || body.radius || 1) / Math.max(depth, 1)) *
    (viewportHeight / (2 * Math.tan(fovY / 2)));
}

describe('Presets', () => {
  it('starts the binary black holes as dynamic bodies', () => {
    const preset = BinaryBHPreset();
    const blackHoles = preset.bodies.filter(body => body.type === 'blackhole');

    expect(blackHoles).toHaveLength(2);
    expect(blackHoles.every(body => body.fixed === false)).toBe(true);
    expect(blackHoles.some(body => Math.hypot(...body.velocity) > 0)).toBe(true);
  });

  it('moves the binary preset when the physics engine steps', () => {
    const engine = new PhysicsEngine();
    engine.loadPreset(BinaryBHPreset());
    const initialPositions = engine.bodies.map(body => [...body.position]);

    engine.step(0.01);

    expect(engine.bodies.some((body, index) => body.distanceTo({ position: initialPositions[index] }) > 0)).toBe(true);
  });

  it('keeps binary black holes in the preset camera view while the simulation advances', () => {
    const preset = BinaryBHPreset();
    const engine = new PhysicsEngine();
    engine.loadPreset(preset);

    for (let i = 0; i < 200; i++) {
      engine.step(0.01);
    }

    const blackHoles = engine.bodies.filter(body => body.type === 'blackhole');
    expect(blackHoles.every(body => isBodyInPresetCameraView(body, preset.camera))).toBe(true);
  });

  it('keeps central black holes fixed in anchored presets', () => {
    expect(TDEPreset().bodies.find(body => body.type === 'blackhole').fixed).toBe(true);
    expect(KerrPreset().bodies.find(body => body.type === 'blackhole').fixed).toBe(true);
  });

  it('keeps the TDE bodies inside the preset camera clipping range', () => {
    const preset = TDEPreset();

    expect(preset.bodies.every(body => isBodyInPresetCameraView(body, preset.camera))).toBe(true);
    expect(Math.min(...preset.bodies.map(body => projectedRadiusPixels(body, preset.camera)))).toBeGreaterThan(2);
  });

  it('starts TDE at 3x tidal radius with e=0.95 orbit', () => {
    const preset = TDEPreset();
    const blackHole = preset.bodies.find(body => body.type === 'blackhole');
    const star = preset.bodies.find(body => body.type === 'star');
    const separation = Math.hypot(
      star.position[0] - blackHole.position[0],
      star.position[1] - blackHole.position[1],
      star.position[2] - blackHole.position[2]
    );
    const dR = Constants.tidalDisruptionRadius(blackHole.mass, star.radius, star.mass);

    expect(separation).toBeCloseTo(3 * dR, -2);
    expect(preset.matterParticles.length).toBe(1000);
  });

  it('generates polytrope matter particles for TDE preset', () => {
    const preset = TDEPreset();
    expect(preset.matterParticles.length).toBeGreaterThan(0);
    expect(preset.matterParticles[0].phase).toBe('stellar');
    expect(preset.matterParticles[0].mass).toBeCloseTo(1 / 1000, 5);
    expect(preset.matterParticles[0].density).toBeGreaterThan(0);
  });
});
