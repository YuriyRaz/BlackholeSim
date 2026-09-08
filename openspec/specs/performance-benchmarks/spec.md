# performance-benchmarks

## Purpose

Enforce minimum performance floors in benchmarks to ensure the simulation runs at acceptable rates.

## Requirements

### Requirement: Rendering performance floor
Rendering benchmarks SHALL assert a minimum of 30 FPS. Tests SHALL fail if rendering falls below this floor, rather than merely asserting > 0.

#### Scenario: Rendering meets FPS floor
- **WHEN** the rendering benchmark runs
- **THEN** the measured FPS SHALL be ≥ 30

### Requirement: Physics sub-step performance floor
Physics sub-step benchmarks SHALL assert realistic minimum throughput. Tests SHALL fail if throughput drops below acceptable thresholds, rather than merely asserting > 0.

#### Scenario: Physics throughput meets minimum
- **WHEN** the physics sub-step benchmark runs
- **THEN** the measured throughput SHALL meet the minimum threshold for the particle count
