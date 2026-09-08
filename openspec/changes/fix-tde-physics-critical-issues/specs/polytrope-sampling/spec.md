# Spec: Polytrope Sampling

## Requirement

Particle positions must follow the Lane-Emden density profile, not uniform volume sampling.

## Acceptance Criteria

- Cumulative mass profile precomputed from Lane-Emden solution
- Particles sampled via inverse CDF matching `M(ξ)/M_total`
- Central density higher than surface density (density gradient preserved)
