# Request: Finalize visual-effects-03 & Implement audio-polish-04

## Goal

Complete the remaining work on the BlackholeSim project: finalize visual-effects-03 (verify, fix, sync, archive, commit & push) and fully implement audio-polish-04 (apply all tasks, verify, fix, sync, archive, commit & push). Run architect reviews for both.

## Workspace

C:\Projects\BlackholeSim

## What Is Already Done

### ✅ core-renderer-01 — FULLY COMPLETE
- Archived at: openspec/changes/archive/2026-07-09-core-renderer-01

### ✅ physics-engine-02 — FULLY COMPLETE
- Archived at: openspec/changes/archive/2026-07-09-physics-engine-02

### ⚠️ visual-effects-03 — IMPLEMENTED BUT NOT FINALIZED
- Proposal: DONE
- Implementation: DONE — all tasks checked off, code committed (efdc047)
- Verification: NOT DONE
- Sync specs: NOT DONE
- Archive: NOT DONE
- Commit final: NOT DONE
- Active change dir: openspec/changes/visual-effects-03

### ❌ audio-polish-04 — PROPOSED ONLY
- Proposal: DONE
- Implementation: NOT STARTED — all tasks unchecked
- Active change dir: openspec/changes/audio-polish-04

## Constraints

- Do NOT re-propose or re-implement core-renderer-01 or physics-engine-02.
- Do NOT re-propose visual-effects-03 or audio-polish-04 (proposals exist).
- Do NOT re-implement visual-effects-03 (code is committed, all tasks checked).

## Roles

### Implementation
The flow:
1. For each task group use new job and run command /openspec-apply-change
2. In new job:
   2.1. Run command /openspec-verify-change
   2.2. Fix all findings even minor
   2.3. For major issue ask Architect
3. /openspec-sync-specs
4. /openspec-archive-change
5. Commit into main and push

### Architect
Use the OpenSpec explore command to investigate any issues / make architecture review / find the solutions for open questions. Always check the documentation. But documentation might be updated/corrected if needed.

## Jobs

### J001: visual-effects-03 Implementation (continue from verify step)
- Role: Implementation
- Change: openspec/changes/visual-effects-03
- Skip apply (already done). Start from verify.
- Workflow: verify → fix findings → sync → archive → commit & push

### J002: visual-effects-03 Architect Review
- Role: Architect
- Change: openspec/changes/visual-effects-03
- Review implemented code, check for correctness, suggest corrections via sub-jobs if needed.
- Depends on: J001

### J003: audio-polish-04 Implementation (full pipeline)
- Role: Implementation
- Change: openspec/changes/audio-polish-04
- Full pipeline: apply all task groups → verify → fix → sync → archive → commit & push
- Depends on: J002

### J004: audio-polish-04 Architect Review
- Role: Architect
- Change: openspec/changes/audio-polish-04
- Review implemented code, check for correctness, suggest corrections via sub-jobs if needed.
- Depends on: J003
