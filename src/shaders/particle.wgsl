@struct Particle { pos: vec3<f32>, vel: vec3<f32>, color: vec3<f32>, size: f32 };

@group(0) @binding(0) var<storage, read> particles: array<Particle>;
@group(0) @binding(1) var<uniform> viewProj: mat4x4<f32>;
@group(0) @binding(2) var<uniform> camPos: vec3<f32>;
@group(0) @binding(3) var<uniform> resolution: vec2<f32>;
@group(0) @binding(4) var<uniform> maxCount: u32;

struct VSOut { @builtin(position) pos: vec4<f32>, @location(0) color: vec4<f32>, @location(1) pointSize: f32 };

@vertex
fn vs(@builtin(vertex_index) vi: u32) -> VSOut {
  let idx = vi;
  if (idx >= maxCount) { return VSOut(vec4<f32>(0.0, 0.0, -2.0, 1.0), vec4<f32>(0.0), 0.0); }
  let p = particles[idx];
  let worldPos = vec4<f32>(p.pos, 1.0);
  let clipPos = viewProj * worldPos;
  let dist = length(p.pos - camPos);
  let ptSize = p.size / max(dist, 1.0) * resolution.y * 0.01;
  return VSOut(clipPos, vec4<f32>(p.color, 1.0), ptSize);
}

@fragment
fn fs(in: VSOut) -> @location(0) vec4<f32> {
  let center = vec2<f32>(0.5);
  let p = gl_FragCoord.xy / resolution;
  let d = length(p - center);
  if (d > 0.5) { discard; }
  let alpha = 1.0 - smoothstep(0.3, 0.5, d);
  return vec4<f32>(in.color.rgb * alpha, alpha);
}
