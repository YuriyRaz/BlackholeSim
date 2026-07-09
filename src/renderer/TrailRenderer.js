export class TrailRenderer {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._program = null;
    this._vbo = null;
    this._uniforms = {};
    this._particleTrailsEnabled = true;
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    this._program = this.shaderModule.compileGL('trail',
      `#version 300 es
      layout(location=0) in vec3 a_pos;
      layout(location=1) in float a_alpha;
      layout(location=2) in vec3 a_color;
      uniform mat4 u_viewProj;
      out float v_alpha;
      out vec3 v_color;
      void main() {
        gl_Position = u_viewProj * vec4(a_pos, 1.0);
        v_alpha = a_alpha;
        v_color = a_color;
      }`,
      `#version 300 es
      precision highp float;
      in float v_alpha;
      in vec3 v_color;
      out vec4 fragColor;
      void main() {
        fragColor = vec4(v_color, v_alpha * 0.6);
      }`
    );

    const names = ['u_viewProj'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });

    this._vbo = gl.createBuffer();
  }

  render(camState, settings) {
    if (this.renderer.backend !== 'webgl2') return;
    const gl = this.renderer.gl;
    if (!this._program) return;

    gl.useProgram(this._program);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);

    const bodies = camState.bodies || [];
    for (const body of bodies) {
      if (!body.trail || body.trail.length < 2) continue;

      const trail = body.trail;
      const vertexCount = trail.length;
      const data = new Float32Array(vertexCount * 7);
      const color = body.color || [1, 1, 1];

      for (let i = 0; i < vertexCount; i++) {
        const offset = i * 7;
        data[offset] = trail[i][0];
        data[offset + 1] = trail[i][1];
        data[offset + 2] = trail[i][2];
        data[offset + 3] = i / vertexCount;
        data[offset + 4] = color[0];
        data[offset + 5] = color[1];
        data[offset + 6] = color[2];
      }

      this._drawTrailData(gl, data, vertexCount);
    }

    if (this._particleTrailsEnabled && camState.particleTrails) {
      const trails = camState.particleTrails;
      for (const id in trails) {
        const trail = trails[id];
        if (!trail || trail.length < 2) continue;
        const vertexCount = trail.length;
        const data = new Float32Array(vertexCount * 7);
        const color = camState.particleTrailColor || [0.5, 0.7, 1.0];

        for (let i = 0; i < vertexCount; i++) {
          const offset = i * 7;
          data[offset] = trail[i][0];
          data[offset + 1] = trail[i][1];
          data[offset + 2] = trail[i][2];
          data[offset + 3] = i / vertexCount;
          data[offset + 4] = color[0];
          data[offset + 5] = color[1];
          data[offset + 6] = color[2];
        }

        this._drawTrailData(gl, data, vertexCount);
      }
    }

    gl.disable(gl.BLEND);
  }

  _drawTrailData(gl, data, vertexCount) {
    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);

    const stride = 7 * 4;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, stride, 12);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 16);

    gl.drawArrays(gl.LINE_STRIP, 0, vertexCount);
  }

  resize() {}
}