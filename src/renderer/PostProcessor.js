export class PostProcessor {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this._shaderModule = shaderModule;
    this._w = renderer.width;
    this._h = renderer.height;
    this._fb1 = null;
    this._fb2 = null;
    this._workingFBO = null;
    this._programs = {};
    this._quadVAO = null;
    this._flashIntensity = 0;
    this._flashDecay = 0;
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    const sm = this._shaderModule;
    const vs = `#version 300 es
    in vec2 a_pos; out vec2 v_uv;
    void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`;

    this._programs.tonemap = this._compileProgram(gl, vs, TONEMAP_FS);
    this._programs.bloomPrefilter = this._compileProgram(gl, vs, BLOOM_PREFILTER_FS);
    this._programs.bloomBlur = this._compileProgram(gl, vs, BLOOM_BLUR_FS);
    this._programs.bloomCombine = this._compileProgram(gl, vs, BLOOM_COMBINE_FS);
    this._programs.fxaa = this._compileProgram(gl, vs, FXAA_FS);
    this._programs.vignette = this._compileProgram(gl, vs, VIGNETTE_FS);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    this._quadVBO = buf;

    this._createFBOs(gl);
  }

  _createFBOs(gl) {
    const w = Math.floor(this._w / 2) || 1;
    const h = Math.floor(this._h / 2) || 1;
    this._fb1 = this._createFBO(gl, w, h);
    this._fb2 = this._createFBO(gl, w, h);
    this._screenFBO = this._createFBO(gl, this._w, this._h);
    this._workingFBO = this._createFBO(gl, this._w, this._h);
  }

  _createFBO(gl, w, h) {
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
      console.warn('PostProcessor framebuffer incomplete:', status);
    }
    return { fbo, tex, w, h };
  }

  _compileProgram(gl, vs, fs) {
    const v = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(v, vs);
    gl.compileShader(v);
    if (!gl.getShaderParameter(v, gl.COMPILE_STATUS)) {
      console.error('Vertex shader error:', gl.getShaderInfoLog(v));
    }
    const f = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(f, fs);
    gl.compileShader(f);
    if (!gl.getShaderParameter(f, gl.COMPILE_STATUS)) {
      console.error('Fragment shader error:', gl.getShaderInfoLog(f));
    }
    const p = gl.createProgram();
    gl.attachShader(p, v);
    gl.attachShader(p, f);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(p));
    }
    return p;
  }

  _drawQuad(gl) {
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  render(settings) {
    const gl = this.renderer.gl;
    if (!gl) return;
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);

    this._captureScreen(gl);

    let currentTex = this._screenFBO.tex;
    const nextTarget = () => currentTex === this._screenFBO.tex ? this._workingFBO : this._screenFBO;

    if (settings.bloom) {
      const target = nextTarget();
      this._applyBloom(gl, currentTex, target);
      currentTex = target.tex;
    }
    if (settings.tonemap) {
      const target = nextTarget();
      this._applyTonemap(gl, currentTex, target);
      currentTex = target.tex;
    }
    if (settings.fxaa) {
      const target = nextTarget();
      this._applyFXAA(gl, currentTex, target);
      currentTex = target.tex;
    }

    this._applyVignette(gl, currentTex, null);
  }

  _captureScreen(gl) {
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, null);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, this._screenFBO.fbo);
    gl.blitFramebuffer(
      0, 0, this._w, this._h,
      0, 0, this._w, this._h,
      gl.COLOR_BUFFER_BIT, gl.NEAREST
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  setFlashIntensity(intensity) {
    this._flashIntensity = intensity;
  }

  updateFlash(dt) {
    if (this._flashIntensity > 0) {
      this._flashDecay += dt;
      this._flashIntensity *= Math.exp(-this._flashDecay / 0.5);
      if (this._flashIntensity < 0.01) {
        this._flashIntensity = 0;
        this._flashDecay = 0;
      }
    }
  }

  _bindTarget(gl, target) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fbo : null);
    gl.viewport(0, 0, target ? target.w : this.renderer.width, target ? target.h : this.renderer.height);
  }

  _applyTonemap(gl, inputTex, target) {
    this._bindTarget(gl, target);
    gl.useProgram(this._programs.tonemap);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, inputTex);
    gl.uniform1i(gl.getUniformLocation(this._programs.tonemap, 'u_sceneTex'), 0);
    this._drawQuad(gl);
  }

  _applyBloom(gl, inputTex, target) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, this._fb1.fbo);
    gl.viewport(0, 0, this._fb1.w, this._fb1.h);
    gl.useProgram(this._programs.bloomPrefilter);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, inputTex);
    gl.uniform1i(gl.getUniformLocation(this._programs.bloomPrefilter, 'u_sceneTex'), 0);
    gl.uniform1f(gl.getUniformLocation(this._programs.bloomPrefilter, 'u_flashIntensity'), this._flashIntensity);
    this._drawQuad(gl);

    const horizontal = [1.0 / this._fb2.w, 0.0];
    const vertical = [0.0, 1.0 / this._fb2.h];
    for (let i = 0; i < 4; i++) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this._fb2.fbo);
      gl.viewport(0, 0, this._fb2.w, this._fb2.h);
      gl.useProgram(this._programs.bloomBlur);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this._fb1.tex);
      gl.uniform1i(gl.getUniformLocation(this._programs.bloomBlur, 'u_inputTex'), 0);
      gl.uniform2fv(gl.getUniformLocation(this._programs.bloomBlur, 'u_direction'), i % 2 === 0 ? horizontal : vertical);
      this._drawQuad(gl);

      gl.bindFramebuffer(gl.FRAMEBUFFER, this._fb1.fbo);
      gl.viewport(0, 0, this._fb1.w, this._fb1.h);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this._fb2.tex);
      gl.uniform1i(gl.getUniformLocation(this._programs.bloomBlur, 'u_inputTex'), 0);
      gl.uniform2fv(gl.getUniformLocation(this._programs.bloomBlur, 'u_direction'), i % 2 === 0 ? vertical : horizontal);
      this._drawQuad(gl);
    }

    this._bindTarget(gl, target);
    gl.useProgram(this._programs.bloomCombine);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, inputTex);
    gl.uniform1i(gl.getUniformLocation(this._programs.bloomCombine, 'u_sceneTex'), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this._fb1.tex);
    gl.uniform1i(gl.getUniformLocation(this._programs.bloomCombine, 'u_bloomTex'), 1);
    this._drawQuad(gl);
  }

  _applyFXAA(gl, inputTex, target) {
    this._bindTarget(gl, target);
    gl.useProgram(this._programs.fxaa);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, inputTex);
    gl.uniform1i(gl.getUniformLocation(this._programs.fxaa, 'u_inputTex'), 0);
    gl.uniform2f(gl.getUniformLocation(this._programs.fxaa, 'u_texelSize'), 1.0 / this._w, 1.0 / this._h);
    this._drawQuad(gl);
  }

  _applyVignette(gl, inputTex, target) {
    this._bindTarget(gl, target);
    gl.useProgram(this._programs.vignette);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, inputTex);
    gl.uniform1i(gl.getUniformLocation(this._programs.vignette, 'u_inputTex'), 0);
    this._drawQuad(gl);
  }

  resize(w, h) {
    this._w = w;
    this._h = h;
    const gl = this.renderer.gl;
    if (gl) this._createFBOs(gl);
  }
}

