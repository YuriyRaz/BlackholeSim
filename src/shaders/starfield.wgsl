@group(0) @binding(0) var<uniform> camDir: vec3<f32>;
@group(0) @binding(1) var<uniform> resolution: vec2<f32>;
@group(0) @binding(2) var<uniform> starCount: u32;
@group(0) @binding(3) var<uniform> time: f32;
@group(0) @binding(4) var skyboxTex: texture_cube<f32>;
@group(0) @binding(5) var skyboxSampler: sampler;

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

fn hash31(p: vec3<f32>) -> f32 {
  var h = fract(sin(dot(p, vec3<f32>(127.1, 311.7, 74.7))) * 43758.5453);
  return h;
}

fn starField(dir: vec3<f32>) -> vec3<f32> {
  let cellSize = 0.02;
  let cell = floor(dir / cellSize);
  let local = fract(dir / cellSize) - 0.5;

  var col = vec3<f32>(0.0);
  for (var dx: i32 = -1; dx <= 1; dx++) {
    for (var dy: i32 = -1; dy <= 1; dy++) {
      for (var dz: i32 = -1; dz <= 1; dz++) {
        let offset = vec3<f32>(f32(dx), f32(dy), f32(dz));
        let cellId = cell + offset;
        let h = hash31(cellId);

        if (h * 5000.0 > f32(starCount)) { continue; }

        let starPos = vec3<f32>(
          hash31(cellId + vec3<f32>(1.0, 0.0, 0.0)) - 0.5,
          hash31(cellId + vec3<f32>(0.0, 1.0, 0.0)) - 0.5,
          hash31(cellId + vec3<f32>(0.0, 0.0, 1.0)) - 0.5
        );
        let diff = local - offset - starPos;
        let d = length(diff);

        let tempHash = hash31(cellId + vec3<f32>(7.0, 13.0, 23.0));
        var starColor: vec3<f32>;
        if (tempHash < 0.3) { starColor = vec3<f32>(0.7, 0.8, 1.0); }
        else if (tempHash < 0.7) { starColor = vec3<f32>(1.0); }
        else { starColor = vec3<f32>(1.0, 0.8, 0.6); }

        let freq = 0.5 + hash31(cellId + vec3<f32>(31.0)) * 1.5;
        let phase = hash31(cellId + vec3<f32>(47.0)) * 6.28;
        let twinkle = 1.0 + 0.3 * sin(time * freq * 6.28 + phase);

        let brightness = exp(-d * d * 200.0) * twinkle;
        col += starColor * brightness * 10.0;
      }
    }
  }
  return col;
}

@fragment
fn fs(in: VSOut) -> @location(0) vec4<f32> {
  let aspect = resolution.x / resolution.y;
  let halfH = 0.5;
  let halfW = halfH * aspect;
  let localDir = normalize(vec3<f32>(
    (in.uv.x * 2.0 - 1.0) * halfW,
    (in.uv.y * 2.0 - 1.0) * halfH,
    1.0
  ));
  let right = normalize(cross(camDir, vec3<f32>(0.0, 1.0, 0.0)));
  let up = cross(right, camDir);
  let dir = normalize(localDir.x * right + localDir.y * up + localDir.z * camDir);

  let bg = textureSample(skyboxTex, skyboxSampler, dir);
  let stars = starField(dir);
  let col = bg.rgb + stars;
  return vec4<f32>(col, 1.0);
}
