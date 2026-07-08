@group(0) @binding(0) var<uniform> viewProj: mat4x4<f32>;
@group(0) @binding(1) var<uniform> bodyPos: vec3<f32>;
@group(0) @binding(2) var<uniform> bodyColor: vec3<f32>;
@group(0) @binding(3) var<uniform> bodyRadius: f32;
@group(0) @binding(4) var<uniform> bodyType: u32;
@group(0) @binding(5) var<uniform> time: f32;

struct VSOut { @builtin(position) pos: vec4<f32>, @location(0) normal: vec3<f32>, @location(1) worldPos: vec3<f32> };

@vertex
fn vs(@location(0) inPos: vec3<f32>) -> VSOut {
  let worldPos = vec4<f32>(inPos * bodyRadius + bodyPos, 1.0);
  var out: VSOut;
  out.pos = viewProj * worldPos;
  out.normal = inPos;
  out.worldPos = worldPos.xyz;
  return out;
}

@fragment
fn fs(in: VSOut) -> @location(0) vec4<f32> {
  let n = normalize(in.normal);
  let light = normalize(vec3<f32>(1.0, 1.0, 1.0));
  let diff = max(dot(n, light), 0.1);
  let col = bodyColor * diff;

  if (bodyType == 0u) {
    return vec4<f32>(0.0, 0.0, 0.0, 1.0);
  } else if (bodyType == 1u) {
    let viewDir = normalize(camPos - in.worldPos);
    let rim = 1.0 - max(dot(viewDir, n), 0.0);
    let corona = pow(rim, 3.0) * 0.5;
    return vec4<f32>(col + vec3<f32>(corona * 0.5, corona * 0.3, corona), 1.0);
  } else if (bodyType == 2u) {
    let beam = pow(max(dot(n, vec3<f32>(0.0, 1.0, 0.0)), 0.0), 8.0);
    let pulse = 0.5 + 0.5 * sin(time * 10.0);
    return vec4<f32>(col + vec3<f32>(beam * pulse), 1.0);
  }
  return vec4<f32>(col, 1.0);
}
