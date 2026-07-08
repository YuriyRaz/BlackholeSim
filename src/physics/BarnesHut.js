import { Constants } from '../core/Constants.js';

export class BHNode {
  constructor(x, y, z, size) {
    this.x = x;
    this.y = y;
    this.z = z;
    this.size = size;
    this.mass = 0;
    this.massX = 0;
    this.massY = 0;
    this.massZ = 0;
    this.body = null;
    this.children = null;
    this.isLeaf = true;
  }

  insert(body) {
    if (this.mass === 0) {
      this.body = body;
      this.mass = body.mass;
      this.massX = body.position[0];
      this.massY = body.position[1];
      this.massZ = body.position[2];
      return;
    }

    if (this.isLeaf) {
      this._subdivide();
      this._insertIntoChild(this.body);
      this.body = null;
      this.isLeaf = false;
    }

    this._insertIntoChild(body);

    const totalMass = this.mass + body.mass;
    this.massX = (this.massX * this.mass + body.position[0] * body.mass) / totalMass;
    this.massY = (this.massY * this.mass + body.position[1] * body.mass) / totalMass;
    this.massZ = (this.massZ * this.mass + body.position[2] * body.mass) / totalMass;
    this.mass = totalMass;
  }

  _subdivide() {
    const halfSize = this.size / 2;
    this.children = [
      new BHNode(this.x - halfSize, this.y - halfSize, this.z - halfSize, halfSize),
      new BHNode(this.x + halfSize, this.y - halfSize, this.z - halfSize, halfSize),
      new BHNode(this.x - halfSize, this.y + halfSize, this.z - halfSize, halfSize),
      new BHNode(this.x + halfSize, this.y + halfSize, this.z - halfSize, halfSize),
      new BHNode(this.x - halfSize, this.y - halfSize, this.z + halfSize, halfSize),
      new BHNode(this.x + halfSize, this.y - halfSize, this.z + halfSize, halfSize),
      new BHNode(this.x - halfSize, this.y + halfSize, this.z + halfSize, halfSize),
      new BHNode(this.x + halfSize, this.y + halfSize, this.z + halfSize, halfSize)
    ];
  }

  _insertIntoChild(body) {
    const px = body.position[0];
    const py = body.position[1];
    const pz = body.position[2];
    
    const ix = px > this.x ? 1 : 0;
    const iy = py > this.y ? 1 : 0;
    const iz = pz > this.z ? 1 : 0;
    const index = ix + iy * 2 + iz * 4;
    
    this.children[index].insert(body);
  }

  computeAcceleration(body, theta) {
    if (this.mass === 0) return [0, 0, 0];

    const dx = this.massX - body.position[0];
    const dy = this.massY - body.position[1];
    const dz = this.massZ - body.position[2];
    const r2 = dx * dx + dy * dy + dz * dz + Constants.softening * Constants.softening;
    const r = Math.sqrt(r2);

    if (this.isLeaf) {
      if (this.body === body) return [0, 0, 0];
      const f = Constants.G * this.mass / (r2 * r);
      return [f * dx, f * dy, f * dz];
    }

    if (this.size / r < theta) {
      const f = Constants.G * this.mass / (r2 * r);
      return [f * dx, f * dy, f * dz];
    }

    let ax = 0, ay = 0, az = 0;
    for (const child of this.children) {
      const acc = child.computeAcceleration(body, theta);
      ax += acc[0];
      ay += acc[1];
      az += acc[2];
    }
    return [ax, ay, az];
  }
}

export class BarnesHut {
  constructor() {
    this.root = null;
  }

  build(bodies) {
    if (bodies.length === 0) {
      this.root = null;
      return;
    }

    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;

    for (const body of bodies) {
      minX = Math.min(minX, body.position[0]);
      maxX = Math.max(maxX, body.position[0]);
      minY = Math.min(minY, body.position[1]);
      maxY = Math.max(maxY, body.position[1]);
      minZ = Math.min(minZ, body.position[2]);
      maxZ = Math.max(maxZ, body.position[2]);
    }

    const size = Math.max(maxX - minX, maxY - minY, maxZ - minZ) * 1.1;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const cz = (minZ + maxZ) / 2;

    this.root = new BHNode(cx, cy, cz, size);
    for (const body of bodies) {
      this.root.insert(body);
    }
  }

  computeAcceleration(body, theta = Constants.barnesHutTheta) {
    if (!this.root) return [0, 0, 0];
    return this.root.computeAcceleration(body, theta);
  }
}