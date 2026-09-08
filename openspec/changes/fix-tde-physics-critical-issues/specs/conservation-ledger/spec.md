# Spec: Conservation Ledger

## Requirement

Conservation diagnostics must include momentum and angular momentum. Escape accounting must be invoked when particles leave the system.

## Acceptance Criteria

- `getDiagnostics()` returns `momentum.linear` and `momentum.angular`
- `recordEscape(mass)` called when particles are marked escaped
- Mass accounting `accounted ≈ initial` when no accretion occurs
