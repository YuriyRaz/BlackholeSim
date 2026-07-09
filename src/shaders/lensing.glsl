#version 300 es
precision highp float;

uniform sampler2D u_sceneTex;
uniform vec3 u_camPos;
uniform vec3 u_camDir;
uniform vec2 u_resolution;
uniform int u_stepCount;
uniform int u_bhCount;
uniform vec3 u_gwSourcePosition;
uniform float u_gwFrequency;
uniform float u_gwStrain;
uniform float u_time;

struct BlackHole { vec3 pos; float mass; float spin; float rs; };
uniform BlackHole u_bhs[4];

in vec2 v_uv;
out vec4 fragColor;

vec3 screenRay(vec2 uv) {
  float aspect = u_resolution.x / u_resolution.y;
  float halfH = 0.5;
  float halfW = halfH * aspect;
  vec3 dir = normalize(vec3(
    (uv.x * 2.0 - 1.0) * halfW,
    (uv.y * 2.0 - 1.0) * halfH,
    1.0
  ));
  vec3 right = normalize(cross(u_camDir, vec3(0.0, 1.0, 0.0)));
  vec3 up = cross(right, u_camDir);
  return normalize(dir.x * right + dir.y * up + dir.z * u_camDir);
}

vec3 gwRippleDeflection(vec3 pos, float t) {
  if (u_gwStrain <= 0.0001) return vec3(0.0);
  vec3 toSource = pos - u_gwSourcePosition;
  float dist = length(toSource);
  if (dist < 0.001) return vec3(0.0);
  float amplitude = u_gwStrain * 0.02 / max(dist, 1.0);
  float phase = dist * u_gwFrequency * 0.01 - u_time * u_gwFrequency;
  float ripple = sin(phase) * amplitude;
  vec3 dir = normalize(toSource);
  vec3 perp1 = normalize(cross(dir, vec3(0.0, 1.0, 0.0)));
  vec3 perp2 = normalize(cross(dir, perp1));
  return (perp1 * ripple + perp2 * ripple * 0.7);
}

void main() {
  vec3 rayOri = u_camPos;
  vec3 rayDir = screenRay(v_uv);
  float t = 0.0;
  float dt = 50.0;
  float farPlane = 1e6;

  float photonBrightness = 0.0;

  for (int i = 0; i < u_stepCount; i++) {
    vec3 pos = rayOri + rayDir * t;
    vec3 gwDefl = gwRippleDeflection(pos, u_time);
    rayDir = normalize(rayDir + gwDefl * dt * 0.0005);
    bool absorbed = false;

    for (int bh = 0; bh < u_bhCount; bh++) {
      vec3 d = pos - u_bhs[bh].pos;
      float dist = length(d);
      float rs = u_bhs[bh].rs;

      if (dist < rs * 0.5) { absorbed = true; break; }

      if (dist < rs * 1.6 && dist > rs * 1.4) {
        float ringFactor = 1.0 - abs(dist - rs * 1.5) / (rs * 0.1);
        photonBrightness = max(photonBrightness, ringFactor);
      }

      if (dist < rs * 50.0) {
        float deflAngle = rs / dist;
        vec3 toBH = normalize(d);
        rayDir = normalize(rayDir + toBH * deflAngle * dt * 0.001);

        if (u_bhs[bh].spin > 0.0) {
          vec3 tangential = cross(vec3(0.0, 1.0, 0.0), d);
          rayDir = normalize(rayDir + normalize(tangential) * u_bhs[bh].spin * rs / (dist * dist) * dt * 0.0001);
        }
      }
    }

    if (absorbed) { fragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }

    t += dt;
    if (t > farPlane) break;
  }

  vec4 bgColor = texture(u_sceneTex, v_uv);
  if (photonBrightness > 0.0) {
    vec3 ringColor = vec3(1.0, 0.95, 0.8) * photonBrightness * 2.5;
    bgColor = vec4(bgColor.rgb + ringColor, 1.0);
  }
  fragColor = bgColor;
}
