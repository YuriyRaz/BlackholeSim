# sph-gradient

## Purpose

Correct SPH pressure gradient direction so that compressed particles repel each other.

## Requirements

### Requirement: SPH gradient direction is repulsive
SPH pressure forces SHALL repel particles when compressed, not attract them. `gradWCubicSpline` SHALL receive `dir = (pi - pj)`, the `(i-j)` direction.

#### Scenario: Gradient direction correct
- **WHEN** `gradWCubicSpline` is called for particle i relative to particle j
- **THEN** the `dir` parameter SHALL be `(pi - pj)`

#### Scenario: High pressure causes repulsion
- **WHEN** particles are under high pressure
- **THEN** they SHALL accelerate away from each other, not toward each other

### Requirement: Existing SPH tests pass
Existing SPH density and force unit tests SHALL continue to pass after gradient direction correction.

#### Scenario: SPH tests pass
- **WHEN** the gradient direction is corrected
- **THEN** all existing SPH density and force unit tests SHALL pass
