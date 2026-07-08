export class BodyRenderer {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._program = null;
    this._sphereVAO = null;
    this._uniforms = {};
    this._sphereData = null;
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _createSphere(segments = 16) {
    const vertices = [];
    for (let lat = 0; lat <= segments; lat++) {
      const theta = (lat * Math.PI) / segments;
      const sinT = Math.sin(theta);
      const cosT = Math.cos(theta);
      for (let lon = 0; lon <= segments; lon++) {
        const phi = (lon * 2 * Math.PI) / segments;
        vertices.push(sinT * Math.cos(phi), cosT, sinT * Math.sin(phi));
      }
    }
    const indices = [];
    for (let lat = 0; lat < segments; lat++) {
      for (let lon = 0; lon < segments; lon++) {
        const a = lat * (segments + 1) + lon;
        const b = a + segments + 1;
        indices.push(a, b, a + 1, b, b + 1, a + 1);
      }
    }
    return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
  }

  _initGL() {
    const gl = this.renderer.gl;
    this._program = this.shaderModule.compileGL('body',
      `#version 300 es
      layout(location=0) in vec3 a_pos;
      uniform mat4 u_viewProj;
      uniform vec3 u_bodyPos;
      uniform float u_bodyRadius;
      out vec3 v_normal;
      out vec3 v_worldPos;
      void main() {
        vec3 wp = a_pos * u_bodyRadius + u_bodyPos;
        gl_Position = u_viewProj * vec4(wp, 1.0);
        v_normal = a_pos;
        v_worldPos = wp;
      }`,
      `#version 300 es
      precision highp float;
      in vec3 v_normal; in vec3 v_worldPos;
      uniform vec3 u_bodyColor; uniform uint u_bodyType; uniform float u_time; uniform vec3 u_camPos;
      uniform bool u_selected;
      out vec4 fragColor;
      void main() {
        vec3 n = normalize(v_normal);
        vec3 light = normalize(vec3(1.0));
        float diff = max(dot(n, light), 0.1);
        vec3 col = u_bodyColor * diff;
        if (u_bodyType == 0u) {
          fragColor = vec4(0.0);
        } else if (u_bodyType == 1u) {
          vec3 vd = normalize(u_camPos - v_worldPos);
          float rim = 1.0 - max(dot(vd, n), 0.0);
          fragColor = vec4(col + vec3(pow(rim,3.0)*0.5, pow(rim,3.0)*0.3, pow(rim,3.0)), 1.0);
        } else if (u_bodyType == 2u) {
          float beam = pow(max(dot(n, vec3(0,1,0)),0.0), 8.0);
          fragColor = vec4(col + vec3(beam * (0.5+0.5*sin(u_time*10.0))), 1.0);
        } else {
          fragColor = vec4(col, 1.0);
        }
        if (u_selected) {
          vec3 vd = normalize(u_camPos - v_worldPos);
          float rim = 1.0 - max(dot(vd, n), 0.0);
          fragColor.rgb += vec3(0.2, 0.4, 0.8) * pow(rim, 2.0) * 0.5;
        }
      }`
    );

    const names = ['u_viewProj','u_bodyPos','u_bodyColor','u_bodyRadius','u_bodyType','u_time','u_camPos','u_selected'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });

    this._sphereData = this._createSphere(16);
    this._vbo = gl.createBuffer();
    this._ebo = gl.createBuffer();

    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bufferData(gl.ARRAY_BUFFER, this._sphereData.vertices, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this._ebo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, this._sphereData.indices, gl.STATIC_DRAW);
  }

  render(camState, settings) {
    if (this.renderer.backend !== 'webgl2') return;
    const gl = this.renderer.gl;
    if (!this._program) return;

    const bodies = camState.bodies || [];
    gl.useProgram(this._program);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.CULL_FACE);

    gl.bindBuffer(gl.ARRAY_BUFFER, this._vbo);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this._ebo);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

    gl.uniformMatrix4fv(this._uniforms.u_viewProj, false, camState.viewProjection);
    gl.uniform3f(this._uniforms.u_camPos, ...camState.position);
    gl.uniform1f(this._uniforms.u_time, camState.time || 0);

    for (const body of bodies) {
      const typeMap = { blackhole: 0, star: 1, neutronstar: 2 };
      gl.uniform3f(this._uniforms.u_bodyPos, ...body.position);
      gl.uniform3f(this._uniforms.u_bodyColor, ...body.color);
      gl.uniform1f(this._uniforms.u_bodyRadius, body.radius || 1.0);
      gl.uniform1ui(this._uniforms.u_bodyType, typeMap[body.type] || 1);
      gl.uniform1i(this._uniforms.u_selected, body.selected ? 1 : 0);

      gl.drawElements(gl.TRIANGLES, this._sphereData.indices.length, gl.UNSIGNED_SHORT, 0);
    }
  }

  resize() {}
}
