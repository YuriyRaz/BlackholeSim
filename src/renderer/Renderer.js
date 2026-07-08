export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this._resizeCallbacks = [];
    this._width = 0;
    this._height = 0;
    this._devicePixelRatio = Math.min(window.devicePixelRatio, 2);
    this._depthTexture = null;
    this._depthView = null;
  }

  static async create(canvas) {
    const r = new Renderer(canvas);
    const gpu = navigator.gpu;
    if (gpu) {
      try {
        const adapter = await gpu.requestAdapter();
        if (adapter) {
          r._device = await adapter.requestDevice();
          r._context = canvas.getContext('webgpu');
          r._format = navigator.gpu.getPreferredCanvasFormat();
          r._context.configure({
            device: r._device,
            format: r._format,
            alphaMode: 'opaque'
          });
          r._backend = 'webgpu';
          r._resize();
          window.addEventListener('resize', () => r._resize());
          return r;
        }
      } catch (e) {
        console.warn('WebGPU init failed, falling back to WebGL 2.0', e);
      }
    }
    const gl = canvas.getContext('webgl2');
    if (gl) {
      r._gl = gl;
      r._backend = 'webgl2';
      r._resize();
      window.addEventListener('resize', () => r._resize());
      return r;
    }
    return null;
  }

  get backend() { return this._backend; }
  get device() { return this._device; }
  get gl() { return this._gl; }
  get format() { return this._format; }
  get width() { return this._width; }
  get height() { return this._height; }
  get context() { return this._context; }

  _resize() {
    const parent = this.canvas.parentElement || document.body;
    const rect = parent.getBoundingClientRect();
    this._width = Math.floor(rect.width * this._devicePixelRatio);
    this._height = Math.floor(rect.height * this._devicePixelRatio);
    this.canvas.width = this._width;
    this.canvas.height = this._height;
    this.canvas.style.width = rect.width + 'px';
    this.canvas.style.height = rect.height + 'px';

    if (this._backend === 'webgpu') {
      this._createDepthTexture();
    } else if (this._gl) {
      this._gl.viewport(0, 0, this._width, this._height);
    }
    for (const cb of this._resizeCallbacks) cb(this._width, this._height);
  }

  _createDepthTexture() {
    if (this._depthTexture) this._depthTexture.destroy();
    this._depthTexture = this._device.createTexture({
      size: [this._width, this._height],
      format: 'depth24plus',
      usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING
    });
    this._depthView = this._depthTexture.createView();
  }

  onResize(cb) { this._resizeCallbacks.push(cb); cb(this._width, this._height); }

  beginFrame() {
    if (this._backend === 'webgpu') {
      this._commandEncoder = this._device.createCommandEncoder();
      this._passEncoder = null;
    } else if (this._gl) {
      this._gl.clear(this._gl.COLOR_BUFFER_BIT | this._gl.DEPTH_BUFFER_BIT);
    }
  }

  endFrame() {
    if (this._backend === 'webgpu') {
      this._device.queue.submit([this._commandEncoder.finish()]);
    } else if (this._gl) {
      this._gl.flush();
    }
  }

  beginRenderPass(colorAttachment, depth = true) {
    if (this._backend === 'webgpu') {
      const loadOp = colorAttachment ? 'clear' : 'load';
      const colorValue = { r: 0, g: 0, b: 0, a: 1 };
      const desc = {
        colorAttachments: [{
          view: colorAttachment,
          clearValue: colorValue,
          loadOp,
          storeOp: 'store'
        }]
      };
      if (depth && this._depthView) {
        desc.depthStencilAttachment = {
          view: this._depthView,
          depthClearValue: 1.0,
          depthLoadOp: 'clear',
          depthStoreOp: 'store'
        };
      }
      this._passEncoder = this._commandEncoder.beginRenderPass(desc);
      return this._passEncoder;
    }
    return null;
  }

  beginScreenPass() {
    if (this._backend === 'webgpu') {
      const view = this._context.getCurrentTexture().createView();
      const desc = {
        colorAttachments: [{
          view,
          clearValue: { r: 0, g: 0, b: 0, a: 1 },
          loadOp: 'clear',
          storeOp: 'store'
        }]
      };
      this._passEncoder = this._commandEncoder.beginRenderPass(desc);
      return this._passEncoder;
    }
    return null;
  }

  endRenderPass() {
    if (this._passEncoder) {
      this._passEncoder.end();
      this._passEncoder = null;
    }
  }

  createShaderModule(source) {
    if (this._backend === 'webgpu') {
      return this._device.createShaderModule({ code: source });
    }
    return null;
  }

  createBindGroupLayout(entries) {
    if (this._backend === 'webgpu') {
      return this._device.createBindGroupLayout({ entries });
    }
    return null;
  }

  createBindGroup(layout, entries) {
    if (this._backend === 'webgpu') {
      return this._device.createBindGroup({ layout, entries });
    }
    return null;
  }

  createPipelineLayout(bindGroupLayouts) {
    if (this._backend === 'webgpu') {
      return this._device.createPipelineLayout({ bindGroupLayouts });
    }
    return null;
  }

  createBuffer(data, usage) {
    if (this._backend === 'webgpu') {
      const buffer = this._device.createBuffer({
        size: data.byteLength,
        usage,
        mappedAtCreation: true
      });
      new Uint8Array(buffer.getMappedRange()).set(new Uint8Array(data.buffer || data));
      buffer.unmap();
      return buffer;
    }
    return null;
  }

  createUniformBuffer(data) {
    return this.createBuffer(data, GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST);
  }

  writeBuffer(buffer, data) {
    if (this._backend === 'webgpu') {
      this._device.queue.writeBuffer(buffer, 0, data);
    }
  }

  createTexture(width, height, format = 'rgba8unorm', usage) {
    if (this._backend === 'webgpu') {
      return this._device.createTexture({
        size: [width, height],
        format,
        usage: usage | GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING
      });
    }
    return null;
  }

  get screenTexture() {
    if (this._backend === 'webgpu') {
      return this._context.getCurrentTexture().createView();
    }
    return null;
  }

  resizeFramebuffer(w, h) {
    if (this._depthTexture && this._backend === 'webgpu') {
      this._depthTexture.destroy();
      this._depthTexture = this._device.createTexture({
        size: [w, h],
        format: 'depth24plus',
        usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING
      });
      this._depthView = this._depthTexture.createView();
    }
  }
}
