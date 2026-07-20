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
      layout(location=3) in vec3 a_velocity;
      uniform mat4 u_viewProj;
      uniform vec3 u_camPos;
      uniform vec2 u_resolution;
      out float v_temperature;
      out vec2 v_streakDir;
      void main() {
        vec4 clip = u_viewProj * vec4(a_pos, 1.0);
        vec3 velocityDir = normalize(a_velocity + vec3(0.001));
        vec4 clipVel = u_viewProj * vec4(a_pos + velocityDir * max(a_size, 1.0), 1.0);
        vec2 ndc = clip.xy / max(clip.w, 0.0001);
        vec2 velNdc = clipVel.xy / max(clipVel.w, 0.0001);
        vec2 screenDir = (velNdc - ndc) * u_resolution;
        float dist = length(a_pos - u_camPos);
        float ptSize = clamp(a_size / max(dist, 1.0) * u_resolution.y * 0.035, 1.25, 18.0);
        gl_PointSize = ptSize;
        gl_Position = clip;
        v_temperature = a_temperature;
        v_streakDir = length(screenDir) > 0.001 ? normalize(screenDir) : vec2(1.0, 0.0);
      }`,
      `#version 300 es
      precision highp float;
      in float v_temperature;
      in vec2 v_streakDir;
      out vec4 fragColor;

      vec3 temperatureToColor(float t) {
        float temp = clamp((log(max(t, 1.0)) - log(1000.0)) / (log(1.0e12) - log(1000.0)), 0.0, 1.0);
        vec3 cool = vec3(1.0, 0.42, 0.08);
        vec3 warm = vec3(1.0, 0.82, 0.25);
        vec3 hot = vec3(0.45, 0.78, 1.0);
        vec3 col = mix(cool, warm, smoothstep(0.0, 0.55, temp));
        col = mix(col, hot, smoothstep(0.55, 1.0, temp) * 0.45);
        return col;
      }

      void main() {
        vec2 c = gl_PointCoord - vec2(0.5);
        vec2 dir = normalize(v_streakDir);
        vec2 perp = vec2(-dir.y, dir.x);
        c = vec2(dot(c, dir) * 0.38, dot(c, perp) * 1.55);
        float d = length(c);
        if (d > 0.5) discard;
        float alpha = (1.0 - smoothstep(0.18, 0.5, d)) * 0.78;
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

    const data = new Float32Array(count * 8);
    for (let i = 0; i < count; i++) {
      const p = particles[i];
      const off = i * 8;
      data[off] = p.position[0];
      data[off+1] = p.position[1];
      data[off+2] = p.position[2];
      data[off+3] = p.size || 1.0;
      data[off+4] = p.temperature || 0;
      data[off+5] = p.velocity?.[0] || 0;
      data[off+6] = p.velocity?.[1] || 0;
      data[off+7] = p.velocity?.[2] || 0;
    }

    gl.useProgram(this._program);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);

    const stride = 8 * 4;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, stride, 12);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, stride, 16);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 3, gl.FLOAT, false, stride, 20);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);
    gl.uniform3f(this._uniforms.u_camPos, ...camState.position);
    gl.uniform2f(this._uniforms.u_resolution, this.renderer.width, this.renderer.height);

    gl.drawArrays(gl.POINTS, 0, count);
  }

  resize() {}
}
