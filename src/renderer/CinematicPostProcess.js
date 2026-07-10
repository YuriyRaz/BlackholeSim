export class CinematicPostProcess {
  constructor(renderer, shaderModule) {
    this.renderer = renderer;
    this._shaderModule = shaderModule;
    this._w = renderer.width;
    this._h = renderer.height;
    this._programs = {};
    this._quadVAO = null;
    this._enabled = {
      motionBlur: false,
      chromaticAberration: true,
      lensFlare: true,
      depthOfField: false,
      colorGrading: true,
      vignette: true
    };
    this._quality = 'medium';
    this._init();
  }

  _init() {
    if (this.renderer.backend === 'webgl2') {
      this._initGL();
    }
  }

  _initGL() {
    const gl = this.renderer.gl;
    const vs = `#version 300 es
    in vec2 a_pos; out vec2 v_uv;
    void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`;

    this._programs.chromaticAberration = this._compileProgram(gl, vs, CHROMATIC_ABERRATION_FS);
    this._programs.colorGrading = this._compileProgram(gl, vs, COLOR_GRADING_FS);
    this._programs.vignette = this._compileProgram(gl, vs, VIGNETTE_FS);
    
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    this._quadVBO = buf;

    this._createFBOs(gl);
  }

  _createFBOs(gl) {
    if (this._fboA) {
      gl.deleteTexture(this._fboA.tex);
      gl.deleteFramebuffer(this._fboA.fbo);
    }
    if (this._fboB) {
      gl.deleteTexture(this._fboB.tex);
      gl.deleteFramebuffer(this._fboB.fbo);
    }
    this._fboA = this._createFBO(gl, this._w, this._h);
    this._fboB = this._createFBO(gl, this._w, this._h);
  }

  _createFBO(gl, w, h) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w || 1, h || 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { fbo, tex };
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

  setQuality(quality) {
    this._quality = quality;
    this._enabled.motionBlur = quality === 'high';
  }

  setEnabled(effect, enabled) {
    this._enabled[effect] = enabled;
  }

  render() {
    const gl = this.renderer.gl;
    if (!gl || !this._fboA || !this._fboB) return;
    
    gl.disable(gl.DEPTH_TEST);

    // Capture current screen into fboA by blitting
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, null);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, this._fboA.fbo);
    gl.blitFramebuffer(
      0, 0, this._w, this._h,
      0, 0, this._w, this._h,
      gl.COLOR_BUFFER_BIT, gl.NEAREST
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);

    let currentTex = this._fboA.tex;
    let targetFBO = this._fboB;
    
    const effects = [];
    if (this._enabled.chromaticAberration) effects.push('chromaticAberration');
    if (this._enabled.colorGrading) effects.push('colorGrading');
    if (this._enabled.vignette) effects.push('vignette');

    for (let i = 0; i < effects.length; i++) {
      const isLast = (i === effects.length - 1);
      if (isLast) {
        // Render final pass to screen
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      } else {
        gl.bindFramebuffer(gl.FRAMEBUFFER, targetFBO.fbo);
      }

      switch (effects[i]) {
        case 'chromaticAberration':
          this._renderChromaticAberration(gl, currentTex);
          break;
        case 'colorGrading':
          this._renderColorGrading(gl, currentTex);
          break;
        case 'vignette':
          this._renderVignette(gl, currentTex);
          break;
      }

      if (!isLast) {
        currentTex = targetFBO.tex;
        targetFBO = (targetFBO === this._fboB) ? this._fboA : this._fboB;
      }
    }
    
    gl.enable(gl.DEPTH_TEST);
  }

  _renderChromaticAberration(gl, texture) {
    const program = this._programs.chromaticAberration;
    if (!program) return;
    
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(gl.getUniformLocation(program, 'u_texture'), 0);
    gl.uniform2f(gl.getUniformLocation(program, 'u_resolution'), this._w, this._h);
    gl.uniform1f(gl.getUniformLocation(program, 'u_intensity'), 0.002);
    
    this._drawQuad(gl);
  }

  _renderColorGrading(gl, texture) {
    const program = this._programs.colorGrading;
    if (!program) return;
    
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(gl.getUniformLocation(program, 'u_texture'), 0);
    gl.uniform3f(gl.getUniformLocation(program, 'u_shadowColor'), 0.1, 0.1, 0.2);
    gl.uniform3f(gl.getUniformLocation(program, 'u_highlightColor'), 1.0, 0.8, 0.6);
    
    this._drawQuad(gl);
  }

  _renderVignette(gl, texture) {
    const program = this._programs.vignette;
    if (!program) return;
    
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(gl.getUniformLocation(program, 'u_texture'), 0);
    gl.uniform1f(gl.getUniformLocation(program, 'u_intensity'), 0.3);
    
    this._drawQuad(gl);
  }

  resize(w, h) {
    this._w = w;
    this._h = h;
    const gl = this.renderer.gl;
    if (gl) this._createFBOs(gl);
  }

  destroy() {
    const gl = this.renderer.gl;
    if (gl) {
      if (this._fboA) {
        gl.deleteTexture(this._fboA.tex);
        gl.deleteFramebuffer(this._fboA.fbo);
      }
      if (this._fboB) {
        gl.deleteTexture(this._fboB.tex);
        gl.deleteFramebuffer(this._fboB.fbo);
      }
    }
    for (const program of Object.values(this._programs)) {
      if (program && gl) {
        gl.deleteProgram(program);
      }
    }
    this._programs = {};
  }
}

const CHROMATIC_ABERRATION_FS = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_texture;
uniform vec2 u_resolution;
uniform float u_intensity;

void main() {
  vec2 center = v_uv - 0.5;
  float dist = length(center);
  vec2 offset = center * dist * u_intensity;
  
  float r = texture(u_texture, v_uv + offset).r;
  float g = texture(u_texture, v_uv).g;
  float b = texture(u_texture, v_uv - offset).b;
  
  fragColor = vec4(r, g, b, 1.0);
}`;

const COLOR_GRADING_FS = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_texture;
uniform vec3 u_shadowColor;
uniform vec3 u_highlightColor;

void main() {
  vec4 color = texture(u_texture, v_uv);
  float luminance = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
  
  vec3 graded = mix(
    color.rgb + u_shadowColor * (1.0 - luminance),
    color.rgb + u_highlightColor * luminance,
    luminance
  );
  
  fragColor = vec4(graded, color.a);
}`;

const VIGNETTE_FS = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_texture;
uniform float u_intensity;

void main() {
  vec4 color = texture(u_texture, v_uv);
  vec2 center = v_uv - 0.5;
  float dist = length(center);
  float vignette = 1.0 - dist * u_intensity;
  vignette = clamp(vignette, 0.0, 1.0);
  
  fragColor = vec4(color.rgb * vignette, color.a);
}`;