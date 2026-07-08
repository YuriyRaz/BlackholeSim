(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const s of document.querySelectorAll('link[rel="modulepreload"]'))i(s);new MutationObserver(s=>{for(const r of s)if(r.type==="childList")for(const o of r.addedNodes)o.tagName==="LINK"&&o.rel==="modulepreload"&&i(o)}).observe(document,{childList:!0,subtree:!0});function e(s){const r={};return s.integrity&&(r.integrity=s.integrity),s.referrerPolicy&&(r.referrerPolicy=s.referrerPolicy),s.crossOrigin==="use-credentials"?r.credentials="include":s.crossOrigin==="anonymous"?r.credentials="omit":r.credentials="same-origin",r}function i(s){if(s.ep)return;s.ep=!0;const r=e(s);fetch(s.href,r)}})();class B{constructor(){this._last=performance.now(),this._delta=0,this._elapsed=0}update(){const t=performance.now();return this._delta=(t-this._last)/1e3,this._last=t,this._elapsed+=this._delta,this._delta}reset(){this._delta=0,this._last=performance.now()}get delta(){return this._delta}get elapsed(){return this._elapsed}}class R{constructor(t){this.canvas=t,this._resizeCallbacks=[],this._width=0,this._height=0,this._devicePixelRatio=Math.min(window.devicePixelRatio,2),this._depthTexture=null,this._depthView=null}static async create(t){const e=new R(t),i=navigator.gpu;if(i)try{const r=await i.requestAdapter();if(r)return e._device=await r.requestDevice(),e._context=t.getContext("webgpu"),e._format=navigator.gpu.getPreferredCanvasFormat(),e._context.configure({device:e._device,format:e._format,alphaMode:"opaque"}),e._backend="webgpu",e._resize(),window.addEventListener("resize",()=>e._resize()),e}catch(r){console.warn("WebGPU init failed, falling back to WebGL 2.0",r)}const s=t.getContext("webgl2");return s?(e._gl=s,e._backend="webgl2",e._resize(),window.addEventListener("resize",()=>e._resize()),e):null}get backend(){return this._backend}get device(){return this._device}get gl(){return this._gl}get format(){return this._format}get width(){return this._width}get height(){return this._height}get context(){return this._context}_resize(){const e=(this.canvas.parentElement||document.body).getBoundingClientRect();this._width=Math.floor(e.width*this._devicePixelRatio),this._height=Math.floor(e.height*this._devicePixelRatio),this.canvas.width=this._width,this.canvas.height=this._height,this.canvas.style.width=e.width+"px",this.canvas.style.height=e.height+"px",this._backend==="webgpu"?this._createDepthTexture():this._gl&&this._gl.viewport(0,0,this._width,this._height);for(const i of this._resizeCallbacks)i(this._width,this._height)}_createDepthTexture(){this._depthTexture&&this._depthTexture.destroy(),this._depthTexture=this._device.createTexture({size:[this._width,this._height],format:"depth24plus",usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.TEXTURE_BINDING}),this._depthView=this._depthTexture.createView()}onResize(t){this._resizeCallbacks.push(t),t(this._width,this._height)}beginFrame(){this._backend==="webgpu"?(this._commandEncoder=this._device.createCommandEncoder(),this._passEncoder=null):this._gl&&this._gl.clear(this._gl.COLOR_BUFFER_BIT|this._gl.DEPTH_BUFFER_BIT)}endFrame(){this._backend==="webgpu"?this._device.queue.submit([this._commandEncoder.finish()]):this._gl&&this._gl.flush()}beginRenderPass(t,e=!0){if(this._backend==="webgpu"){const r={colorAttachments:[{view:t,clearValue:{r:0,g:0,b:0,a:1},loadOp:t?"clear":"load",storeOp:"store"}]};return e&&this._depthView&&(r.depthStencilAttachment={view:this._depthView,depthClearValue:1,depthLoadOp:"clear",depthStoreOp:"store"}),this._passEncoder=this._commandEncoder.beginRenderPass(r),this._passEncoder}return null}beginScreenPass(){if(this._backend==="webgpu"){const e={colorAttachments:[{view:this._context.getCurrentTexture().createView(),clearValue:{r:0,g:0,b:0,a:1},loadOp:"clear",storeOp:"store"}]};return this._passEncoder=this._commandEncoder.beginRenderPass(e),this._passEncoder}return null}endRenderPass(){this._passEncoder&&(this._passEncoder.end(),this._passEncoder=null)}createShaderModule(t){return this._backend==="webgpu"?this._device.createShaderModule({code:t}):null}createBindGroupLayout(t){return this._backend==="webgpu"?this._device.createBindGroupLayout({entries:t}):null}createBindGroup(t,e){return this._backend==="webgpu"?this._device.createBindGroup({layout:t,entries:e}):null}createPipelineLayout(t){return this._backend==="webgpu"?this._device.createPipelineLayout({bindGroupLayouts:t}):null}createBuffer(t,e){if(this._backend==="webgpu"){const i=this._device.createBuffer({size:t.byteLength,usage:e,mappedAtCreation:!0});return new Uint8Array(i.getMappedRange()).set(new Uint8Array(t.buffer||t)),i.unmap(),i}return null}createUniformBuffer(t){return this.createBuffer(t,GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST)}writeBuffer(t,e){this._backend==="webgpu"&&this._device.queue.writeBuffer(t,0,e)}createTexture(t,e,i="rgba8unorm",s){return this._backend==="webgpu"?this._device.createTexture({size:[t,e],format:i,usage:s|GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.TEXTURE_BINDING}):null}get screenTexture(){return this._backend==="webgpu"?this._context.getCurrentTexture().createView():null}resizeFramebuffer(t,e){this._depthTexture&&this._backend==="webgpu"&&(this._depthTexture.destroy(),this._depthTexture=this._device.createTexture({size:[t,e],format:"depth24plus",usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.TEXTURE_BINDING}),this._depthView=this._depthTexture.createView())}}class U{constructor(t){this.renderer=t,this._cache=new Map}get WGSL(){return this.renderer.backend==="webgpu"}async compile(t,e,i){const s=t+(this.WGSL?"_wgsl":"_glsl");if(this._cache.has(s))return this._cache.get(s);if(this.WGSL){const r=this.renderer.createShaderModule(e);return this._cache.set(s,r),r}return{source:i,name:t}}compileSync(t,e,i){const s=t+(this.WGSL?"_wgsl":"_glsl");if(this._cache.has(s))return this._cache.get(s);if(this.WGSL){const r=this.renderer.createShaderModule(e);return this._cache.set(s,r),r}return{source:i,name:t}}compileGL(t,e,i){const s=this.renderer.gl;if(!s)return null;const r=this._compileGLShader(s,s.VERTEX_SHADER,e,t+"_vert"),o=this._compileGLShader(s,s.FRAGMENT_SHADER,i,t+"_frag"),n=s.createProgram();if(s.attachShader(n,r),s.attachShader(n,o),s.linkProgram(n),!s.getProgramParameter(n,s.LINK_STATUS)){const a=s.getProgramInfoLog(n);throw s.deleteProgram(n),new Error(`Program link error (${t}): ${a}`)}return n}_compileGLShader(t,e,i,s){const r=t.createShader(e);if(t.shaderSource(r,i),t.compileShader(r),!t.getShaderParameter(r,t.COMPILE_STATUS)){const o=t.getShaderInfoLog(r),n=e===t.VERTEX_SHADER?"vertex":"fragment";throw t.deleteShader(r),new Error(`Shader compile error (${s}, ${n}): ${o}`)}return r}}class D{constructor(t,e){this.renderer=t,this._w=t.width,this._h=t.height,this._fb1=null,this._fb2=null,this._programs={},this._quadVAO=null,this._init()}_init(){this.renderer.backend==="webgl2"&&this._initGL()}_initGL(){const t=this.renderer.gl;this._shaderModule;const e=`#version 300 es
    in vec2 a_pos; out vec2 v_uv;
    void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`;this._programs.tonemap=this._compileProgram(t,e,I),this._programs.bloomPrefilter=this._compileProgram(t,e,k),this._programs.bloomBlur=this._compileProgram(t,e,O),this._programs.bloomCombine=this._compileProgram(t,e,N),this._programs.fxaa=this._compileProgram(t,e,z),this._programs.vignette=this._compileProgram(t,e,G);const i=t.createBuffer();t.bindBuffer(t.ARRAY_BUFFER,i),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW),this._quadVBO=i,this._createFBOs(t)}_createFBOs(t){const e=Math.floor(this._w/2)||1,i=Math.floor(this._h/2)||1;this._fb1=this._createFBO(t,e,i),this._fb2=this._createFBO(t,e,i),this._screenFBO=this._createFBO(t,this._w,this._h)}_createFBO(t,e,i){const s=t.createTexture();t.bindTexture(t.TEXTURE_2D,s),t.texImage2D(t.TEXTURE_2D,0,t.RGBA16F,e,i,0,t.RGBA,t.HALF_FLOAT,null),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE);const r=t.createFramebuffer();return t.bindFramebuffer(t.FRAMEBUFFER,r),t.framebufferTexture2D(t.FRAMEBUFFER,t.COLOR_ATTACHMENT0,t.TEXTURE_2D,s,0),{fbo:r,tex:s,w:e,h:i}}_compileProgram(t,e,i){const s=t.createShader(t.VERTEX_SHADER);t.shaderSource(s,e),t.compileShader(s);const r=t.createShader(t.FRAGMENT_SHADER);t.shaderSource(r,i),t.compileShader(r);const o=t.createProgram();return t.attachShader(o,s),t.attachShader(o,r),t.linkProgram(o),o}_drawQuad(t){t.bindBuffer(t.ARRAY_BUFFER,this._quadVBO),t.enableVertexAttribArray(0),t.vertexAttribPointer(0,2,t.FLOAT,!1,0,0),t.drawArrays(t.TRIANGLE_STRIP,0,4)}render(t,e){const i=this.renderer.gl;i&&(i.disable(i.DEPTH_TEST),i.enable(i.BLEND),i.blendFunc(i.SRC_ALPHA,i.ONE_MINUS_SRC_ALPHA),this._sceneTexture=e,t.bloom&&this._applyBloom(i),t.tonemap&&this._applyTonemap(i),t.fxaa&&this._applyFXAA(i),this._applyVignette(i))}_applyTonemap(t){t.bindFramebuffer(t.FRAMEBUFFER,this._screenFBO.fbo),t.useProgram(this._programs.tonemap),this._sceneTexture&&(t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._sceneTexture),t.uniform1i(t.getUniformLocation(this._programs.tonemap,"u_sceneTex"),0)),this._drawQuad(t)}_applyBloom(t){t.bindFramebuffer(t.FRAMEBUFFER,this._fb1.fbo),t.useProgram(this._programs.bloomPrefilter),this._sceneTexture&&(t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._sceneTexture),t.uniform1i(t.getUniformLocation(this._programs.bloomPrefilter,"u_sceneTex"),0)),this._drawQuad(t);const e=[1/this._fb2.w,0],i=[0,1/this._fb2.h];for(let s=0;s<4;s++)t.bindFramebuffer(t.FRAMEBUFFER,this._fb2.fbo),t.useProgram(this._programs.bloomBlur),t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._fb1.tex),t.uniform1i(t.getUniformLocation(this._programs.bloomBlur,"u_inputTex"),0),t.uniform2fv(t.getUniformLocation(this._programs.bloomBlur,"u_direction"),s%2===0?e:i),this._drawQuad(t),t.bindFramebuffer(t.FRAMEBUFFER,this._fb1.fbo),t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._fb2.tex),t.uniform1i(t.getUniformLocation(this._programs.bloomBlur,"u_inputTex"),0),t.uniform2fv(t.getUniformLocation(this._programs.bloomBlur,"u_direction"),s%2===0?i:e),this._drawQuad(t);t.bindFramebuffer(t.FRAMEBUFFER,this._screenFBO.fbo),t.useProgram(this._programs.bloomCombine),t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._sceneTexture),t.uniform1i(t.getUniformLocation(this._programs.bloomCombine,"u_sceneTex"),0),t.activeTexture(t.TEXTURE1),t.bindTexture(t.TEXTURE_2D,this._fb1.tex),t.uniform1i(t.getUniformLocation(this._programs.bloomCombine,"u_bloomTex"),1),this._drawQuad(t)}_applyFXAA(t){t.bindFramebuffer(t.FRAMEBUFFER,null),t.useProgram(this._programs.fxaa),t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,this._screenFBO.tex),t.uniform1i(t.getUniformLocation(this._programs.fxaa,"u_inputTex"),0),t.uniform2f(t.getUniformLocation(this._programs.fxaa,"u_texelSize"),1/this._w,1/this._h),this._drawQuad(t)}_applyVignette(t){t.useProgram(this._programs.vignette),this._drawQuad(t)}resize(t,e){this._w=t,this._h=e;const i=this.renderer.gl;i&&this._createFBOs(i)}}const I=`#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
vec3 aces(vec3 x){return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0);}
void main(){fragColor=vec4(aces(v_uv),1.0);}`,k=`#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_sceneTex;
uniform vec2 u_texelSize;
void main(){
  vec3 c = texture(u_sceneTex, v_uv).rgb;
  float brightness = dot(c, vec3(0.2126, 0.7152, 0.0722));
  float soft = smoothstep(0.6, 1.0, brightness);
  fragColor = vec4(c * soft, 1.0);
}`,O=`#version 300 es
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
}`,N=`#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
uniform sampler2D u_sceneTex;
uniform sampler2D u_bloomTex;
void main(){
  vec3 scene = texture(u_sceneTex, v_uv).rgb;
  vec3 bloom = texture(u_bloomTex, v_uv).rgb;
  fragColor = vec4(scene + bloom * 0.6, 1.0);
}`,z=`#version 300 es
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
}`,G=`#version 300 es
precision highp float;
in vec2 v_uv; out vec4 fragColor;
void main(){
  float d=length(v_uv-0.5);
  float v=smoothstep(0.8,0.3,d);
  fragColor=vec4(vec3(v),1.0);
}`;class X{constructor(t){this.theta=0,this.phi=Math.PI/4,this.distance=100,this.targetTheta=0,this.targetPhi=Math.PI/4,this.targetDistance=100,this.focusPoint=[0,0,0],this.targetFocus=[0,0,0],this._damping=.08,this._minDist=2,this._maxDist=5e3,this._minPhi=-85*Math.PI/180,this._maxPhi=85*Math.PI/180,this._keys={},this._isOrbiting=!1,this._isPanning=!1,this._lastMouse=[0,0],t.addEventListener("mousedown",e=>this._onMouseDown(e)),t.addEventListener("mousemove",e=>this._onMouseMove(e)),t.addEventListener("mouseup",()=>this._onMouseUp()),t.addEventListener("wheel",e=>this._onWheel(e)),window.addEventListener("keydown",e=>{this._keys[e.key.toLowerCase()]=!0}),window.addEventListener("keyup",e=>{this._keys[e.key.toLowerCase()]=!1})}_onMouseDown(t){t.button===0&&!t.shiftKey?this._isOrbiting=!0:(t.button===2||t.button===0&&t.shiftKey)&&(this._isPanning=!0),this._lastMouse=[t.clientX,t.clientY],t.preventDefault()}_onMouseMove(t){const e=t.clientX-this._lastMouse[0],i=t.clientY-this._lastMouse[1];if(this._lastMouse=[t.clientX,t.clientY],this._isOrbiting&&(this.targetTheta-=e*.005,this.targetPhi=Math.max(this._minPhi,Math.min(this._maxPhi,this.targetPhi-i*.005))),this._isPanning){const s=this._getRight(),r=this._getUp(),o=this.distance*.002;this.targetFocus[0]-=(s[0]*e+r[0]*i)*o,this.targetFocus[1]-=(s[1]*e+r[1]*i)*o,this.targetFocus[2]-=(s[2]*e+r[2]*i)*o}}_onMouseUp(){this._isOrbiting=!1,this._isPanning=!1}_onWheel(t){this.targetDistance*=1+t.deltaY*.001,this.targetDistance=Math.max(this._minDist,Math.min(this._maxDist,this.targetDistance)),t.preventDefault()}_getRight(){return[Math.cos(this.theta),0,Math.sin(this.theta)]}_getUp(){return[0,1,0]}getPosition(){const t=Math.cos(this.phi);return[this.focusPoint[0]+this.distance*t*Math.sin(this.theta),this.focusPoint[1]+this.distance*Math.sin(this.phi),this.focusPoint[2]+this.distance*t*Math.cos(this.theta)]}getDirection(){const t=this.getPosition();return[this.focusPoint[0]-t[0],this.focusPoint[1]-t[1],this.focusPoint[2]-t[2]]}update(t){const e=this.distance*2;this._keys.w&&(this.targetFocus[2]-=e*t),this._keys.s&&(this.targetFocus[2]+=e*t),this._keys.a&&(this.targetFocus[0]-=e*t),this._keys.d&&(this.targetFocus[0]+=e*t),this._keys.q&&(this.targetFocus[1]+=e*t),this._keys.e&&(this.targetFocus[1]-=e*t),this.theta+=(this.targetTheta-this.theta)*this._damping,this.phi+=(this.targetPhi-this.phi)*this._damping,this.distance+=(this.targetDistance-this.distance)*this._damping,this.focusPoint[0]+=(this.targetFocus[0]-this.focusPoint[0])*this._damping,this.focusPoint[1]+=(this.targetFocus[1]-this.focusPoint[1])*this._damping,this.focusPoint[2]+=(this.targetFocus[2]-this.focusPoint[2])*this._damping}setTarget(t,e,i,s){this.targetTheta=t,this.targetPhi=Math.max(this._minPhi,Math.min(this._maxPhi,e)),this.targetDistance=Math.max(this._minDist,Math.min(this._maxDist,i)),s&&(this.targetFocus=[...s])}reset(){this.setTarget(0,Math.PI/4,100,[0,0,0])}}class V{constructor(){this.theta=0,this.phi=Math.PI/6,this.distance=150,this.rpm=.3,this.focusPoint=[0,0,0],this._active=!1,this._userInput=!1,this._inactiveTimer=0}get active(){return this._active}enable(){this._active=!0,this._userInput=!1}disable(){this._active=!1}onUserInput(){this._active&&(this._userInput=!0,this._inactiveTimer=0)}update(t){if(this._active){if(this._userInput){this._inactiveTimer+=t,this._inactiveTimer>3&&(this._userInput=!1);return}this.theta+=this.rpm*2*Math.PI/60*t}}getPosition(){const t=Math.cos(this.phi);return[this.focusPoint[0]+this.distance*t*Math.sin(this.theta),this.focusPoint[1]+this.distance*Math.sin(this.phi),this.focusPoint[2]+this.distance*t*Math.cos(this.theta)]}getDirection(){const t=this.getPosition();return[this.focusPoint[0]-t[0],this.focusPoint[1]-t[1],this.focusPoint[2]-t[2]]}}class W{constructor(t){this.free=new X(t),this.cinematic=new V,this._mode="free",this._transitioning=!1,this._transitionProgress=0,this._transitionDuration=1.5,this._transitionStart=null,this._transitionFrom=null,this._transitionTo=null,this._viewProjection=new Float32Array(16),this._perspective=new Float32Array(16),this._aspect=t.width/t.height||1}get mode(){return this._mode}update(t){if(this._transitioning){if(this._transitionProgress+=t/this._transitionDuration,this._transitionProgress>=1)this._transitionProgress=1,this._transitioning=!1,this.free.theta=this._transitionTo.theta,this.free.phi=this._transitionTo.phi,this.free.distance=this._transitionTo.distance,this.free.focusPoint=[...this._transitionTo.focus],this.free.targetTheta=this.free.theta,this.free.targetPhi=this.free.phi,this.free.targetDistance=this.free.distance,this.free.targetFocus=[...this.free.focusPoint];else{const e=this._easeInOut(this._transitionProgress);this.free.theta=this._lerp(this._transitionFrom.theta,this._transitionTo.theta,e),this.free.phi=this._lerp(this._transitionFrom.phi,this._transitionTo.phi,e),this.free.distance=this._lerp(this._transitionFrom.distance,this._transitionTo.distance,e),this.free.focusPoint[0]=this._lerp(this._transitionFrom.focus[0],this._transitionTo.focus[0],e),this.free.focusPoint[1]=this._lerp(this._transitionFrom.focus[1],this._transitionTo.focus[1],e),this.free.focusPoint[2]=this._lerp(this._transitionFrom.focus[2],this._transitionTo.focus[2],e)}return}this._mode==="cinematic"?(this.cinematic.update(t),this.free.theta=this.cinematic.theta,this.free.phi=this.cinematic.phi,this.free.distance=this.cinematic.distance,this.free.focusPoint=[...this.cinematic.focusPoint]):this.free.update(t)}setMode(t){this._mode=t,t==="cinematic"?(this.cinematic.theta=this.free.theta,this.cinematic.phi=this.free.phi,this.cinematic.distance=this.free.distance,this.cinematic.focusPoint=[...this.free.focusPoint],this.cinematic.enable()):this.cinematic.disable()}transitionTo(t,e,i,s){this._transitioning=!0,this._transitionProgress=0,this._transitionFrom={theta:this.free.theta,phi:this.free.phi,distance:this.free.distance,focus:[...this.free.focusPoint]},this._transitionTo={theta:t,phi:e,distance:i,focus:s||[...this.free.focusPoint]}}setPreset(t){const i={cinematic:{theta:0,phi:Math.PI/6,distance:150,focus:[0,0,0]},topdown:{theta:0,phi:85*Math.PI/180,distance:200,focus:[0,0,0]},edgeon:{theta:0,phi:0,distance:200,focus:[0,0,0]},closeup:{theta:0,phi:Math.PI/6,distance:10,focus:[0,0,0]},system:{theta:0,phi:Math.PI/6,distance:2e3,focus:[0,0,0]}}[t];i&&this.transitionTo(i.theta,i.phi,i.distance,i.focus)}reset(){this.transitionTo(0,Math.PI/4,100,[0,0,0])}getState(){const t=this.free.getPosition(),e=this.free.getDirection(),i=this._normalize(e);return this._updateVP(t,i),{position:t,direction:i,viewProjection:this._viewProjection,focus:[...this.free.focusPoint]}}_normalize(t){const e=Math.sqrt(t[0]*t[0]+t[1]*t[1]+t[2]*t[2]);return e>0?[t[0]/e,t[1]/e,t[2]/e]:[0,0,1]}_updateVP(t,e){const i=60*Math.PI/180,s=.1,r=1e6,o=1/Math.tan(i/2),n=this._aspect,a=this._cross(e,[0,1,0]),l=Math.sqrt(a[0]*a[0]+a[1]*a[1]+a[2]*a[2]),c=l>0?[a[0]/l,a[1]/l,a[2]/l]:[1,0,0],d=this._cross(c,e),p=Math.sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]),f=p>0?[d[0]/p,d[1]/p,d[2]/p]:[0,1,0],u=this._perspective;u[0]=o/n,u[1]=0,u[2]=0,u[3]=0,u[4]=0,u[5]=o,u[6]=0,u[7]=0,u[8]=0,u[9]=0,u[10]=(r+s)/(s-r),u[11]=-1,u[12]=0,u[13]=0,u[14]=2*r*s/(s-r),u[15]=0;const _=this._viewProjection;_[0]=c[0],_[1]=f[0],_[2]=-e[0],_[3]=0,_[4]=c[1],_[5]=f[1],_[6]=-e[1],_[7]=0,_[8]=c[2],_[9]=f[2],_[10]=-e[2],_[11]=0,_[12]=-(c[0]*t[0]+c[1]*t[1]+c[2]*t[2]),_[13]=-(f[0]*t[0]+f[1]*t[1]+f[2]*t[2]),_[14]=e[0]*t[0]+e[1]*t[1]+e[2]*t[2],_[15]=1;const w=new Float32Array(16);this._mul4x4(u,_,w);for(let b=0;b<16;b++)this._viewProjection[b]=w[b]}_cross(t,e){return[t[1]*e[2]-t[2]*e[1],t[2]*e[0]-t[0]*e[2],t[0]*e[1]-t[1]*e[0]]}_mul4x4(t,e,i){for(let s=0;s<4;s++)for(let r=0;r<4;r++){i[r*4+s]=0;for(let o=0;o<4;o++)i[r*4+s]+=t[o*4+s]*e[r*4+o]}}_lerp(t,e,i){return t+(e-t)*i}_easeInOut(t){return t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2}resize(t,e){this._aspect=t/e}screenToWorldRay(t,e){const i=this.free.getPosition(),s=this.free.getDirection(),r=this._normalize(s),o=60*Math.PI/180,n=this._aspect,a=Math.tan(o/2),l=a*n,c=this._cross(r,[0,1,0]),d=Math.sqrt(c[0]*c[0]+c[1]*c[1]+c[2]*c[2]),p=d>0?[c[0]/d,c[1]/d,c[2]/d]:[1,0,0],f=this._cross(p,r),u=[p[0]*(t*2-1)*l+f[0]*(e*2-1)*a+r[0],p[1]*(t*2-1)*l+f[1]*(e*2-1)*a+r[1],p[2]*(t*2-1)*l+f[2]*(e*2-1)*a+r[2]],_=Math.sqrt(u[0]*u[0]+u[1]*u[1]+u[2]*u[2]);return{origin:i,direction:[u[0]/_,u[1]/_,u[2]/_]}}pickObject(t,e){let i=null,s=1/0;for(const r of e){const o=this._raySphereIntersect(t,r.position,r.radius||1);o!==null&&o<s&&(s=o,i=r)}return i}_raySphereIntersect(t,e,i){const s=[t.origin[0]-e[0],t.origin[1]-e[1],t.origin[2]-e[2]],r=t.direction[0]*t.direction[0]+t.direction[1]*t.direction[1]+t.direction[2]*t.direction[2],o=2*(s[0]*t.direction[0]+s[1]*t.direction[1]+s[2]*t.direction[2]),n=s[0]*s[0]+s[1]*s[1]+s[2]*s[2]-i*i,a=o*o-4*r*n;if(a<0)return null;const l=(-o-Math.sqrt(a))/(2*r);return l>0?l:null}}class H{constructor(t){this.cameraManager=t,this._presets=["cinematic","topdown","edgeon","closeup","system"],this._labels=["Cinematic","Top-down","Edge-on","Close-up","System"],this._active="cinematic",this._el=null}mount(t){this._el=document.createElement("div"),this._el.style.display="flex",this._el.style.gap="4px",this._presets.forEach((e,i)=>{const s=document.createElement("button");s.className="ui-btn"+(e===this._active?" active":""),s.textContent=this._labels[i],s.addEventListener("click",()=>this._select(e,s)),this._el.appendChild(s)}),t.appendChild(this._el)}_select(t){this._active=t,this.cameraManager.setPreset(t),this._el.querySelectorAll(".ui-btn").forEach((e,i)=>{e.classList.toggle("active",this._presets[i]===t)})}}class q{constructor(){this._el=null,this._fpsEl=null,this._frameCount=0}mount(t){this._el=document.createElement("div"),this._el.innerHTML=`
      <div><span class="ui-label">FPS: </span><span id="fps-val">0</span></div>
      <div><span class="ui-label">Particles: </span><span id="particle-count">0</span></div>
      <div><span class="ui-label">Mass: </span><span>10 M☉</span></div>
      <div><span class="ui-label">Spin: </span><span>0.7</span></div>
    `,this._fpsEl=this._el.querySelector("#fps-val"),t.appendChild(this._el)}updateFPS(t){this._frameCount++,this._frameCount%10===0&&this._fpsEl&&(this._fpsEl.textContent=Math.round(t))}}class Y{constructor(t){this.settings=t,this._el=null}mount(t){this._el=document.createElement("div"),[["lensing","Lensing"],["particles","Particles"],["stars","Stars"],["bodies","Bodies"],["postProcessing","Post-FX"]].forEach(([i,s])=>{const r=document.createElement("label");r.className="ui-toggle";const o=document.createElement("input");o.type="checkbox",o.checked=this.settings[i],o.addEventListener("change",()=>{this.settings[i]=o.checked});const n=document.createElement("span");n.className="ui-label",n.textContent=s,r.appendChild(o),r.appendChild(n),this._el.appendChild(r)}),t.appendChild(this._el)}}class j{constructor(t){this.quality=t,this._el=null}mount(t){this._el=document.createElement("div"),this._el.style.marginTop="8px";const e=document.createElement("div");e.className="ui-label",e.textContent="Quality",this._el.appendChild(e);const i=["Minimum","Low","Medium","High","Auto"],s=document.createElement("div");s.style.display="flex",s.style.gap="4px",s.style.marginTop="4px",i.forEach(r=>{const o=document.createElement("button");o.className="ui-btn",o.textContent=r.charAt(0),o.title=r,o.addEventListener("click",()=>{this.quality.setMode(r),s.querySelectorAll(".ui-btn").forEach(n=>n.classList.remove("active")),o.classList.add("active")}),r==="Auto"&&o.classList.add("active"),s.appendChild(o)}),this._el.appendChild(s),t.appendChild(this._el)}}class ${constructor(){this._visible=!0,this._el=null,this._create(),setTimeout(()=>this._fadeOut(),5e3),window.addEventListener("keydown",t=>{t.key.toLowerCase()==="h"&&this._toggle()})}_create(){this._el=document.createElement("div"),this._el.className="ui-panel",this._el.style.cssText="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:100;transition:opacity 0.5s;pointer-events:none;",this._el.innerHTML=`
      <div style="text-align:center;">
        <div style="font-size:14px;font-weight:bold;margin-bottom:8px;">Keyboard Shortcuts</div>
        <div>Left drag — Orbit</div>
        <div>Right drag — Pan</div>
        <div>Scroll — Zoom</div>
        <div>WASD/QE — Move camera</div>
        <div>R — Reset camera</div>
        <div>C — Toggle cinematic</div>
        <div>H — Toggle this overlay</div>
      </div>
    `,document.getElementById("app").appendChild(this._el)}_fadeOut(){this._el.style.opacity="0",this._visible=!1}_fadeIn(){this._el.style.opacity="1",this._visible=!0}_toggle(){this._visible?this._fadeOut():this._fadeIn()}}class Q{constructor(){this._el=null,this._phase="idle"}mount(t){this._el=document.createElement("div"),this._el.style.marginTop="8px";const e=document.createElement("div");e.className="ui-label",e.textContent="Phase",this._el.appendChild(e),this._phaseEl=document.createElement("div"),this._phaseEl.style.cssText="color: #8f8; font-weight: bold; margin-top: 2px;",this._phaseEl.textContent="Idle",this._el.appendChild(this._phaseEl),t.appendChild(this._el)}setPhase(t){if(this._phase=t,this._phaseEl){const e={idle:"Idle",inspiral:"Inspiral",merger:"Merger",ringdown:"Ringdown",accretion:"Accretion",collision:"Collision"};this._phaseEl.textContent=e[t]||t}}}class K{constructor(t){this.cameraManager=t,this._el=null}mount(t){this._el=document.createElement("div"),this._el.style.marginTop="8px";const e=document.createElement("div");e.className="ui-label",e.textContent="Camera",this._el.appendChild(e);const i=document.createElement("div");i.style.display="flex",i.style.gap="4px",i.style.marginTop="4px",this._freeBtn=document.createElement("button"),this._freeBtn.className="ui-btn active",this._freeBtn.textContent="Free",this._freeBtn.addEventListener("click",()=>{this.cameraManager.setMode("free"),this._freeBtn.classList.add("active"),this._cinematicBtn.classList.remove("active")}),this._cinematicBtn=document.createElement("button"),this._cinematicBtn.className="ui-btn",this._cinematicBtn.textContent="Cine",this._cinematicBtn.title="Cinematic auto-orbit",this._cinematicBtn.addEventListener("click",()=>{this.cameraManager.setMode("cinematic"),this._cinematicBtn.classList.add("active"),this._freeBtn.classList.remove("active")}),i.appendChild(this._freeBtn),i.appendChild(this._cinematicBtn),this._el.appendChild(i),t.appendChild(this._el)}}class Z{constructor(t){this.quality=t,this._el=null}mount(t){this._el=document.createElement("div"),this._el.style.marginTop="8px";const e=document.createElement("div");e.className="ui-label",e.textContent="Stars",this._el.appendChild(e);const i=document.createElement("div");i.style.display="flex",i.style.alignItems="center",i.style.gap="6px",i.style.marginTop="4px",this._slider=document.createElement("input"),this._slider.type="range",this._slider.min="1000",this._slider.max="5000",this._slider.value=String(this.quality.starCount),this._slider.style.cssText="width: 80px; accent-color: #6af;",this._slider.addEventListener("input",()=>{this.quality.starCount=parseInt(this._slider.value,10),this._valueEl.textContent=this.quality.starCount}),this._valueEl=document.createElement("span"),this._valueEl.style.cssText="font-size: 11px; min-width: 30px;",this._valueEl.textContent=this.quality.starCount,i.appendChild(this._slider),i.appendChild(this._valueEl),this._el.appendChild(i),t.appendChild(this._el)}}class J{constructor({cameraManager:t,quality:e,profiler:i}){this.cameraManager=t,this.quality=e,this.profiler=i,this._displaySettings={lensing:!0,particles:!0,stars:!0,bodies:!0,jets:!0,gwRipples:!0,trails:!0,postProcessing:!0},this._presetSelector=new H(t),this._physicsInfo=new q,this._displayToggles=new Y(this._displaySettings),this._qualitySelector=new j(e),this._keyboardShortcuts=new $,this._phaseIndicator=new Q,this._cameraModeToggle=new K(t),this._starCountControl=new Z(e),this._createCSS(),this._createLayout(),this._createMuteButton()}_createCSS(){const t=document.createElement("style");t.textContent=`
      .ui-panel { position: absolute; color: #eee; font-family: monospace; font-size: 12px;
        background: rgba(0,0,0,0.7); border-radius: 6px; padding: 8px 12px; pointer-events: auto; }
      .ui-top { top: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
      .ui-left { top: 60px; left: 10px; }
      .ui-right { top: 60px; right: 10px; }
      .ui-bottom { bottom: 10px; right: 10px; }
      .ui-btn { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
        color: #eee; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-family: monospace; font-size: 11px; }
      .ui-btn:hover { background: rgba(255,255,255,0.2); }
      .ui-btn.active { background: rgba(100,150,255,0.4); border-color: rgba(100,150,255,0.8); }
      .ui-toggle { display: flex; align-items: center; gap: 6px; margin: 3px 0; cursor: pointer; }
      .ui-toggle input { accent-color: #6af; }
      .ui-label { font-size: 11px; color: #aaa; }
      .mute-btn { position: absolute; bottom: 10px; left: 10px; }
      @media (max-width: 1024px) {
        .ui-btn { padding: 4px 6px; font-size: 10px; }
        .ui-label { display: none; }
      }
    `,document.head.appendChild(t)}_createLayout(){const t=document.getElementById("app");this._topPanel=document.createElement("div"),this._topPanel.className="ui-panel ui-top",t.appendChild(this._topPanel),this._leftPanel=document.createElement("div"),this._leftPanel.className="ui-panel ui-left",t.appendChild(this._leftPanel),this._rightPanel=document.createElement("div"),this._rightPanel.className="ui-panel ui-right",t.appendChild(this._rightPanel),this._bottomPanel=document.createElement("div"),this._bottomPanel.className="ui-panel ui-bottom",t.appendChild(this._bottomPanel),this._presetSelector.mount(this._topPanel),this._physicsInfo.mount(this._leftPanel),this._phaseIndicator.mount(this._leftPanel),this._displayToggles.mount(this._rightPanel),this._qualitySelector.mount(this._rightPanel),this._starCountControl.mount(this._rightPanel),this._cameraModeToggle.mount(this._rightPanel)}_createMuteButton(){const t=document.getElementById("app"),e=document.createElement("button");e.className="ui-btn mute-btn",e.textContent="🔊",e.title="Mute (audio not implemented)",t.appendChild(e)}getDisplaySettings(){return this._displaySettings}updateFPS(t){this._physicsInfo.updateFPS(t)}setPhase(t){this._phaseIndicator.setPhase(t)}}const tt={Minimum:{lensingResolution:"half",lensingSteps:10,particleBudget:6e3,bloom:!1,tonemap:!0,fxaa:!1,vignette:!1},Low:{lensingResolution:"half",lensingSteps:15,particleBudget:12e3,bloom:!0,tonemap:!0,fxaa:!1,vignette:!0},Medium:{lensingResolution:"half",lensingSteps:20,particleBudget:2e4,bloom:!0,tonemap:!0,fxaa:!0,vignette:!0},High:{lensingResolution:"full",lensingSteps:30,particleBudget:35e3,bloom:!0,tonemap:!0,fxaa:!0,vignette:!0}};class et{constructor(t){this.profiler=t,this._mode="Auto",this._currentLevel="Medium",this._lowFrames=0,this._highFrames=0,this._cooldown=0,this._frameSkip=!1,this._skipFrames=0,this._starCount=2e3}get starCount(){return this._starCount}set starCount(t){this._starCount=Math.max(1e3,Math.min(5e3,Math.round(t)))}get mode(){return this._mode}get level(){return this._mode==="Auto"?`Auto (${this._currentLevel})`:this._currentLevel}setMode(t){this._mode=t,t!=="Auto"&&(this._currentLevel=t)}getSettings(){return{...tt[this._currentLevel],starCount:this._starCount,frameSkip:this._frameSkip}}update(){const t=this.profiler.fps;if(this._mode==="Auto"){if(this._cooldown>0){this._cooldown--;return}t<28?(this._lowFrames++,this._highFrames=0):t>55?(this._highFrames++,this._lowFrames=0):(this._lowFrames=0,this._highFrames=0),this._lowFrames>=120?(this._downgrade(),this._lowFrames=0,this._cooldown=120):this._highFrames>=120&&(this._upgrade(),this._highFrames=0,this._cooldown=120),this._currentLevel==="Minimum"&&t<20?(this._skipFrames++,this._skipFrames>=60&&(this._frameSkip=!0)):this._frameSkip&&t>25&&(this._skipFrames++,this._skipFrames>=60&&(this._frameSkip=!1,this._skipFrames=0))}}_downgrade(){const t=["High","Medium","Low","Minimum"],e=t.indexOf(this._currentLevel);e<t.length-1&&(this._currentLevel=t[e+1])}_upgrade(){const t=["High","Medium","Low","Minimum"],e=t.indexOf(this._currentLevel);e>0&&(this._currentLevel=t[e-1])}}class it{constructor(){this._frames=new Float64Array(60),this._index=0,this._count=0,this._fps=0,this._dt=0}update(t){this._dt=t,this._frames[this._index]=t,this._index=(this._index+1)%60,this._count<60&&this._count++;let e=0;for(let i=0;i<this._count;i++)e+=this._frames[i];this._fps=e>0?this._count/e:0}get fps(){return this._fps}get frameTime(){return this._dt*1e3}}class st{constructor(t,e){this.renderer=t,this.shaderModule=e,this._program=null,this._vao=null,this._vbo=null,this._uniforms={},this._maxCount=35e3,this._init()}_init(){this.renderer.backend==="webgl2"&&this._initGL()}_initGL(){const t=this.renderer.gl,e=this.shaderModule;this._program=e.compileGL("particle",`#version 300 es
      layout(location=0) in vec3 a_pos;
      layout(location=1) in vec3 a_color;
      layout(location=2) in float a_size;
      uniform mat4 u_viewProj;
      uniform vec3 u_camPos;
      uniform vec2 u_resolution;
      out vec3 v_color;
      void main() {
        vec4 clip = u_viewProj * vec4(a_pos, 1.0);
        float dist = length(a_pos - u_camPos);
        float ptSize = a_size / max(dist, 1.0) * u_resolution.y * 0.01;
        gl_PointSize = ptSize;
        gl_Position = clip;
        v_color = a_color;
      }`,`#version 300 es
      precision highp float;
      in vec3 v_color; out vec4 fragColor;
      void main() {
        vec2 c = gl_PointCoord - vec2(0.5);
        float d = length(c);
        if (d > 0.5) discard;
        float alpha = 1.0 - smoothstep(0.3, 0.5, d);
        fragColor = vec4(v_color * alpha, alpha);
      }`),["u_viewProj","u_camPos","u_resolution"].forEach(s=>{this._uniforms[s]=t.getUniformLocation(this._program,s)}),this._vbo=t.createBuffer()}render(t,e){if(this.renderer.backend!=="webgl2")return;const i=this.renderer.gl;if(!this._program)return;const s=t.particles||[],r=Math.min(s.length,this._maxCount);if(r===0)return;const o=new Float32Array(r*7);for(let a=0;a<r;a++){const l=s[a],c=a*7;o[c]=l.position[0],o[c+1]=l.position[1],o[c+2]=l.position[2],o[c+3]=l.color[0],o[c+4]=l.color[1],o[c+5]=l.color[2],o[c+6]=l.size||1}i.useProgram(this._program),i.disable(i.DEPTH_TEST),i.enable(i.BLEND),i.blendFunc(i.SRC_ALPHA,i.ONE),i.bindBuffer(i.ARRAY_BUFFER,this._vbo),i.bufferData(i.ARRAY_BUFFER,o,i.DYNAMIC_DRAW);const n=7*4;i.enableVertexAttribArray(0),i.vertexAttribPointer(0,3,i.FLOAT,!1,n,0),i.enableVertexAttribArray(1),i.vertexAttribPointer(1,3,i.FLOAT,!1,n,12),i.enableVertexAttribArray(2),i.vertexAttribPointer(2,1,i.FLOAT,!1,n,24),i.uniformMatrix4fv(this._uniforms.u_viewProj,!1,t.viewProjection),i.uniform3f(this._uniforms.u_camPos,...t.position),i.uniform2f(this._uniforms.u_resolution,this.renderer.width,this.renderer.height),i.drawArrays(i.POINTS,0,r)}resize(){}}class rt{constructor(t,e){this.renderer=t,this.shaderModule=e,this._program=null,this._sphereVAO=null,this._uniforms={},this._sphereData=null,this._init()}_init(){this.renderer.backend==="webgl2"&&this._initGL()}_createSphere(t=16){const e=[];for(let s=0;s<=t;s++){const r=s*Math.PI/t,o=Math.sin(r),n=Math.cos(r);for(let a=0;a<=t;a++){const l=a*2*Math.PI/t;e.push(o*Math.cos(l),n,o*Math.sin(l))}}const i=[];for(let s=0;s<t;s++)for(let r=0;r<t;r++){const o=s*(t+1)+r,n=o+t+1;i.push(o,n,o+1,n,n+1,o+1)}return{vertices:new Float32Array(e),indices:new Uint16Array(i)}}_initGL(){const t=this.renderer.gl;this._program=this.shaderModule.compileGL("body",`#version 300 es
      layout(location=0) in vec3 a_pos;
      uniform mat4 u_viewProj;
      uniform vec3 u_bodyPos;
      uniform float u_bodyRadius;
      out vec3 v_normal;
      out vec3 v_worldPos;
      void main() {
        vec3 wp = a_pos * u_bodyPos + u_bodyPos;
        gl_Position = u_viewProj * vec4(wp, 1.0);
        v_normal = a_pos;
        v_worldPos = wp;
      }`,`#version 300 es
      precision highp float;
      in vec3 v_normal; in vec3 v_worldPos;
      uniform vec3 u_bodyColor; uniform uint u_bodyType; uniform float u_time; uniform vec3 u_camPos;
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
      }`),["u_viewProj","u_bodyPos","u_bodyColor","u_bodyRadius","u_bodyType","u_time","u_camPos"].forEach(i=>{this._uniforms[i]=t.getUniformLocation(this._program,i)}),this._sphereData=this._createSphere(16),this._vbo=t.createBuffer(),this._ebo=t.createBuffer(),t.bindBuffer(t.ARRAY_BUFFER,this._vbo),t.bufferData(t.ARRAY_BUFFER,this._sphereData.vertices,t.STATIC_DRAW),t.bindBuffer(t.ELEMENT_ARRAY_BUFFER,this._ebo),t.bufferData(t.ELEMENT_ARRAY_BUFFER,this._sphereData.indices,t.STATIC_DRAW)}render(t,e){if(this.renderer.backend!=="webgl2")return;const i=this.renderer.gl;if(!this._program)return;const s=t.bodies||[];i.useProgram(this._program),i.enable(i.DEPTH_TEST),i.enable(i.CULL_FACE),i.bindBuffer(i.ARRAY_BUFFER,this._vbo),i.bindBuffer(i.ELEMENT_ARRAY_BUFFER,this._ebo),i.enableVertexAttribArray(0),i.vertexAttribPointer(0,3,i.FLOAT,!1,0,0),i.uniformMatrix4fv(this._uniforms.u_viewProj,!1,t.viewProjection),i.uniform3f(this._uniforms.u_camPos,...t.position),i.uniform1f(this._uniforms.u_time,t.time||0);for(const r of s){const o={blackhole:0,star:1,neutronstar:2};i.uniform3f(this._uniforms.u_bodyPos,...r.position),i.uniform3f(this._uniforms.u_bodyColor,...r.color),i.uniform1f(this._uniforms.u_bodyRadius,r.radius||1),i.uniform1ui(this._uniforms.u_bodyType,o[r.type]||1),i.drawElements(i.TRIANGLES,this._sphereData.indices.length,i.UNSIGNED_SHORT,0)}}resize(){}}class ot{constructor(t,e){this.renderer=t,this.shaderModule=e,this._halfRes=!0,this._stepCount=20,this._program=null,this._fbo=null,this._quadVBO=null,this._uniforms={},this._init()}_init(){this.renderer.backend==="webgl2"?this._initGL():this.renderer.backend==="webgpu"&&this._initWebGPU()}_initGL(){const t=this.renderer.gl,e=this.shaderModule;this._program=e.compileGL("lensing",`#version 300 es
      in vec2 a_pos; out vec2 v_uv;
      void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`,`#version 300 es
      precision highp float;
      uniform sampler2D u_sceneTex;
      uniform vec3 u_camPos;
      uniform vec3 u_camDir;
      uniform vec2 u_resolution;
      uniform int u_stepCount;
      uniform int u_bhCount;
      struct BlackHole { vec3 pos; float mass; float spin; float rs; };
      uniform BlackHole u_bhs[4];
      in vec2 v_uv; out vec4 fragColor;
      vec3 screenRay(vec2 uv) {
        float aspect = u_resolution.x / u_resolution.y;
        vec3 right = normalize(cross(u_camDir, vec3(0.0, 1.0, 0.0)));
        vec3 up = cross(right, u_camDir);
        return normalize((uv.x*2.0-1.0)*aspect*right + (uv.y*2.0-1.0)*up + u_camDir);
      }
      void main() {
        vec3 rayOri = u_camPos;
        vec3 rayDir = screenRay(v_uv);
        float t = 0.0; float dt = 50.0;
        for (int i = 0; i < u_stepCount; i++) {
          vec3 pos = rayOri + rayDir * t;
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
      }`);const i=t.createBuffer();t.bindBuffer(t.ARRAY_BUFFER,i),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW),this._quadVBO=i,this._uniforms={},["u_sceneTex","u_camPos","u_camDir","u_resolution","u_stepCount","u_bhCount"].forEach(r=>{this._uniforms[r]=t.getUniformLocation(this._program,r)});for(let r=0;r<4;r++)this._uniforms[`u_bhs[${r}].pos`]=t.getUniformLocation(this._program,`u_bhs[${r}].pos`),this._uniforms[`u_bhs[${r}].mass`]=t.getUniformLocation(this._program,`u_bhs[${r}].mass`),this._uniforms[`u_bhs[${r}].spin`]=t.getUniformLocation(this._program,`u_bhs[${r}].spin`),this._uniforms[`u_bhs[${r}].rs`]=t.getUniformLocation(this._program,`u_bhs[${r}].rs`);this._createFBO(t)}_createFBO(t){const e=this._halfRes?Math.floor(this.renderer.width/2):this.renderer.width,i=this._halfRes?Math.floor(this.renderer.height/2):this.renderer.height;this._fbo={w:e,h:i};const s=t.createTexture();t.bindTexture(t.TEXTURE_2D,s),t.texImage2D(t.TEXTURE_2D,0,t.RGBA16F,e,i,0,t.RGBA,t.HALF_FLOAT,null),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE);const r=t.createFramebuffer();t.bindFramebuffer(t.FRAMEBUFFER,r),t.framebufferTexture2D(t.FRAMEBUFFER,t.COLOR_ATTACHMENT0,t.TEXTURE_2D,s,0),this._fbo.fbo=r,this._fbo.tex=s}_initWebGPU(){const t=this.shaderModule;this._module=t.compileSync("lensing",`@group(0)@binding(0) var sceneTex: texture_2d<f32>;
       @group(0)@binding(1) var sceneSampler: sampler;
       @group(0)@binding(2) var<uniform> camPos: vec3<f32>;
       @group(0)@binding(3) var<uniform> camDir: vec3<f32>;
       @group(0)@binding(4) var<uniform> resolution: vec2<f32>;
       @group(0)@binding(5) var<uniform> stepCount: u32;
       @group(0)@binding(6) var<uniform> bhCount: u32;
       struct BlackHole { pos: vec3<f32>; mass: f32; spin: f32; rs: f32; _p1: f32; _p2: f32; };
       @group(0)@binding(7) var<uniform> bhs: array<BlackHole,4>;
       struct VSOut { @builtin(position) pos: vec4<f32>; @location(0) uv: vec2<f32>; };
       @vertex fn vs(@builtin(vertex_index) vi: u32) -> VSOut {
         var o: VSOut; let x = f32(i32(vi&1u)*2-1); let y = f32(i32(vi>>1u)*2-1);
         o.pos = vec4<f32>(x,y,0,1); o.uv = vec2<f32>((x+1)*0.5,(1-y)*0.5); return o;
       }
       @fragment fn fs(in: VSOut) -> @location(0) vec4<f32> {
         var ro = camPos; var rd = normalize(vec3<f32>((in.uv.x*2-1),(in.uv.y*2-1),1));
         var t = 0f; for(var i:u32=0u;i<stepCount;i++){
           let p = ro+rd*t; var absorbed = false;
           for(var b:u32=0u;b<bhCount;b++){
             let d = p-bhs[b].pos; let dist=length(d);
             if(dist<bhs[b].rs*0.5){absorbed=true;break;}
             if(dist<bhs[b].rs*50){let a=bhs[b].rs/dist; rd=normalize(rd+normalize(d)*a*0.5);}
           }
           if(absorbed){return vec4<f32>(0,0,0,1);}
           t+=50; if(t>1e6){break;}
         }
         return textureSample(sceneTex,sceneSampler,in.uv);
       }`,"")}render(t,e,i,s){this._halfRes=e.lensingResolution==="half",this._stepCount=e.lensingSteps,this.renderer.backend==="webgl2"&&this._renderGL(t,e,i)}_renderGL(t,e,i){const s=this.renderer.gl,r=this._halfRes?this._fbo:{fbo:null,w:this.renderer.width,h:this.renderer.height};if(this._halfRes&&(!this._fbo||this._fbo.w!==Math.floor(this.renderer.width/2))&&this._createFBO(s),s.bindFramebuffer(s.FRAMEBUFFER,r.fbo),s.viewport(0,0,r.w,r.h),s.useProgram(this._program),s.disable(s.DEPTH_TEST),s.activeTexture(s.TEXTURE0),s.bindTexture(s.TEXTURE_2D,i),s.uniform1i(this._uniforms.u_sceneTex,0),s.uniform3f(this._uniforms.u_camPos,...t.position),s.uniform3f(this._uniforms.u_camDir,...t.direction),s.uniform2f(this._uniforms.u_resolution,this.renderer.width,this.renderer.height),s.uniform1i(this._uniforms.u_stepCount,this._stepCount),s.uniform1i(this._uniforms.u_bhCount,t.blackHoles?.length||0),t.blackHoles)for(let o=0;o<Math.min(t.blackHoles.length,4);o++){const n=t.blackHoles[o];s.uniform3f(this._uniforms[`u_bhs[${o}].pos`],...n.position),s.uniform1f(this._uniforms[`u_bhs[${o}].mass`],n.mass),s.uniform1f(this._uniforms[`u_bhs[${o}].spin`],n.spin),s.uniform1f(this._uniforms[`u_bhs[${o}].rs`],n.rs)}s.bindBuffer(s.ARRAY_BUFFER,this._quadVBO),s.enableVertexAttribArray(0),s.vertexAttribPointer(0,2,s.FLOAT,!1,0,0),s.drawArrays(s.TRIANGLE_STRIP,0,4),this._halfRes&&(s.bindFramebuffer(s.FRAMEBUFFER,null),s.viewport(0,0,this.renderer.width,this.renderer.height),s.bindTexture(s.TEXTURE_2D,this._fbo.tex),s.drawArrays(s.TRIANGLE_STRIP,0,4))}resize(t,e){this.renderer.backend==="webgl2"&&this._createFBO(this.renderer.gl)}}class nt{constructor(t,e){this.renderer=t,this.shaderModule=e,this._program=null,this._quadVBO=null,this._texture=null,this._uniforms={},this._init()}get texture(){return this._texture}_init(){this.renderer.backend==="webgl2"&&this._initGL()}_initGL(){const t=this.renderer.gl,e=this.shaderModule;this._program=e.compileGL("starfield",`#version 300 es
      in vec2 a_pos; out vec2 v_uv;
      void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`,`#version 300 es
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
      }`);const i=t.createBuffer();t.bindBuffer(t.ARRAY_BUFFER,i),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW),this._quadVBO=i,["u_camDir","u_resolution","u_starCount","u_time","u_nebulaTex"].forEach(r=>{this._uniforms[r]=t.getUniformLocation(this._program,r)}),this._texture=this._createNebulaTexture(t)}_createNebulaTexture(t){const e=t.createTexture();t.bindTexture(t.TEXTURE_2D,e);const i=64,s=32,r=new Uint8Array(i*s*4);for(let o=0;o<s;o++)for(let n=0;n<i;n++){const a=(o*i+n)*4,l=Math.sin(n*.3+o*.1)*.3+.1,c=Math.sin(n*.2+o*.15)*.2+.05,d=Math.cos(n*.1+o*.3)*.4+.2;r[a]=Math.floor(Math.max(0,Math.min(1,l))*255),r[a+1]=Math.floor(Math.max(0,Math.min(1,c))*255),r[a+2]=Math.floor(Math.max(0,Math.min(1,d))*255),r[a+3]=255}return t.texImage2D(t.TEXTURE_2D,0,t.RGBA,i,s,0,t.RGBA,t.UNSIGNED_BYTE,r),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.REPEAT),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),e}render(t,e,i){if(this.renderer.backend!=="webgl2")return;const s=this.renderer.gl;s.disable(s.DEPTH_TEST),s.useProgram(this._program),s.uniform3f(this._uniforms.u_camDir,...t.direction),s.uniform2f(this._uniforms.u_resolution,this.renderer.width,this.renderer.height),s.uniform1i(this._uniforms.u_starCount,e.starCount),s.uniform1f(this._uniforms.u_time,i),s.activeTexture(s.TEXTURE0),s.bindTexture(s.TEXTURE_2D,this._texture),s.uniform1i(this._uniforms.u_nebulaTex,0),s.bindBuffer(s.ARRAY_BUFFER,this._quadVBO),s.enableVertexAttribArray(0),s.vertexAttribPointer(0,2,s.FLOAT,!1,0,0),s.drawArrays(s.TRIANGLE_STRIP,0,4)}resize(){}}const F=document.getElementById("viewport"),g=new B,m=await R.create(F);if(!m)throw document.body.innerHTML='<div style="color:#fff;font-size:24px;text-align:center;margin-top:40vh">WebGPU and WebGL 2.0 are not supported in this browser.</div>',new Error("No GPU backend available");const T=new it,x=new et(T),E=new W(F),v=new U(m),A=new ot(m,v),P=new nt(m,v),M=new st(m,v),C=new rt(m,v),L=new D(m,v),y=new J({cameraManager:E,quality:x,profiler:T});m.onResize((h,t)=>{E.resize(h,t),A.resize(h,t),P.resize(h,t),M.resize(h,t),C.resize(h,t),L.resize(h,t)});document.addEventListener("visibilitychange",()=>{document.hidden&&g.reset()});function S(){requestAnimationFrame(S);const h=g.update();if(h<=0)return;T.update(h),x.update(),E.update(h);const t=E.getState(),e=x.getSettings(),i=y.getDisplaySettings();m.beginFrame(),i.stars&&P.render(t,e,g.elapsed),i.lensing&&A.render(t,e,P.texture,g.elapsed),i.particles&&M.render(t,e),i.bodies&&C.render(t,e),i.postProcessing&&L.render(e),m.endFrame(),y.updateFPS(T.fps)}S();
