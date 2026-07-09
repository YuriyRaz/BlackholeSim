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
      layout(location=1) in float a_size;
      layout(location=2) in float a_temperature;
      uniform mat4 u_viewProj;
      uniform vec3 u_camPos;
      uniform vec2 u_resolution;
      out float v_temperature;
      void main() {
        vec4 clip = u_viewProj * vec4(a_pos, 1.0);
        float dist = length(a_pos - u_camPos);
        float ptSize = a_size / max(dist, 1.0) * u_resolution.y * 0.01;
        gl_PointSize = ptSize;
        gl_Position = clip;
        v_temperature = a_temperature;
      }`,
      `#version 300 es
      precision highp float;
      in float v_temperature;
      out vec4 fragColor;

      vec3 temperatureToColor(float t) {
        float temp = clamp(t, 0.0, 100000.0) / 100000.0;
        vec3 col;
        col.r = smoothstep(0.0, 0.5, temp) + smoothstep(0.6, 1.0, temp) * 0.3;
        col.g = smoothstep(0.2, 0.7, temp);
        col.b = smoothstep(0.5, 1.0, temp);
        col = clamp(col, 0.0, 1.0);
        float brightness = 0.5 + 0.5 * temp;
        return col * brightness;
      }

      void main() {
        vec2 c = gl_PointCoord - vec2(0.5);
        float d = length(c);
        if (d > 0.5) discard;
        float alpha = 1.0 - smoothstep(0.3, 0.5, d);
        vec3 col = temperatureToColor(v_temperature);
        fragColor = vec4(col * alpha, alpha);
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

    const data = new Float32Array(count * 5);
    for (let i = 0; i < count; i++) {
      const p = particles[i];
      const off = i * 5;
      data[off] = p.position[0];
      data[off+1] = p.position[1];
      data[off+2] = p.position[2];
      data[off+3] = p.size || 1.0;
      data[off+4] = p.temperature || 0;
    }

    gl.useProgram(this._program);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);

    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);

    const stride = 5 * 4;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, stride, 12);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, stride, 16);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);
    gl.uniform3f(this._uniforms.u_camPos, ...camState.position);
    gl.uniform2f(this._uniforms.u_resolution, this.renderer.width, this.renderer.height);

    gl.drawArrays(gl.POINTS, 0, count);
  }

  resize() {}
}
