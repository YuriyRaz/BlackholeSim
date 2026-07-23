import { Constants } from '../core/Constants.js';
import { generatePolytrope } from '../physics/Polytrope.js';

export function BinaryBHPreset() {
  const m1 = 36;
  const m2 = 29;
  const M = m1 + m2;
  const Rs = Constants.schwarzschildRadiusKm(M);
  const sep = 20 * Rs;
  const r1 = sep * m2 / M;
  const r2 = sep * m1 / M;
  const vOrb = Constants.orbitalVelocity(M, sep);
  const v1 = vOrb * m2 / M;
  const v2 = vOrb * m1 / M;

  return {
    bodies: [
      { type: 'blackhole', mass: m1, position: [-r1, 0, 0], velocity: [0, 0, -v1], spin: 0, fixed: false, name: 'BH1_36Msun' },
      { type: 'blackhole', mass: m2, position: [r2, 0, 0], velocity: [0, 0, v2], spin: 0, fixed: false, name: 'BH2_29Msun' }
    ],
    gas: [],
    camera: { theta: 0, phi: Math.PI / 4, distance: sep * 3, focus: [0, 0, 0] }
  };
}

export function TDEPreset() {
  const M_bh = 1e6;
  const m_star = 1;
  const R_star = 1;
  const dR = Constants.tidalDisruptionRadius(M_bh, R_star, m_star);
  const eccentricity = 0.95;
  const rApo = 3 * dR;
  const rPeri = rApo * (1 - eccentricity) / (1 + eccentricity);
  const semiMajor = (rApo + rPeri) / 2;
  const vApo = Math.sqrt(Constants.G_solar_km * M_bh * (2 / rApo - 1 / semiMajor));

  const polytrope = generatePolytrope({
    mass: m_star,
    radius: R_star,
    numParticles: Constants.defaultStarResolution,
    seed: 42,
    gamma: 5 / 3,
  });

  const matterParticles = polytrope.particles.map(p => ({
    position: [p.position[0] - rApo, p.position[1], p.position[2]],
    velocity: [p.velocity[0], vApo + p.velocity[1], p.velocity[2]],
    mass: p.mass,
    density: p.density,
    internalEnergy: p.internalEnergy,
    temperature: p.temperature,
    phase: 'stellar',
    lifecycle: 'alive',
    smoothingLength: p.smoothingLength,
  }));

  const bhVisualRadius = Math.max(Constants.schwarzschildRadiusKm(M_bh) * 0.5, dR * 0.04);

  return {
    bodies: [
      { type: 'blackhole', mass: M_bh, renderRadius: bhVisualRadius, position: [0, 0, 0], velocity: [0, 0, 0], spin: 0, fixed: true, name: 'SMBH_1e6Msun' },
      { type: 'star', mass: m_star, radius: R_star, renderRadius: dR * 0.04, temperature: 5778, position: [-rApo, 0, 0], velocity: [0, 0, vApo], name: 'Star_1Msun' }
    ],
    matterParticles,
    camera: { theta: 0, phi: Math.PI / 8, distance: rApo * 0.9, focus: [-rApo * 0.25, 0, 0] }
  };
}

export function KerrPreset() {
  const M = 10;
  const Rs = Constants.schwarzschildRadiusKm(M);
  const spin = 0.998;
  const isco = Constants.iscoRadius(spin) * Rs;
  const gas = [];
  const nGas = 100;

  for (let i = 0; i < nGas; i++) {
    const r = isco + (Constants.gasMaxRadius * Rs - isco) * Math.random();
    const angle = Math.random() * Constants.TWO_PI;
    const vOrb = Constants.orbitalVelocity(M, r);
    const thickness = Constants.gasDiskThickness * r;
    const z = (Math.random() - 0.5) * thickness;

    gas.push({
      position: [r * Math.cos(angle), z, r * Math.sin(angle)],
      velocity: [-vOrb * Math.sin(angle), 0, vOrb * Math.cos(angle)],
      mass: 1e-6,
      temperature: 1e6 / Math.sqrt(r / Rs)
    });
  }

  return {
    bodies: [
      { type: 'blackhole', mass: M, position: [0, 0, 0], velocity: [0, 0, 0], spin: spin, fixed: true, name: 'Kerr_BH_10Msun' }
    ],
    gas,
    camera: { theta: 0, phi: Math.PI / 3, distance: Rs * 60, focus: [0, 0, 0] }
  };
}

export function CustomPreset() {
  return {
    bodies: [
      { type: 'blackhole', mass: 10, position: [0, 0, 0], velocity: [0, 0, 0], spin: 0.5, fixed: true, name: 'BH_10Msun' }
    ],
    gas: [],
    camera: { theta: 0, phi: Math.PI / 4, distance: 100, focus: [0, 0, 0] }
  };
}

export const PRESETS = {
  binaryBH: { name: 'Binary BH', fn: BinaryBHPreset },
  tde: { name: 'TDE', fn: TDEPreset },
  kerr: { name: 'Kerr', fn: KerrPreset },
  custom: { name: 'Custom', fn: CustomPreset }
};
