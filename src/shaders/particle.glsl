#version 300 es
precision highp float;

struct Particle { vec3 pos; vec3 vel; vec3 color; float size; };
layout(std140, binding = 0) buffer ParticleBuffer { Particle particles[]; };

uniform mat4 u_viewProj;
uniform vec3 u_camPos;
uniform vec2 u_resolution;
uniform int u_maxCount;

in float v_alpha;
in vec3 v_color;
out vec4 fragColor;

void main() {
  vec2 center = gl_PointCoord - vec2(0.5);
  float d = length(center);
  if (d > 0.5) discard;
  float alpha = 1.0 - smoothstep(0.3, 0.5, d);
  fragColor = vec4(v_color * alpha, alpha);
}
