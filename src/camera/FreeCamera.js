export class FreeCamera {
  constructor(canvas) {
    this.theta = 0;
    this.phi = Math.PI / 4;
    this.distance = 100;
    this.targetTheta = 0;
    this.targetPhi = Math.PI / 4;
    this.targetDistance = 100;
    this.focusPoint = [0, 0, 0];
    this.targetFocus = [0, 0, 0];
    this._damping = 0.08;
    this._minDist = 2;
    this._maxDist = 1e10;
    this._minPhi = -85 * Math.PI / 180;
    this._maxPhi = 85 * Math.PI / 180;
    this._keys = {};
    this._isOrbiting = false;
    this._isPanning = false;
    this._lastMouse = [0, 0];

    canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
    canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
    canvas.addEventListener('mouseup', () => this._onMouseUp());
    canvas.addEventListener('wheel', (e) => this._onWheel(e));
    window.addEventListener('keydown', (e) => { this._keys[e.key.toLowerCase()] = true; });
    window.addEventListener('keyup', (e) => { this._keys[e.key.toLowerCase()] = false; });
  }

  _onMouseDown(e) {
    if (e.button === 0 && !e.shiftKey) { this._isOrbiting = true; }
    else if (e.button === 2 || (e.button === 0 && e.shiftKey)) { this._isPanning = true; }
    this._lastMouse = [e.clientX, e.clientY];
    e.preventDefault();
  }

  _onMouseMove(e) {
    const dx = e.clientX - this._lastMouse[0];
    const dy = e.clientY - this._lastMouse[1];
    this._lastMouse = [e.clientX, e.clientY];

    if (this._isOrbiting) {
      this.targetTheta -= dx * 0.005;
      this.targetPhi = Math.max(this._minPhi, Math.min(this._maxPhi, this.targetPhi - dy * 0.005));
    }
    if (this._isPanning) {
      const right = this._getRight();
      const up = this._getUp();
      const scale = this.distance * 0.002;
      this.targetFocus[0] -= (right[0] * dx + up[0] * dy) * scale;
      this.targetFocus[1] -= (right[1] * dx + up[1] * dy) * scale;
      this.targetFocus[2] -= (right[2] * dx + up[2] * dy) * scale;
    }
  }

  _onMouseUp() {
    this._isOrbiting = false;
    this._isPanning = false;
  }

  _onWheel(e) {
    this.targetDistance *= 1 + e.deltaY * 0.001;
    this.targetDistance = Math.max(this._minDist, Math.min(this._maxDist, this.targetDistance));
    e.preventDefault();
  }

  _getRight() {
    return [Math.cos(this.theta), 0, Math.sin(this.theta)];
  }

  _getUp() {
    return [0, 1, 0];
  }

  getPosition() {
    const cosPhi = Math.cos(this.phi);
    return [
      this.focusPoint[0] + this.distance * cosPhi * Math.sin(this.theta),
      this.focusPoint[1] + this.distance * Math.sin(this.phi),
      this.focusPoint[2] + this.distance * cosPhi * Math.cos(this.theta)
    ];
  }

  getDirection() {
    const pos = this.getPosition();
    return [
      this.focusPoint[0] - pos[0],
      this.focusPoint[1] - pos[1],
      this.focusPoint[2] - pos[2]
    ];
  }

  update(dt) {
    const spd = this.distance * 2.0;
    if (this._keys['w']) this.targetFocus[2] -= spd * dt;
    if (this._keys['s']) this.targetFocus[2] += spd * dt;
    if (this._keys['a']) this.targetFocus[0] -= spd * dt;
    if (this._keys['d']) this.targetFocus[0] += spd * dt;
    if (this._keys['q']) this.targetFocus[1] += spd * dt;
    if (this._keys['e']) this.targetFocus[1] -= spd * dt;

    this.theta += (this.targetTheta - this.theta) * this._damping;
    this.phi += (this.targetPhi - this.phi) * this._damping;
    this.distance += (this.targetDistance - this.distance) * this._damping;
    this.focusPoint[0] += (this.targetFocus[0] - this.focusPoint[0]) * this._damping;
    this.focusPoint[1] += (this.targetFocus[1] - this.focusPoint[1]) * this._damping;
    this.focusPoint[2] += (this.targetFocus[2] - this.focusPoint[2]) * this._damping;
  }

  setTarget(theta, phi, distance, focus) {
    this.targetTheta = theta;
    this.targetPhi = Math.max(this._minPhi, Math.min(this._maxPhi, phi));
    this.targetDistance = Math.max(this._minDist, Math.min(this._maxDist, distance));
    if (focus) this.targetFocus = [...focus];
  }

  reset() {
    this.setTarget(0, Math.PI / 4, 100, [0, 0, 0]);
  }
}
