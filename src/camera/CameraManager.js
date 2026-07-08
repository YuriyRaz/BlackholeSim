import { FreeCamera } from './FreeCamera.js';
import { CinematicCamera } from './CinematicCamera.js';

export class CameraManager {
  constructor(canvas) {
    this.free = new FreeCamera(canvas);
    this.cinematic = new CinematicCamera();
    this._mode = 'free';
    this._transitioning = false;
    this._transitionProgress = 0;
    this._transitionDuration = 1.5;
    this._transitionStart = null;
    this._transitionFrom = null;
    this._transitionTo = null;
    this._viewProjection = new Float32Array(16);
    this._perspective = new Float32Array(16);
    this._aspect = canvas.width / canvas.height || 1;
  }

  get mode() { return this._mode; }

  update(dt) {
    if (this._transitioning) {
      this._transitionProgress += dt / this._transitionDuration;
      if (this._transitionProgress >= 1) {
        this._transitionProgress = 1;
        this._transitioning = false;
        this.free.theta = this._transitionTo.theta;
        this.free.phi = this._transitionTo.phi;
        this.free.distance = this._transitionTo.distance;
        this.free.focusPoint = [...this._transitionTo.focus];
        this.free.targetTheta = this.free.theta;
        this.free.targetPhi = this.free.phi;
        this.free.targetDistance = this.free.distance;
        this.free.targetFocus = [...this.free.focusPoint];
      } else {
        const t = this._easeInOut(this._transitionProgress);
        this.free.theta = this._lerp(this._transitionFrom.theta, this._transitionTo.theta, t);
        this.free.phi = this._lerp(this._transitionFrom.phi, this._transitionTo.phi, t);
        this.free.distance = this._lerp(this._transitionFrom.distance, this._transitionTo.distance, t);
        this.free.focusPoint[0] = this._lerp(this._transitionFrom.focus[0], this._transitionTo.focus[0], t);
        this.free.focusPoint[1] = this._lerp(this._transitionFrom.focus[1], this._transitionTo.focus[1], t);
        this.free.focusPoint[2] = this._lerp(this._transitionFrom.focus[2], this._transitionTo.focus[2], t);
      }
      return;
    }

    if (this._mode === 'cinematic') {
      this.cinematic.update(dt);
      this.free.theta = this.cinematic.theta;
      this.free.phi = this.cinematic.phi;
      this.free.distance = this.cinematic.distance;
      this.free.focusPoint = [...this.cinematic.focusPoint];
    } else {
      this.free.update(dt);
    }
  }

  setMode(mode) {
    this._mode = mode;
    if (mode === 'cinematic') {
      this.cinematic.theta = this.free.theta;
      this.cinematic.phi = this.free.phi;
      this.cinematic.distance = this.free.distance;
      this.cinematic.focusPoint = [...this.free.focusPoint];
      this.cinematic.enable();
    } else {
      this.cinematic.disable();
    }
  }

  transitionTo(theta, phi, distance, focus) {
    this._transitioning = true;
    this._transitionProgress = 0;
    this._transitionFrom = {
      theta: this.free.theta,
      phi: this.free.phi,
      distance: this.free.distance,
      focus: [...this.free.focusPoint]
    };
    this._transitionTo = { theta, phi, distance, focus: focus || [...this.free.focusPoint] };
  }

  setPreset(preset) {
    const presets = {
      cinematic: { theta: 0, phi: Math.PI / 6, distance: 150, focus: [0, 0, 0] },
      topdown: { theta: 0, phi: 85 * Math.PI / 180, distance: 200, focus: [0, 0, 0] },
      edgeon: { theta: 0, phi: 0, distance: 200, focus: [0, 0, 0] },
      closeup: { theta: 0, phi: Math.PI / 6, distance: 10, focus: [0, 0, 0] },
      system: { theta: 0, phi: Math.PI / 6, distance: 2000, focus: [0, 0, 0] }
    };
    const p = presets[preset];
    if (p) this.transitionTo(p.theta, p.phi, p.distance, p.focus);
  }

  reset() { this.transitionTo(0, Math.PI / 4, 100, [0, 0, 0]); }

  getState() {
    const pos = this.free.getPosition();
    const dir = this.free.getDirection();
    const n = this._normalize(dir);
    this._updateVP(pos, n);
    return {
      position: pos,
      direction: n,
      viewProjection: this._viewProjection,
      focus: [...this.free.focusPoint]
    };
  }

