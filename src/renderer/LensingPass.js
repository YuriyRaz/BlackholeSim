import { FrameBuffer } from './FrameBuffer.js';

export class LensingPass {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this.shaderModule = shaderModule;
    this._halfRes = true;
    this._stepCount = 20;
    this._program = null;
    this._fbo = null;
    this._quadVBO = null;
    this._uniforms = {};
    this._gwRipplesEnabled = true;
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    } else if (this.renderer.backend === 'webgpu') {
      this._initWebGPU();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    const sm = this.shaderModule;
    this._program = sm.compileGL('lensing',
      `#version 300 es
      in vec2 a_pos; out vec2 v_uv;
      void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`,
      `#version 300 es
      precision highp float;
      uniform sampler2D u_sceneTex;
      uniform vec3 u_camPos;
      uniform vec3 u_camDir;
      uniform vec2 u_resolution;
      uniform int u_stepCount;
      uniform int u_bhCount;
      uniform vec3 u_gwSourcePosition;
      uniform float u_gwFrequency;
      uniform float u_gwStrain;
      uniform float u_time;
      struct BlackHole { vec3 pos; float mass; float spin; float rs; };
      uniform BlackHole u_bhs[4];
      in vec2 v_uv; out vec4 fragColor;
      vec3 screenRay(vec2 uv) {
        float aspect = u_resolution.x / u_resolution.y;
        vec3 right = normalize(cross(u_camDir, vec3(0.0, 1.0, 0.0)));
        vec3 up = cross(right, u_camDir);
        return normalize((uv.x*2.0-1.0)*aspect*right + (uv.y*2.0-1.0)*up + u_camDir);
      }
      vec3 gwRippleDeflection(vec3 pos, float t) {
        if (u_gwStrain <= 0.0001) return vec3(0.0);
        vec3 toSource = pos - u_gwSourcePosition;
        float dist = length(toSource);
        if (dist < 0.001) return vec3(0.0);
        float amplitude = u_gwStrain * 0.02 / max(dist, 1.0);
        float phase = dist * u_gwFrequency * 0.01 - u_time * u_gwFrequency;
        float ripple = sin(phase) * amplitude;
        vec3 dir = normalize(toSource);
        vec3 perp1 = normalize(cross(dir, vec3(0.0, 1.0, 0.0)));
        vec3 perp2 = normalize(cross(dir, perp1));
        return (perp1 * ripple + perp2 * ripple * 0.7);
      }
      void main() {
        vec3 rayOri = u_camPos;
        vec3 rayDir = screenRay(v_uv);
        float t = 0.0; float dt = 50.0;
        for (int i = 0; i < u_stepCount; i++) {
          vec3 pos = rayOri + rayDir * t;
          vec3 gwDefl = gwRippleDeflection(pos, u_time);
          rayDir = normalize(rayDir + gwDefl * dt * 0.0005);
          bool absorbed = false;
          for (int bh = 0; bh < u_bhCount; bh++) {
            vec3 d = pos - u_bhs[bh].pos;
            float dist = length(d);
            if (dist < u_bhs[bh].rs * 0.5) { absorbed = true; break; }
            if (dist < u_bhs[bh].rs * 50.0) {
              float deflAngle = u_bhs[bh].rs / dist;
              vec3 toBH = normalize(d);
              rayDir = normalize(rayDir + toBH * deflAngle * dt * 0.001);
              if (u_bhs[bh].spin > 0.0) {
                vec3 tangential = cross(vec3(0.0, 1.0, 0.0), d);
                rayDir = normalize(rayDir + normalize(tangential) * u_bhs[bh].spin * u_bhs[bh].rs / (dist*dist) * dt * 0.0001);
              }
            }
          }
          if (absorbed) { fragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }
          t += dt;
          if (t > 1e6) break;
        }
        fragColor = texture(u_sceneTex, v_uv);
      }`
    );

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    this._quadVBO = buf;

    this._uniforms = {};
    const names = ['u_sceneTex','u_camPos','u_camDir','u_resolution','u_stepCount','u_bhCount',
      'u_gwSourcePosition','u_gwFrequency','u_gwStrain','u_time'];
    names.forEach(n => { this._uniforms[n] = gl.getUniformLocation(this._program, n); });
    for (let i = 0; i < 4; i++) {
      this._uniforms[`u_bhs[${i}].pos`] = gl.getUniformLocation(this._program, `u_bhs[${i}].pos`);
      this._uniforms[`u_bhs[${i}].mass`] = gl.getUniformLocation(this._program, `u_bhs[${i}].mass`);
      this._uniforms[`u_bhs[${i}].spin`] = gl.getUniformLocation(this._program, `u_bhs[${i}].spin`);
      this._uniforms[`u_bhs[${i}].rs`] = gl.getUniformLocation(this._program, `u_bhs[${i}].rs`);
    }

    this._createFBO(gl);
  }

  _createFBO(gl) {
    const w = this._halfRes ? Math.floor(this.renderer.width / 2) : this.renderer.width;
    const h = this._halfRes ? Math.floor(this.renderer.height / 2) : this.renderer.height;
    this._fbo = { w, h };
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
    if (status !== gl.FRAMEBUFFER_COMPLETE) {
      console.warn('Lensing framebuffer incomplete:', status);
    }
    this._fbo.fbo = fbo;
    this._fbo.tex = tex;
  }

  _initWebGPU() {
    const sm = this.shaderModule;
    this._module = sm.compileSync('lensing',
      `@group(0)@binding(0) var sceneTex: texture_2d<f32>;
       @group(0)@binding(1) var sceneSampler: sampler;
       @group(0)@binding(2) var<uniform> camPos: vec3<f32>;
       @group(0)@binding(3) var<uniform> camDir: vec3<f32>;
       @group(0)@binding(4) var<uniform> resolution: vec2<f32>;
       @group(0)@binding(5) var<uniform> stepCount: u32;
       @group(0)@binding(6) var<uniform> bhCount: u32;
       @group(0)@binding(7) var<uniform> gwSourcePosition: vec3<f32>;
       @group(0)@binding(8) var<uniform> gwFrequency: f32;
       @group(0)@binding(9) var<uniform> gwStrain: f32;
       @group(0)@binding(10) var<uniform> time: f32;
       struct BlackHole { pos: vec3<f32>; mass: f32; spin: f32; rs: f32; _p1: f32; _p2: f32; };
       @group(0)@binding(11) var<uniform> bhs: array<BlackHole,4>;
       struct VSOut { @builtin(position) pos: vec4<f32>; @location(0) uv: vec2<f32>; };
       @vertex fn vs(@builtin(vertex_index) vi: u32) -> VSOut {
         var o: VSOut; let x = f32(i32(vi&1u)*2-1); let y = f32(i32(vi>>1u)*2-1);
         o.pos = vec4<f32>(x,y,0,1); o.uv = vec2<f32>((x+1)*0.5,(1-y)*0.5); return o;
       }
       fn gwDeflection(pos: vec3<f32>, t: f32) -> vec3<f32> {
         if (gwStrain <= 0.0001) { return vec3<f32>(0.0); }
         let toSource = pos - gwSourcePosition;
         let dist = length(toSource);
         if (dist < 0.001) { return vec3<f32>(0.0); }
         let amp = gwStrain * 0.02 / max(dist, 1.0);
         let phase = dist * gwFrequency * 0.01 - t * gwFrequency;
         let ripple = sin(phase) * amp;
         let dir = normalize(toSource);
         let perp1 = normalize(cross(dir, vec3<f32>(0.0, 1.0, 0.0)));
         let perp2 = normalize(cross(dir, perp1));
         return perp1 * ripple + perp2 * ripple * 0.7;
       }
       @fragment fn fs(in: VSOut) -> @location(0) vec4<f32> {
         var ro = camPos; var rd = normalize(vec3<f32>((in.uv.x*2-1),(in.uv.y*2-1),1));
         var t = 0f; for(var i:u32=0u;i<stepCount;i++){
           let p = ro+rd*t;
           let gwD = gwDeflection(p, time);
           rd = normalize(rd + gwD * 0.5);
           var absorbed = false;
           for(var b:u32=0u;b<bhCount;b++){
             let d = p-bhs[b].pos; let dist=length(d);
             if(dist<bhs[b].rs*0.5){absorbed=true;break;}
             if(dist<bhs[b].rs*50){let a=bhs[b].rs/dist; rd=normalize(rd+normalize(d)*a*0.5);}
           }
           if(absorbed){return vec4<f32>(0,0,0,1);}
           t+=50; if(t>1e6){break;}
         }
         return textureSample(sceneTex,sceneSampler,in.uv);
       }`,
      ''
    );
  }

  render(camState, settings, sceneTexture, time) {
    this._halfRes = settings.lensingResolution === 'half';
    this._stepCount = settings.lensingSteps;

    if (this.renderer.backend === 'webgl2') {
      this._renderGL(camState, settings, sceneTexture, time);
    }
  }

  _renderGL(camState, settings, sceneTexture, time) {
    const gl = this.renderer.gl;
    const fbo = this._halfRes ? this._fbo : { fbo: null, w: this.renderer.width, h: this.renderer.height };

    if (this._halfRes && (!this._fbo || this._fbo.w !== Math.floor(this.renderer.width/2))) {
      this._createFBO(gl);
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.fbo);
    gl.viewport(0, 0, fbo.w, fbo.h);
    gl.useProgram(this._program);
    gl.disable(gl.DEPTH_TEST);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, sceneTexture);
    gl.uniform1i(this._uniforms.u_sceneTex, 0);
    gl.uniform3f(this._uniforms.u_camPos, ...camState.position);
    gl.uniform3f(this._uniforms.u_camDir, ...camState.direction);
    gl.uniform2f(this._uniforms.u_resolution, this.renderer.width, this.renderer.height);
    gl.uniform1i(this._uniforms.u_stepCount, this._stepCount);
    gl.uniform1i(this._uniforms.u_bhCount, camState.blackHoles?.length || 0);

    if (this._gwRipplesEnabled && camState.gw) {
      const gw = camState.gw;
      const sourcePos = camState.gwSourcePosition || [0, 0, 0];
      gl.uniform3f(this._uniforms.u_gwSourcePosition, sourcePos[0], sourcePos[1], sourcePos[2]);
      gl.uniform1f(this._uniforms.u_gwFrequency, gw.frequency);
      gl.uniform1f(this._uniforms.u_gwStrain, gw.strain);
      gl.uniform1f(this._uniforms.u_time, time || 0);
    } else {
      gl.uniform1f(this._uniforms.u_gwStrain, 0);
    }

    if (camState.blackHoles) {
      for (let i = 0; i < Math.min(camState.blackHoles.length, 4); i++) {
        const bh = camState.blackHoles[i];
        gl.uniform3f(this._uniforms[`u_bhs[${i}].pos`], ...bh.position);
        gl.uniform1f(this._uniforms[`u_bhs[${i}].mass`], bh.mass);
        gl.uniform1f(this._uniforms[`u_bhs[${i}].spin`], bh.spin);
        gl.uniform1f(this._uniforms[`u_bhs[${i}].rs`], bh.rs);
      }
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    if (this._halfRes) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.renderer.width, this.renderer.height);
      gl.bindTexture(gl.TEXTURE_2D, this._fbo.tex);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }

  resize(w, h) {
    if (this.renderer.backend === 'webgl2') {
      this._createFBO(this.renderer.gl);
    }
  }
}
