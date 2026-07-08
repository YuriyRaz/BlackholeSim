export class ShaderModule {
  constructor(renderer) {
    this.renderer = renderer;
    this._cache = new Map();
  }

  get WGSL() { return this.renderer.backend === 'webgpu'; }

  async compile(name, wgslSource, glslSource) {
    const key = name + (this.WGSL ? '_wgsl' : '_glsl');
    if (this._cache.has(key)) return this._cache.get(key);

    if (this.WGSL) {
      const module = this.renderer.createShaderModule(wgslSource);
      this._cache.set(key, module);
      return module;
    }
    return { source: glslSource, name };
  }

  compileSync(name, wgslSource, glslSource) {
    const key = name + (this.WGSL ? '_wgsl' : '_glsl');
    if (this._cache.has(key)) return this._cache.get(key);

    if (this.WGSL) {
      const module = this.renderer.createShaderModule(wgslSource);
      this._cache.set(key, module);
      return module;
    }
    return { source: glslSource, name };
  }

  compileGL(name, vertexSource, fragmentSource) {
    const gl = this.renderer.gl;
    if (!gl) return null;
    const vs = this._compileGLShader(gl, gl.VERTEX_SHADER, vertexSource, name + '_vert');
    const fs = this._compileGLShader(gl, gl.FRAGMENT_SHADER, fragmentSource, name + '_frag');
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const info = gl.getProgramInfoLog(program);
      gl.deleteProgram(program);
      throw new Error(`Program link error (${name}): ${info}`);
    }
    return program;
  }

  _compileGLShader(gl, type, source, label) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      const stage = type === gl.VERTEX_SHADER ? 'vertex' : 'fragment';
      gl.deleteShader(shader);
      throw new Error(`Shader compile error (${label}, ${stage}): ${info}`);
    }
    return shader;
  }
}
