import { Constants } from '../core/Constants.js';

export function BinaryBHPreset() {
  const m1 = 36;
  const m2 = 29;
  const M = m1 + m2;
  const Rs = Constants.schwarzschildRadiusKm(M);
  const sep = 20 * Rs;
  const r1 = sep * m2 / M;
  const r2 = sep * m1 / M;
  const vOrb = Math.sqrt(Constants.G * M * Constants.M_sun / (sep * 1000)) * 1e-3;
  const v1 = vOrb * m2 / M;
  const v2 = vOrb * m1 / M;

  return {
    bodies: [
      { type: 'blackhole', mass: m1, position: [-r1, 0, 0], velocity: [0, 0, -v1], spin: 0, fixed: true, name: 'BH1_36Msun' },
      { type: 'blackhole', mass: m2, position: [r2, 0, 0], velocity: [0, 0, v2], spin: 0, fixed: true, name: 'BH2_29Msun' }
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
  const a = dR * 1.5;
  const e = 0.9;
  const periapsis = a * (1 - e);
  const vPeriapsis = Math.sqrt(Constants.G * M_bh * Constants.M_sun * (2 / periapsis - 1 / a)) * 1e-3;
  const vApoapsis = Math.sqrt(Constants.G * M_bh * Constants.M_sun * (2 / (a * (1 + e)) - 1 / a)) * 1e-3;

  return {
    bodies: [
      { type: 'blackhole', mass: M_bh, position: [0, 0, 0], velocity: [0, 0, 0], spin: 0, fixed: true, name: 'SMBH_1Msun' },
      { type: 'star', mass: m_star, radius: R_star, temperature: 5778, position: [-a, 0, 0], velocity: [0, 0, -vApoapsis], name: 'Star_1Msun' }
    ],
    gas: [],
    camera: { theta: 0, phi: Math.PI / 6, distance: a * 3, focus: [0, 0, 0] }
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
    const vOrb = Math.sqrt(Constants.G * M * Constants.M_sun / (r * 1000)) * 1e-3;
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
