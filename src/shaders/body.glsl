#version 300 es
precision highp float;

in vec3 v_normal;
in vec3 v_worldPos;

uniform mat4 u_viewProj;
uniform vec3 u_bodyPos;
uniform vec3 u_bodyColor;
uniform float u_bodyRadius;
uniform uint u_bodyType;
uniform float u_time;
uniform vec3 u_camPos;

out vec4 fragColor;

void main() {
  vec3 n = normalize(v_normal);
  vec3 light = normalize(vec3(1.0));
  float diff = max(dot(n, light), 0.1);
  vec3 col = u_bodyColor * diff;

  if (u_bodyType == 0u) {
    fragColor = vec4(0.0, 0.0, 0.0, 1.0);
  } else if (u_bodyType == 1u) {
    vec3 viewDir = normalize(u_camPos - v_worldPos);
    float rim = 1.0 - max(dot(viewDir, n), 0.0);
    float corona = pow(rim, 3.0) * 0.5;
    fragColor = vec4(col + vec3(corona * 0.5, corona * 0.3, corona), 1.0);
  } else if (u_bodyType == 2u) {
    float beam = pow(max(dot(n, vec3(0.0, 1.0, 0.0)), 0.0), 8.0);
    float pulse = 0.5 + 0.5 * sin(u_time * 10.0);
    fragColor = vec4(col + vec3(beam * pulse), 1.0);
  } else {
    fragColor = vec4(col, 1.0);
  }
}
