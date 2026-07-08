export class BackgroundPass {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._program = null;
    this._quadVBO = null;
    this._texture = null;
    this._uniforms = {};
    this._init();
  }

  get texture() { return this._texture; }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    const sm = this.shaderModule;
    this._program = sm.compileGL('starfield',
      `#version 300 es
      in vec2 a_pos; out vec2 v_uv;
      void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`,
      `#version 300 es
      precision highp float;
      uniform vec3 u_camDir; uniform vec2 u_resolution; uniform int u_starCount; uniform float u_time;
      uniform sampler2D u_nebulaTex;
      in vec2 v_uv; out vec4 fragColor;
      float hash31(vec3 p) { return fract(sin(dot(p, vec3(127.1,311.7,74.7)))*43758.5453); }
      vec3 stars(vec3 dir) {
        float cs=0.02; vec3 cell=floor(dir/cs); vec3 loc=fract(dir/cs)-0.5;
        vec3 c=vec3(0.0);
        for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++)for(int dz=-1;dz<=1;dz++){
          vec3 off=vec3(float(dx),float(dy),float(dz)); vec3 id=cell+off;
          float h=hash31(id); if(h*5000.0>float(u_starCount))continue;
          vec3 sp=vec3(hash31(id+vec3(1,0,0))-0.5,hash31(id+vec3(0,1,0))-0.5,hash31(id+vec3(0,0,1))-0.5);
          float d=length(loc-off-sp);
          float th=hash31(id+vec3(7,13,23)); vec3 sc;
          if(th<0.3)sc=vec3(0.7,0.8,1.0);else if(th<0.7)sc=vec3(1.0);else sc=vec3(1.0,0.8,0.6);
          float tw=1.0+0.3*sin(u_time*(0.5+hash31(id+vec3(31))*1.5)*6.28+hash31(id+vec3(47))*6.28);
          c+=sc*exp(-d*d*200.0)*tw*10.0;
        }
        return c;
      }
      void main() {
        float asp=u_resolution.x/u_resolution.y; float hH=0.5; float hW=hH*asp;
        vec3 ld=normalize(vec3((v_uv.x*2.0-1.0)*hW,(v_uv.y*2.0-1.0)*hH,1.0));
        vec3 right=normalize(cross(u_camDir,vec3(0,1,0))); vec3 up=cross(right,u_camDir);
        vec3 dir=normalize(ld.x*right+ld.y*up+ld.z*u_camDir);
        vec2 sphereUV=vec2(atan(dir.z,dir.x)/6.2832+0.5, asin(dir.y)/3.1416+0.5);
        vec3 bg=texture(u_nebulaTex,sphereUV).rgb;
        fragColor=vec4(bg+stars(dir),1.0);
      }`
    );

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    this._quadVBO = buf;

    const names = ['u_camDir','u_resolution','u_starCount','u_time','u_nebulaTex'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });

    this._texture = this._createNebulaTexture(gl);
  }

  _createNebulaTexture(gl) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    const w = 64, h = 32;
    const data = new Uint8Array(w * h * 4);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 4;
        const r = Math.sin(x * 0.3 + y * 0.1) * 0.3 + 0.1;
        const g = Math.sin(x * 0.2 + y * 0.15) * 0.2 + 0.05;
        const b = Math.cos(x * 0.1 + y * 0.3) * 0.4 + 0.2;
        data[i] = Math.floor(Math.max(0, Math.min(1, r)) * 255);
        data[i+1] = Math.floor(Math.max(0, Math.min(1, g)) * 255);
        data[i+2] = Math.floor(Math.max(0, Math.min(1, b)) * 255);
        data[i+3] = 255;
      }
    }
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return tex;
  }

  render(camState, settings, time) {
    if (this.renderer.backend !== 'webgl2') return;
    const gl = this.renderer.gl;
    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this._program);

    gl.uniform3f(this._uniforms.u_camDir, ...camState.direction);
    gl.uniform2f(this._uniforms.u_resolution, this.renderer.width, this.renderer.height);
    gl.uniform1i(this._uniforms.u_starCount, settings.starCount);
    gl.uniform1f(this._uniforms.u_time, time);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this._texture);
    gl.uniform1i(this._uniforms.u_nebulaTex, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  resize() {}
}
