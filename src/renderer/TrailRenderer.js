export class TrailRenderer {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._program = null;
    this._vbo = null;
    this._uniforms = {};
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
      uniform mat4 u_viewProj;
      out float v_alpha;
      void main() {
        gl_Position = u_viewProj * vec4(a_pos, 1.0);
        v_alpha = a_alpha;
      }`,
      `#version 300 es
      precision highp float;
      in float v_alpha;
      uniform vec3 u_trailColor;
      out vec4 fragColor;
      void main() {
        fragColor = vec4(u_trailColor, v_alpha * 0.6);
      }`
    );

    const names = ['u_viewProj', 'u_trailColor'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });

    this._vbo = gl.createBuffer();
  }

  render(camState, settings) {
    if (this.renderer.backend !== 'webgl2') return;
    const gl = this.renderer.gl;
    if (!this._program) return;

    const bodies = camState.bodies || [];
    gl.useProgram(this._program);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);

    for (const body of bodies) {
      if (!body.trail || body.trail.length < 2) continue;

      const trail = body.trail;
      const vertexCount = trail.length;
      const data = new Float32Array(vertexCount * 4);

      for (let i = 0; i < vertexCount; i++) {
        const offset = i * 4;
        data[offset] = trail[i][0];
        data[offset + 1] = trail[i][1];
        data[offset + 2] = trail[i][2];
        data[offset + 3] = i / vertexCount;
      }

      gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);

      const stride = 4 * 4;
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 1, gl.FLOAT, false, stride, 12);

      const color = body.color || [1, 1, 1];
      gl.uniform3f(this._uniforms.u_trailColor, color[0], color[1], color[2]);

      gl.drawArrays(gl.LINE_STRIP, 0, vertexCount);
    }

    gl.disable(gl.BLEND);
  }

  resize() {}
}