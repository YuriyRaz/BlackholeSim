---
name: job-orchestrator
description: Operate a durable, persistent-session queue of explicit subagent jobs.
---

# Job Orchestrator

The root session is the human interface. It MUST NOT perform domain work itself:
route investigation, implementation, verification, decisions, and synthesis to
explicit jobs. Receipt and artifact contracts enforce this boundary.

## Standalone Orchestrator Script

The orchestrator can run as a standalone Python script using the `opencode-ai` SDK.
This separates deterministic routing from LLM sessions and enables parallel job execution.

### Starting the Orchestrator

```bash
python scripts/orchestrator.py --run <run-root> --opencode-server <url> --opencode-session-id <session-id>
```

### Session Discovery Flow

Before starting the orchestrator, the agent must discover the user's session ID:

1. **Ask the user for their opencode server URL** (e.g., `http://localhost:4096`)
2. **List active sessions via SDK**:
   ```python
   client = AsyncOpencode(base_url=server_url)
   sessions = await client.session.list()
   ```
3. **Filter out orchestrator-created sessions**: Sessions with titles starting with `[RUN-` are orchestrator-created
4. **Select the most recent user session**: Choose the session without the `[RUN-` prefix
5. **Pass the session ID as `--opencode-session-id`**

If SDK listing fails, the user can specify the session ID manually.

## Root Allowlist

The root MAY only initialize runs, register jobs, call `next`, prepare
dispatches, launch or resume workers through the configured transport adapter,
record exact verified transport facts, answer user questions, run `audit`,
`recover`, or `repair`, and relay final run status. Repository investigation,
editing, domain testing, verification, report authorship, checkpoint authorship,
outcome synthesis, and domain acceptance MUST be delegated.

The root MUST record the exact native session reference returned by the
transport. Invented labels, aliases, reconstructed IDs, and descriptive
references are forbidden. The root MUST send the generated prompt verbatim and
MUST NOT prepend, append, summarize, correct, or replace it.

## Root Boundary

The root orchestrator only orchestrates. It MAY:
- Initialize runs with `init`
- Register jobs with `register`
- Call `next` to inspect the next operation
- Prepare dispatches with `prepare-dispatch`
- Launch or resume workers via transport adapter receipts
- Record transport facts with `launch-receipt` and `response-receipt`
- Ask user questions with `ask`
- Record answers with `answer`
- List pending questions with `pending`
- Commit expansions with `commit-expansion`
- Run `audit`, `recover`, or `repair`
- Relay final run status
- Cancel runs with `cancel`
- Advance campaign cycles with `advance-cycle`
- Create finalization workers with `create-finalization-worker`

The root MUST NOT:
- Perform domain work (investigation, implementation, verification)
- Edit source code or repository files directly
- Author reports, checkpoints, or outcome synthesis
- Make acceptance decisions
- Load or promote runs from older protocol versions

## Legacy Root-Session Approach

The root-session control-loop approach (running the control loop inline in the agent session) is deprecated. The standalone orchestrator script is the only supported default approach.

If you need to use the legacy root-session approach, see [legacy-root-session-orchestration.md](references/legacy-root-session-orchestration.md).

## Default Strategy Routing

The default adaptive strategy routes campaigns through ordered phases:

1. **Proposal Explore** — read-only workspace exploration
2. **Proposal Architect** — read-only architecture design
3. **Proposal Finalize** — read-only proposal validation
4. **Implementation Planning** — read-only work plan generation
5. **Implementation** — write-capable implementation work
6. **Deterministic Checks** — read-only automated validation
7. **Verification** — read-only independent verification (non-overridable)
8. **Review** — read-only architect review (non-overridable)
9. **Finalization** — write-capable OpenSpec finalization
10. **Goal Judge** — read-only goal assessment (non-overridable)

Compilation modes: `full_campaign`, `proposal_only`,
`implementation_from_proposal`, `architect_review_only`, `resume`, `custom`.

## Typed Terminal Outcomes

Terminal outcomes are typed sealed records:

- `GOAL_ACHIEVED` — goal satisfied by accepted evidence
- `CONTINUE` — more work required; expansion plan attached
- `BLOCKED` — goal cannot be achieved
- `INFEASIBLE` — goal is technically impossible
- `BLOCKED_NO_PROGRESS` — no progress possible
- `BUDGET_EXHAUSTED` — resource limits reached

Only `GOAL_ACHIEVED` with `run_status: completed` and `successful: true` means
the goal succeeded. Terminal decisions are sealed with graph digest binding.

## Boundaries

- State lives at `cwd()/.job-orchestrator/runs/` unless `--state-root` is set.
- Never manually read, edit, parse, or reconstruct authoritative run-state JSON
  (`run.json`, `jobs/*/job.json`, or `jobs/index.json`). Use `jobctl audit`,
  `recover`, and `repair`; if they cannot safely handle the condition, report
  that control-plane limitation.
- Files supplied to a command, including job definitions and recovery evidence,
  remain editable until successful ingestion. Correct a rejected input using
  its validation error; do not patch persisted state.
- A canceled, lost, unavailable, empty-with-uncertain-liveness, or contradictory
  transport result exits the normal loop. Run `audit`, gather direct evidence,
  and invoke `recover` before any retry or replacement.

## V6 Incompatibility Boundary

This runtime supports **only protocol version 6**. The following are prohibited:

- Loading runs with `schema_version` < 6
- Promoting or migrating old runs to the current tooling
- Using v5 commands (`init --mode v5`, `workerctl`, etc.)
- Loading state from `schemas/v5/` or earlier
- Interpreting v5 transport receipts as v6 evidence

For v5 runs, use an older compatible checkout. The `reject_v5_or_earlier()`
function in `orchestrator_core` enforces this boundary.

## Start And Register

```text
python scripts/jobctl.py init --request-file <path> --goal "<goal>"
python scripts/jobctl.py register --run <run-root> --definition <jobs.json>
```

Initialization creates a trusted run and fails before creating state unless the
configured Task adapter proves launch and response receipts, native Task
correlation, prompt hashing, status evidence, and proof revalidation.

```text
python scripts/jobctl.py launch-receipt --run <run-root> --receipt <receipt.json>
python scripts/jobctl.py response-receipt --run <run-root> --receipt <receipt.json>
```

## Load A Reference Only When Needed

| Situation | Reference |
| --- | --- |
| Protocol semantics, outcomes, completion, or scheduling | [protocol.md](references/protocol.md) |
| Interruption, contradictory evidence, uncertain external effect, audit, or repair | [recovery.md](references/recovery.md) |
| Creating or replacing a worker prompt | [job-protocol.md](references/job-protocol.md) |
| Selecting or implementing a transport adapter | [transport-capabilities.md](references/transport-capabilities.md) |
| Maintaining the skill or composing workflows | [maintainer-guidance.md](references/maintainer-guidance.md) |
| Canonical strategy reference | [strategy.md](references/strategy.md) |
| Dynamic graph reference | [dynamic-graph.md](references/dynamic-graph.md) |
| Architect role reference | [architect-roles.md](references/architect-roles.md) |
| Campaign reference | [campaign.md](references/campaign.md) |
| Schema registry and state structures | [state-schema.md](references/state-schema.md) |
| Field-level validity | `schemas/v6/*.schema.json` |
| Legacy root-session orchestration (deprecated) | [legacy-root-session-orchestration.md](references/legacy-root-session-orchestration.md) |
