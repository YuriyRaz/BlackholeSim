export class SpatialHashGrid {
  constructor(cellSize = 1) {
    this.cellSize = cellSize;
    this._cells = new Map();
  }

  clear() {
    this._cells.clear();
  }

  _hash(cx, cy, cz) {
    const p1 = 73856093;
    const p2 = 19349663;
    const p3 = 83492791;
    return ((cx * p1) ^ (cy * p2) ^ (cz * p3)) >>> 0;
  }

  _cellKey(x, y, z) {
    const cx = Math.floor(x / this.cellSize);
    const cy = Math.floor(y / this.cellSize);
    const cz = Math.floor(z / this.cellSize);
    return this._hash(cx, cy, cz) + ':' + cx + ':' + cy + ':' + cz;
  }

  insert(particle) {
    const key = this._cellKey(particle.position[0], particle.position[1], particle.position[2]);
    let cell = this._cells.get(key);
    if (!cell) {
      cell = [];
      this._cells.set(key, cell);
    }
    cell.push(particle);
  }

  query(position, radius) {
    const minCx = Math.floor((position[0] - radius) / this.cellSize);
    const maxCx = Math.floor((position[0] + radius) / this.cellSize);
    const minCy = Math.floor((position[1] - radius) / this.cellSize);
    const maxCy = Math.floor((position[1] + radius) / this.cellSize);
    const minCz = Math.floor((position[2] - radius) / this.cellSize);
    const maxCz = Math.floor((position[2] + radius) / this.cellSize);

    const radius2 = radius * radius;
    const result = [];
    const seen = new Set();

    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        for (let cz = minCz; cz <= maxCz; cz++) {
          const key = this._cellKey(cx * this.cellSize, cy * this.cellSize, cz * this.cellSize);
          const cell = this._cells.get(key);
          if (!cell) continue;

          for (const p of cell) {
            if (seen.has(p.id)) continue;
            seen.add(p.id);

            const dx = p.position[0] - position[0];
            const dy = p.position[1] - position[1];
            const dz = p.position[2] - position[2];
            if (dx * dx + dy * dy + dz * dz <= radius2) {
              result.push(p);
            }
          }
        }
      }
    }

    return result;
  }

  rebuild(particles) {
    this.clear();
    for (const p of particles) {
      if (p.isActive) {
        this.insert(p);
      }
    }
  }
}
