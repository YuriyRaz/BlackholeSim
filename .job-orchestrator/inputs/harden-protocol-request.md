# Protocol Hardening Implementation Request

## Goal

Implement the `harden-job-orchestrator-protocol` OpenSpec change: a versioned trusted protocol for the job-orchestrator skill that makes genuine worker execution, artifact provenance, interruption handling, and required verification enforceable.

## Scope

49 tasks across 7 groups in `openspec/changes/harden-job-orchestrator-protocol/tasks.md`:

1. **Versioned Protocol Foundation** (1.1-1.5): v5 schemas, version loading, persistence
2. **Transport Adapter And Dispatch Provenance** (2.1-2.7): adapter handshake, fake adapter, dispatch receipts
3. **Attempts, Responses, And Recovery** (3.1-3.8): append-only attempts, raw responses, side-effect classes
4. **Run-Scoped Artifact Integrity** (4.1-4.7): canonical references, provenance binding, dependency propagation
5. **Evidence-Gated Completion** (5.1-5.8): structured conditions, claims, verifier gates, terminal dispositions
6. **Root And Worker Instructions** (6.1-6.6): SKILL.md, protocol.md, job-protocol.md, transport-capabilities.md, recovery.md, maintainer-guidance.md
7. **Completion Prompt And Conformance** (7.1-7.8): AUTONOMOUS_COMPLETION_PROMPT.md, documentation tests, end-to-end tests

## Key Constraints

- The shared skill lives at `C:\Projects\ai-skills\skills\job-orchestrator\`
- Project-local copy at `.agents/skills/job-orchestrator/` must stay in sync
- Python at `C:\Projects\AkitoBlogBot\.venv\Scripts\python.exe`
- Existing v4 tests (220 total, 3 pre-existing failures) must remain green
- v4 runs must be explicitly `legacy_unattested`, never silently upgraded
- Transport adapters that cannot provide receipts must block trusted execution
