@group(0) @binding(0) var sceneTex: texture_2d<f32>;
@group(0) @binding(1) var sceneSampler: sampler;
@group(0) @binding(2) var<uniform> camPos: vec3<f32>;
@group(0) @binding(3) var<uniform> camDir: vec3<f32>;
@group(0) @binding(4) var<uniform> resolution: vec2<f32>;
@group(0) @binding(5) var<uniform> stepCount: u32;
@group(0) @binding(6) var<uniform> bhCount: u32;

struct BlackHole { pos: vec3<f32>, mass: f32, spin: f32, rs: f32, _pad1: f32, _pad2: f32 };
@group(0) @binding(7) var<uniform> bhs: array<BlackHole, 4>;

struct VSOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) vi: u32) -> VSOut {
  var out: VSOut;
  let x = f32(i32(vi & 1u) * 2 - 1);
  let y = f32(i32(vi >> 1u) * 2 - 1);
  out.pos = vec4<f32>(x, y, 0.0, 1.0);
  out.uv = vec2<f32>((x + 1.0) * 0.5, (1.0 - y) * 0.5);
  return out;
}

fn screenRay(uv: vec2<f32>) -> vec3<f32> {
  let aspect = resolution.x / resolution.y;
  let fov = 1.0;
  let halfH = fov * 0.5;
  let halfW = halfH * aspect;
  let dir = normalize(vec3<f32>(
    (uv.x * 2.0 - 1.0) * halfW,
    (uv.y * 2.0 - 1.0) * halfH,
    1.0
  ));
  let right = normalize(cross(camDir, vec3<f32>(0.0, 1.0, 0.0)));
  let up = cross(right, camDir);
  return normalize(dir.x * right + dir.y * up + dir.z * camDir);
}

fn hash(p: vec3<f32>) -> f32 {
  var h = dot(p, vec3<f32>(127.1, 311.7, 74.7));
  h = fract(sin(h) * 43758.5453123);
  return h;
}

@fragment
fn fs(in: VSOut) -> @location(0) vec4<f32> {
  var rayOri = camPos;
  var rayDir = screenRay(in.uv);
  var t = 0.0;
  let farPlane = 1e6;
  let dt = 50.0;

  for (var i: u32 = 0u; i < stepCount; i++) {
    let pos = rayOri + rayDir * t;
    var hit = false;
    var absorbed = false;

    var photonBrightness = 0.0;

    for (var bh: u32 = 0u; bh < bhCount; bh++) {
      let d = pos - bhs[bh].pos;
      let dist = length(d);
      let rs = bhs[bh].rs;

      if (dist < rs * 0.5) {
        absorbed = true;
        break;
      }

      if (dist < rs * 1.6 && dist > rs * 1.4) {
        let ringFactor = 1.0 - abs(dist - rs * 1.5) / (rs * 0.1);
        photonBrightness = max(photonBrightness, ringFactor);
      }

      if (dist < rs * 50.0) {
        let deflAngle = rs / dist;
        let toBH = normalize(d);
        let right = normalize(cross(rayDir, toBH));
        rayDir = normalize(rayDir + toBH * deflAngle * dt * 0.001);
        hit = true;

        if (bhs[bh].spin > 0.0) {
          let tangential = cross(vec3<f32>(0.0, 1.0, 0.0), d);
          rayDir = normalize(rayDir + normalize(tangential) * bhs[bh].spin * rs / (dist * dist) * dt * 0.0001);
        }
      }
    }

    if (absorbed) { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }

    t += dt;
    if (t > farPlane) { break; }
  }

  var bgColor = textureSample(sceneTex, sceneSampler, in.uv);
  if (photonBrightness > 0.0) {
    let ringColor = vec3<f32>(1.0, 0.95, 0.8) * photonBrightness * 2.5;
    bgColor = vec4<f32>(bgColor.rgb + ringColor, 1.0);
  }
  return bgColor;
}
