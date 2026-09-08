## Why

The job-orchestrator can preserve schema-valid state while recording fabricated sessions, altered prompts, root-authored worker artifacts, stale reports, and unsupported completion claims. The protocol must make genuine worker execution, artifact provenance, interruption handling, and required verification enforceable rather than relying on root-agent prose compliance.

## What Changes

- Define a closed root control-plane operation set and prohibit root investigation, editing, testing, verification, artifact authorship, outcome synthesis, and domain acceptance.
- Require exact generated-prompt delivery and transport-authenticated session receipts containing the native session reference, run/job correlation, and prompt hash.
- Replace a job's singular caller-supplied session reference with append-only, provenance-bearing session attempts that support recovery-authorized replacements.
- Separate raw worker responses from accepted normalized outcomes; malformed or empty responses must be repaired in the same live session or handled through audit and recovery.
- Establish exclusive worker ownership and cryptographic provenance for reports, checkpoints, and outcomes; reject root-authored, changed, stale, or cross-run artifacts.
- Give workers canonical run-scoped artifact references and absolute write paths, and automatically propagate completed dependency reports to dependent prompts.
- Introduce structured completion claims and stable completion-condition results, with required evidence and independent-verifier gates where configured.
- Distinguish successful completion from terminal failed or canceled runs in protocol state and `run_complete` output.
- Require explicit side-effect classification and route canceled, lost, unavailable, ambiguous, or contradictory transport results through audit and recovery before replacement or retry.
- Correct `SKILL.md`, protocol references, worker instructions, recovery guidance, maintainer guidance, CLI examples, and `AUTONOMOUS_COMPLETION_PROMPT.md` to match the implemented control loop.
- Add regression and conformance tests for transport provenance, exact prompt delivery, recovery attempts, artifact isolation and propagation, malformed responses, evidence gates, terminal run outcomes, and documented CLI commands.
- **BREAKING**: Version the persisted protocol and CLI ingestion contracts for authenticated session receipts, attempt history, raw responses, artifact provenance, and completion-condition results. Existing run handling must be explicit rather than silently accepting legacy records as trusted execution evidence.

## Capabilities

### New Capabilities

- `orchestrator-execution-boundary`: Closed root-agent permissions, exact prompt relay, worker-owned semantic artifacts, and rejection of root-synthesized execution results.
- `orchestrator-transport-provenance`: Adapter-authenticated session and response receipts, append-only attempts, side-effect classification, and recovery-first interruption handling.
- `orchestrator-artifact-context`: Run-scoped artifact identities and paths, report provenance and freshness, cross-run isolation, and automatic dependency-report propagation.
- `orchestrator-evidence-gates`: Structured completion claims, stable condition results, required evidence and independent verification, and truthful successful-versus-terminal run outcomes.

### Modified Capabilities

None. The repository has no existing OpenSpec capability for the job-orchestrator protocol.

## Impact

- Affects the job-orchestrator skill instructions and references, `jobctl` control-plane logic, persisted schemas, prompt generation, recovery transitions, report handling, and orchestration tests.
- Changes transport-adapter integration by requiring adapter-issued receipts and exact prompt/response correlation rather than caller-authored session strings.
- Changes worker-facing contracts by supplying authoritative run-scoped report locations and requiring worker-authored normalized responses and evidence.
- Changes completion semantics and may require a new persisted-state version plus an explicit policy for existing v4 runs.
- Updates the project-level autonomous completion prompt so its executable examples use the actual skill script path, available interpreter invocation, exact CLI options, outcome files, answer/resume behavior, advisory waits, and terminal-status interpretation.
