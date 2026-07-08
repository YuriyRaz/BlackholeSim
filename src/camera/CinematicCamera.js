export class CinematicCamera {
  constructor() {
    this.theta = 0;
    this.phi = Math.PI / 6;
    this.distance = 150;
    this.rpm = 0.3;
    this.focusPoint = [0, 0, 0];
    this._active = false;
    this._userInput = false;
    this._inactiveTimer = 0;
  }

  get active() { return this._active; }

  enable() { this._active = true; this._userInput = false; }
  disable() { this._active = false; }

  onUserInput() {
    if (this._active) {
      this._userInput = true;
      this._inactiveTimer = 0;
    }
  }

  update(dt) {
    if (!this._active) return;
    if (this._userInput) {
      this._inactiveTimer += dt;
      if (this._inactiveTimer > 3) this._userInput = false;
      return;
    }
    this.theta += (this.rpm * 2 * Math.PI / 60) * dt;
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
}
