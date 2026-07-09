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

  render(sceneTexture) {
    const gl = this.renderer.gl;
    if (!gl) return;
    
    gl.disable(gl.DEPTH_TEST);
    
    if (this._enabled.chromaticAberration) {
      this._renderChromaticAberration(gl, sceneTexture);
    }
    
    if (this._enabled.colorGrading) {
      this._renderColorGrading(gl, sceneTexture);
    }
    
    if (this._enabled.vignette) {
      this._renderVignette(gl, sceneTexture);
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
  }

  destroy() {
    for (const program of Object.values(this._programs)) {
      if (program && this.renderer.gl) {
        this.renderer.gl.deleteProgram(program);
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