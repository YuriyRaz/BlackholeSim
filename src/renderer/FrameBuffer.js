export class FrameBuffer {
  constructor(renderer, width, height, format = 'rgba8unorm') {
    this.renderer = renderer;
    this.width = width;
    this.height = height;

    if (renderer.backend === 'webgpu') {
      this.texture = renderer.createTexture(width, height, format,
        GPUTextureUsage.TEXTURE_BINDING);
      this.view = this.texture.createView();
    } else if (renderer.gl) {
      this._initGL(renderer.gl, format);
    }
  }

  _initGL(gl, format) {
    this.tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, this.width, this.height, 0, gl.RGBA, gl.HALF_FLOAT, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.tex, 0);
  }

  bind() {
    if (this.renderer.gl) {
      this.renderer.gl.bindFramebuffer(this.renderer.gl.FRAMEBUFFER, this.fbo);
      this.renderer.gl.viewport(0, 0, this.width, this.height);
    }
  }

  unbind() {
    if (this.renderer.gl) {
      this.renderer.gl.bindFramebuffer(this.renderer.gl.FRAMEBUFFER, null);
    }
  }

  resize(w, h) {
    this.width = w;
    this.height = h;
    if (this.renderer.backend === 'webgpu') {
      this.texture?.destroy?.();
      this.texture = this.renderer.createTexture(w, h, 'rgba8unorm', GPUTextureUsage.TEXTURE_BINDING);
      this.view = this.texture.createView();
    }
  }
}