const TONEMAP_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_sceneTex;
vec3 aces(vec3 x){return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0);}
void main(){
  vec3 scene = texture(u_sceneTex, v_uv).rgb;
  fragColor=vec4(aces(scene),1.0);
}`;

const BLOOM_PREFILTER_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_sceneTex;
uniform float u_flashIntensity;
void main(){
  vec3 c = texture(u_sceneTex, v_uv).rgb;
  float brightness = dot(c, vec3(0.2126, 0.7152, 0.0722));
  brightness *= (1.0 + u_flashIntensity * 5.0);
  float soft = smoothstep(0.6, 1.0, brightness);
  fragColor = vec4(c * soft, 1.0);
}`;

const BLOOM_BLUR_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_inputTex;
uniform vec2 u_direction;
void main(){
  vec2 texel = u_direction;
  vec3 result = vec3(0.0);
  float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  result += texture(u_inputTex, v_uv).rgb * weights[0];
  for(int i = 1; i < 5; i++){
    vec2 offset = texel * float(i);
    result += texture(u_inputTex, v_uv + offset).rgb * weights[i];
    result += texture(u_inputTex, v_uv - offset).rgb * weights[i];
  }
  fragColor = vec4(result, 1.0);
}`;

const BLOOM_COMBINE_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_sceneTex;
uniform sampler2D u_bloomTex;
void main(){
  vec3 scene = texture(u_sceneTex, v_uv).rgb;
  vec3 bloom = texture(u_bloomTex, v_uv).rgb;
  fragColor = vec4(scene + bloom * 0.6, 1.0);
}`;

