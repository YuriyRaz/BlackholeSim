export class RenderPass {
  constructor(renderer, framebuffer = null) {
    this.renderer = renderer;
    this.framebuffer = framebuffer;
  }

  begin(colorTexture) {
    if (this.renderer.backend === 'webgpu') {
      const view = colorTexture || (this.framebuffer ? this.framebuffer.createView() : null);
      return this.renderer.beginRenderPass(view);
    }
    if (this.renderer.gl && this.framebuffer) {
      const gl = this.renderer.gl;
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer.fbo || this.framebuffer);
      gl.viewport(0, 0, this.framebuffer.w || this.renderer.width, this.framebuffer.h || this.renderer.height);
    }
    return null;
  }

  end() {
    this.renderer.endRenderPass();
  }
}
