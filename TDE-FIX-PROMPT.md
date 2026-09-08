# TDE Physics Fix — Agent Initial Prompt

Load the `job-orchestrator` skill and follow its control-plane protocol to fix all 7 critical issues from the `rebuild-tde-physics-core` verification. Use Playwright for browser-level physics verification. Use OpenSpec flow for all changes.

## The 7 Critical Issues

1. SPH gradient direction reversed in `src/physics/SPHSolver.js` — `gradWCubicSpline` uses j-i direction causing attraction instead of repulsion
2. Spurious self-gravity — particles accelerate toward themselves
3. Circularization and disk transition in `src/physics/PhysicsEngine.js` — phase transition reads shock state after reset; circularity uses only one angular momentum component
4. 30 FPS rendering requirement not enforced — `test/benchmarks.test.js` only requires throughput > 0
5. Matter trail gaps — `_updateParticleTrails` may not include matter particles consistently
6. Polytrope sampling in `src/physics/Polytrope.js` — `cbrt(random)` uniform volume sampling doesn't match Lane-Emden density profile
7. Conservation ledgers in `src/physics/ConservationLedger.js` — momentum/angular momentum omitted from diagnostics, escape accounting not invoked

## Iteration Protocol

Work in 4 iterations. Each iteration: **Proposal → Implementation → Architect review**.

### Iteration 1: SPH Gradient + Self-Gravity (issues 1-2)
### Iteration 2: Circularization + Disk (issue 3)
### Iteration 3: 30 FPS + Trails (issues 4-5)
### Iteration 4: Polytrope + Conservation (issues 6-7)

### For each iteration:

**Step 1 — Proposal job:**
- Run `openspec explore` to investigate the issue
- If unclear, ask Architect for guidance
- Run `openspec propose` with the fix plan
- Include Playwright test plan

**Step 2 — Implementation job (per task group):**
- Run `openspec-apply-change`
- Run `openspec-verify-change`
- Fix ALL findings (even minor)
- If major issue, ask Architect
- Run `openspec-sync-specs`
- Run `openspec-archive-change`
- Commit and push

**Step 3 — Architect review:**
- Run `openspec explore` to review what was implemented
- Verify physics correctness
- Check documentation accuracy
- If corrections needed, spawn sub-job
- Prepare next iteration plan

## Browser Testing (Playwright)

Install if needed:
```bash
npm init -y && npm install -D @playwright/test && npx playwright install chromium
```

Expose physics state in `src/main.js`:
```javascript
if (typeof window !== 'undefined') {
  window.__getParticleDistances = () => { /* nearest-neighbor distances */ };
  window.__getAverageFPS = () => { /* measured FPS */ };
  window.__getTotalEnergy = () => { /* kinetic + potential */ };
  window.__getTrailGapCount = () => { /* broken trail count */ };
  window.__getBoundParticleCount = () => { /* bound particles */ };
}
```

Write tests in `tests/browser/physics-verification.spec.ts`:
- SPH particles repel when compressed
- Renders at 30 FPS or higher
- Energy conservation within 5% over 10s
- Matter particles render without gaps
- Bound particles form accretion structure

Run: `npx playwright test tests/browser/ --reporter=list`

## Constraints

- Python: `C:\Projects\AkitoBlogBot\.venv\Scripts\python.exe`
- Unit tests: `& "C:\Projects\AkitoBlogBot\.venv\Scripts\python.exe" -m pytest test/ -v`
- Browser tests: `npx playwright test`
- All existing tests must remain green
- Never skip failing tests
- Update `openspec/specs/tidal-disruption/spec.md` if behavior changes
- Update README.md and docs/DESIGN.md as needed

## Completion

All done when:
- [ ] All 7 issues fixed
- [ ] All unit tests pass
- [ ] All Playwright browser tests pass
- [ ] Documentation accurate
- [ ] Changes committed and pushed
