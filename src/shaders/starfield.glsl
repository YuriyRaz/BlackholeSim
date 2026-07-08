#version 300 es
precision highp float;

uniform vec3 u_camDir;
uniform vec2 u_resolution;
uniform int u_starCount;
uniform float u_time;
uniform samplerCube u_skyboxTex;

in vec2 v_uv;
out vec4 fragColor;

float hash31(vec3 p) {
  return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453);
}

vec3 starField(vec3 dir) {
  float cellSize = 0.02;
  vec3 cell = floor(dir / cellSize);
  vec3 local = fract(dir / cellSize) - 0.5;
  vec3 col = vec3(0.0);

  for (int dx = -1; dx <= 1; dx++) {
    for (int dy = -1; dy <= 1; dy++) {
      for (int dz = -1; dz <= 1; dz++) {
        vec3 offset = vec3(float(dx), float(dy), float(dz));
        vec3 cellId = cell + offset;
        float h = hash31(cellId);
        if (h * 5000.0 > float(u_starCount)) continue;

        vec3 starPos = vec3(
          hash31(cellId + vec3(1.0, 0.0, 0.0)) - 0.5,
          hash31(cellId + vec3(0.0, 1.0, 0.0)) - 0.5,
          hash31(cellId + vec3(0.0, 0.0, 1.0)) - 0.5
        );
        vec3 diff = local - offset - starPos;
        float d = length(diff);

        float tempHash = hash31(cellId + vec3(7.0, 13.0, 23.0));
        vec3 starColor;
        if (tempHash < 0.3) starColor = vec3(0.7, 0.8, 1.0);
        else if (tempHash < 0.7) starColor = vec3(1.0);
        else starColor = vec3(1.0, 0.8, 0.6);

        float freq = 0.5 + hash31(cellId + vec3(31.0)) * 1.5;
        float phase = hash31(cellId + vec3(47.0)) * 6.28;
        float twinkle = 1.0 + 0.3 * sin(u_time * freq * 6.28 + phase);

        float brightness = exp(-d * d * 200.0) * twinkle;
        col += starColor * brightness * 10.0;
      }
    }
  }
  return col;
}

void main() {
  float aspect = u_resolution.x / u_resolution.y;
  float halfH = 0.5;
  float halfW = halfH * aspect;
  vec3 localDir = normalize(vec3(
    (v_uv.x * 2.0 - 1.0) * halfW,
    (v_uv.y * 2.0 - 1.0) * halfH,
    1.0
  ));
  vec3 right = normalize(cross(u_camDir, vec3(0.0, 1.0, 0.0)));
  vec3 up = cross(right, u_camDir);
  vec3 dir = normalize(localDir.x * right + localDir.y * up + localDir.z * u_camDir);

  vec3 bg = texture(u_skyboxTex, dir).rgb;
  vec3 stars = starField(dir);
  fragColor = vec4(bg + stars, 1.0);
}