const FXAA_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_inputTex;
uniform vec2 u_texelSize;
float luminance(vec3 c){return dot(c, vec3(0.2126, 0.7152, 0.0722));}
void main(){
  vec2 ts = u_texelSize;
  vec3 rgbNW = texture(u_inputTex, v_uv + vec2(-1.0,-1.0)*ts).rgb;
  vec3 rgbNE = texture(u_inputTex, v_uv + vec2( 1.0,-1.0)*ts).rgb;
  vec3 rgbSW = texture(u_inputTex, v_uv + vec2(-1.0, 1.0)*ts).rgb;
  vec3 rgbSE = texture(u_inputTex, v_uv + vec2( 1.0, 1.0)*ts).rgb;
  vec3 rgbM  = texture(u_inputTex, v_uv).rgb;
  float lumaNW = luminance(rgbNW);
  float lumaNE = luminance(rgbNE);
  float lumaSW = luminance(rgbSW);
  float lumaSE = luminance(rgbSE);
  float lumaM  = luminance(rgbM);
  float lumaMin = min(lumaM, min(min(lumaNW,lumaNE),min(lumaSW,lumaSE)));
  float lumaMax = max(lumaM, max(max(lumaNW,lumaNE),max(lumaSW,lumaSE)));
  vec2 dir;
  dir.x = -((lumaNW+lumaNE)-(lumaSW+lumaSE));
  dir.y =  ((lumaNW+lumaSW)-(lumaNE+lumaSE));
  float dirReduce = max((lumaNW+lumaNE+lumaSW+lumaSE)*0.25*0.125,0.001);
  float rcpDirMin = 1.0/(min(abs(dir.x),abs(dir.y))+dirReduce);
  dir = min(vec2(8.0), max(vec2(-8.0), dir*rcpDirMin)) * ts;
  vec3 rgbA = 0.5*(texture(u_inputTex, v_uv+dir*0.166666).rgb+texture(u_inputTex, v_uv-dir*0.166666).rgb);
  vec3 rgbB = rgbA*0.5+0.25*(texture(u_inputTex, v_uv+dir*0.5).rgb+texture(u_inputTex, v_uv-dir*0.5).rgb);
  float lumaB = luminance(rgbB);
  if(lumaB < lumaMin || lumaB > lumaMax){
    fragColor = vec4(rgbA,1.0);
  }else{
    fragColor = vec4(rgbB,1.0);
  }
}`;

const VIGNETTE_FS = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_inputTex;
void main(){
  float d=length(v_uv-0.5);
  float v=smoothstep(0.8,0.3,d);
  vec3 scene = texture(u_inputTex, v_uv).rgb;
  fragColor=vec4(scene * v,1.0);
}`;
