export class ParticleRenderer {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._program = null;
    this._vao = null;
    this._vbo = null;
    this._uniforms = {};
    this._maxCount = 35000;
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    const sm = this.shaderModule;
    this._program = sm.compileGL('particle',
      `#version 300 es
      layout(location=0) in vec3 a_pos;
      layout(location=1) in vec3 a_color;
      layout(location=2) in float a_size;
      layout(location=3) in float a_temperature;
      uniform mat4 u_viewProj;
      uniform vec3 u_camPos;
      uniform vec2 u_resolution;
      out vec3 v_color;
      void main() {
        vec4 clip = u_viewProj * vec4(a_pos, 1.0);
        float dist = length(a_pos - u_camPos);
        float ptSize = a_size / max(dist, 1.0) * u_resolution.y * 0.01;
        gl_PointSize = ptSize;
        gl_Position = clip;
        v_color = a_color;
      }`,
      `#version 300 es
      precision highp float;
      in vec3 v_color; out vec4 fragColor;
      void main() {
        vec2 c = gl_PointCoord - vec2(0.5);
        float d = length(c);
        if (d > 0.5) discard;
        float alpha = 1.0 - smoothstep(0.3, 0.5, d);
        fragColor = vec4(v_color * alpha, alpha);
      }`
    );

    const names = ['u_viewProj','u_camPos','u_resolution'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });

    this._vbo = gl.createBuffer();
  }

  render(camState, settings) {
    if (this.renderer.backend !== 'webgl2') return;
    const gl = this.renderer.gl;
    if (!this._program) return;

    const particles = camState.particles || [];
    const count = Math.min(particles.length, this._maxCount);
    if (count === 0) return;

    const data = new Float32Array(count * 8);
    for (let i = 0; i < count; i++) {
      const p = particles[i];
      const off = i * 8;
      data[off] = p.position[0];
      data[off+1] = p.position[1];
      data[off+2] = p.position[2];
      data[off+3] = p.color[0];
      data[off+4] = p.color[1];
      data[off+5] = p.color[2];
      data[off+6] = p.size || 1.0;
      data[off+7] = p.temperature || 0;
    }

    gl.useProgram(this._program);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);

    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);

    const stride = 8 * 4;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, stride, 12);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, stride, 24);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 1, gl.FLOAT, false, stride, 28);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);
    gl.uniform3f(this._uniforms.u_camPos, ...camState.position);
    gl.uniform2f(this._uniforms.u_resolution, this.renderer.width, this.renderer.height);

    gl.drawArrays(gl.POINTS, 0, count);
  }

  resize() {}
}
