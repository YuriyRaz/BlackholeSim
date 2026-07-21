import { Constants } from '../core/Constants.js';
import { SimUnits } from '../core/SimUnits.js';
import { MatterParticle } from '../objects/MatterParticle.js';
import { RNG } from '../core/RNG.js';

function integrateLaneEmden(n, steps = 10000) {
  const dz = 1 / steps;
  let xi = 0;
  let theta = 1;
  let dtheta = 0;
  const points = [{ xi: 0, theta: 1 }];

  for (let i = 1; i <= steps * 50; i++) {
    const h = dz * Math.min(1, xi + dz * 10);
    const xi_mid = xi + h / 2;
    const theta_mid = theta + h / 2 * dtheta;
    const dtheta_mid = dtheta + h / 2 * (-2 / (xi + 1e-15) * dtheta - Math.pow(Math.max(theta, 0), n));

    xi += h;
    theta += h * dtheta_mid;
    dtheta += h * (-2 / (xi + 1e-15) * dtheta_mid - Math.pow(Math.max(theta, 0), n));

    if (i % Math.max(1, Math.floor(steps / 200)) === 0) {
      points.push({ xi, theta: Math.max(theta, 0) });
    }

    if (theta <= 0 || !isFinite(theta)) {
      points.push({ xi, theta: 0 });
      return { xi1: xi, dtheta1: dtheta, points };
    }
  }

  return { xi1: xi, dtheta1: dtheta, points };
}

export function generatePolytrope(options = {}) {
  const mass = options.mass ?? 1;
  const radius = options.radius ?? 1;
  const gamma = options.gamma ?? 5 / 3;
  const n = 1 / (gamma - 1);
  const N = options.numParticles ?? clampParticleCount(mass);
  const seed = options.seed ?? 42;

  const rng = new RNG(seed);

  const le = integrateLaneEmden(n);
  const xi1 = le.xi1;
  const dtheta1 = le.dtheta1;

  const R_star_km = radius * Constants.R_sun_km;
  const alpha = R_star_km / xi1;

  const massFactor = -xi1 * xi1 * dtheta1;
  const rho_c = mass / (4 * Math.PI * alpha * alpha * alpha * massFactor);

  const particles = [];

  for (let i = 0; i < N; i++) {
    const r_fraction = Math.cbrt(rng.next());
    const xi_sample = r_fraction * xi1;
    const theta_sample = getThetaAt(le.points, xi_sample);
    const density = rho_c * Math.pow(Math.max(theta_sample, 0), n);

    const r_km = xi_sample * alpha;
    const cosTheta = 2 * rng.next() - 1;
    const sinTheta = Math.sqrt(Math.max(0, 1 - cosTheta * cosTheta));
    const phi = rng.nextFloat(0, 2 * Math.PI);

    const x = r_km * sinTheta * Math.cos(phi);
    const y = r_km * sinTheta * Math.sin(phi);
    const z = r_km * cosTheta;

    const specificInternalEnergy = (Constants.G_solar_km * mass) / (R_star_km * (gamma - 1) * 3);
    const temperature = specificInternalEnergy * 1e7;

    const p = new MatterParticle({
      position: [x, y, z],
      velocity: [0, 0, 0],
      mass: mass / N,
      density: density,
      internalEnergy: specificInternalEnergy,
      temperature: temperature,
      phase: 'stellar',
      lifecycle: 'alive',
      smoothingLength: R_star_km * (3 / (4 * Math.PI * N)) ** (1 / 3),
    });
    p.pressure = (gamma - 1) * p.density * p.internalEnergy;

    particles.push(p);
  }

  return { particles, centralDensity: rho_c, radiusKm: R_star_km, xi1, alpha, n, gamma };
}

function getThetaAt(points, xi) {
  for (let i = 1; i < points.length; i++) {
    if (points[i].xi >= xi) {
      const t = (xi - points[i - 1].xi) / (points[i].xi - points[i - 1].xi + 1e-15);
      return points[i - 1].theta + t * (points[i].theta - points[i - 1].theta);
    }
  }
  return points[points.length - 1].theta;
}

export function clampParticleCount(mass) {
  return Math.max(200, Math.min(2000, Math.round(mass * 1000)));
}