  _normalize(v) {
    const l = Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);
    return l > 0 ? [v[0]/l, v[1]/l, v[2]/l] : [0, 0, 1];
  }

  _updateVP(eye, dir) {
    const fov = 60 * Math.PI / 180;
    const near = 0.1;
    const far = 1e6;
    const f = 1 / Math.tan(fov / 2);
    const aspect = this._aspect;
    const right = this._cross(dir, [0, 1, 0]);
    const rLen = Math.sqrt(right[0]*right[0]+right[1]*right[1]+right[2]*right[2]);
    const r = rLen > 0 ? [right[0]/rLen, right[1]/rLen, right[2]/rLen] : [1, 0, 0];
    const up = this._cross(r, dir);
    const uLen = Math.sqrt(up[0]*up[0]+up[1]*up[1]+up[2]*up[2]);
    const u = uLen > 0 ? [up[0]/uLen, up[1]/uLen, up[2]/uLen] : [0, 1, 0];

    const p = this._perspective;
    p[0] = f/aspect; p[1]=0; p[2]=0; p[3]=0;
    p[4]=0; p[5]=f; p[6]=0; p[7]=0;
    p[8]=0; p[9]=0; p[10]=(far+near)/(near-far); p[11]=-1;
    p[12]=0; p[13]=0; p[14]=(2*far*near)/(near-far); p[15]=0;

    const m = this._viewProjection;
    m[0]=r[0]; m[1]=u[0]; m[2]=-dir[0]; m[3]=0;
    m[4]=r[1]; m[5]=u[1]; m[6]=-dir[1]; m[7]=0;
    m[8]=r[2]; m[9]=u[2]; m[10]=-dir[2]; m[11]=0;
    m[12]=-(r[0]*eye[0]+r[1]*eye[1]+r[2]*eye[2]);
    m[13]=-(u[0]*eye[0]+u[1]*eye[1]+u[2]*eye[2]);
    m[14]=(dir[0]*eye[0]+dir[1]*eye[1]+dir[2]*eye[2]);
    m[15]=1;

    const tmp = new Float32Array(16);
    this._mul4x4(p, m, tmp);
    for (let i = 0; i < 16; i++) this._viewProjection[i] = tmp[i];
  }

  _cross(a, b) {
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  }

  _mul4x4(a, b, out) {
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) {
        out[j*4+i] = 0;
        for (let k = 0; k < 4; k++) {
          out[j*4+i] += a[k*4+i] * b[j*4+k];
        }
      }
    }
  }

  _lerp(a, b, t) { return a + (b - a) * t; }
  _easeInOut(t) { return t < 0.5 ? 2*t*t : 1-Math.pow(-2*t+2,2)/2; }

  resize(w, h) { this._aspect = w / h; }

  screenToWorldRay(screenX, screenY) {
    const pos = this.free.getPosition();
    const dir = this.free.getDirection();
    const n = this._normalize(dir);
    const fov = 60 * Math.PI / 180;
    const aspect = this._aspect;
    const halfH = Math.tan(fov / 2);
    const halfW = halfH * aspect;
    const right = this._cross(n, [0, 1, 0]);
    const rLen = Math.sqrt(right[0]*right[0]+right[1]*right[1]+right[2]*right[2]);
    const r = rLen > 0 ? [right[0]/rLen, right[1]/rLen, right[2]/rLen] : [1, 0, 0];
    const up = this._cross(r, n);
    const rayDir = [
      r[0] * (screenX * 2 - 1) * halfW + up[0] * (screenY * 2 - 1) * halfH + n[0],
      r[1] * (screenX * 2 - 1) * halfW + up[1] * (screenY * 2 - 1) * halfH + n[1],
      r[2] * (screenX * 2 - 1) * halfW + up[2] * (screenY * 2 - 1) * halfH + n[2]
    ];
    const rl = Math.sqrt(rayDir[0]*rayDir[0]+rayDir[1]*rayDir[1]+rayDir[2]*rayDir[2]);
    return { origin: pos, direction: [rayDir[0]/rl, rayDir[1]/rl, rayDir[2]/rl] };
  }

  pickObject(ray, bodies) {
    let closest = null;
    let minDist = Infinity;
    for (const body of bodies) {
      const t = this._raySphereIntersect(ray, body.position, body.radius || 1.0);
      if (t !== null && t < minDist) {
        minDist = t;
        closest = body;
      }
    }
    return closest;
  }

  _raySphereIntersect(ray, center, radius) {
    const oc = [ray.origin[0]-center[0], ray.origin[1]-center[1], ray.origin[2]-center[2]];
    const a = ray.direction[0]*ray.direction[0]+ray.direction[1]*ray.direction[1]+ray.direction[2]*ray.direction[2];
    const b = 2*(oc[0]*ray.direction[0]+oc[1]*ray.direction[1]+oc[2]*ray.direction[2]);
    const c = oc[0]*oc[0]+oc[1]*oc[1]+oc[2]*oc[2]-radius*radius;
    const disc = b*b-4*a*c;
    if (disc < 0) return null;
    const t = (-b-Math.sqrt(disc))/(2*a);
    return t > 0 ? t : null;
  }
}
