# Protocol Semantics

This is the canonical protocol reference. The root procedure is in
[SKILL.md](../SKILL.md); field validity is in `schemas/v6/`.

## Scheduling And Dispatch

`next` is a pure query. It returns `prepare_dispatch` with a selected job and
state revision, or one of `start_job`, `resume_job`, `ask_user`, `wait`,
`commit_expansion`, `recover`, and `run_complete`. `prepare-dispatch` is the
locked mutation that creates an immutable dispatch containing the exact prompt
digest.

The transport adapter must return a verifiable launch receipt before a session
attempt exists. Attempts are append-only; only recovery may authorize a
replacement attempt. The adapter returns an immutable raw response receipt, and
the control plane stores the exact raw response before normalizing it.
Record those verified facts with `launch-receipt` and `response-receipt`.

## Outcomes And Completion

Workers return exactly one normalized outcome: `completed`, `needs_input`, or
`failed`. An empty response from a confirmed live session gets a same-session
response-retrieval continuation. Malformed output gets a same-session
format-repair continuation. Empty or malformed output with uncertain liveness
requires audit and recovery; workspace files never substitute for a worker
response.

Worker completion is a claim, not acceptance. Structured condition results use
`passed`, `failed`, `not_run`, `unavailable`, or `unknown`. Only `passed`
satisfies a required condition. Required independent conditions are satisfied
only by their designated verifier jobs.

When a dependency is accepted, its worker-attested report is propagated to each
dependent prompt automatically in deterministic order. `related_reports` is
advisory context, not a substitute for dependency propagation or provenance.

A terminal `run_complete` response includes `run_status` and `successful`.
Failed and canceled runs are terminal but unsuccessful. Terminal `run.json`
status is persisted with the mutation that makes the job set terminal.

## Dynamic Graph Operations

The v6 protocol supports dynamic graph expansion within a campaign:

- **Goal Judge CONTINUE** — produces expansion_plan with new jobs
- **CAS Commit** — compare-and-swap commits expansion to graph
- **Recovery** — handles crashes at expansion transaction boundaries
- **Seal** — terminal commit binds graph digest to run

## Typed Decisions

All decisions are typed and validated against contracts:
- Goal Judge decisions: GOAL_ACHIEVED, CONTINUE, BLOCKED, INFEASIBLE, BLOCKED_NO_PROGRESS, BUDGET_EXHAUSTED
- Hypothesis results: supported, refuted, inconclusive, blocked
- Synthesis conclusions: root_cause_identified, partial_understanding, no_actionable_cause, needs_further_investigation
- Work plan types: direct_repair, implementation_set, openspec_batch, no_safe_path

## Recovery And Transport

Recovery classification and mutations are defined by [recovery.md](recovery.md).
Transport-adapter requirements are defined by
[transport-capabilities.md](transport-capabilities.md). The worker contract is
defined by [job-protocol.md](job-protocol.md).

## Workflow Composition

The job prompt determines domain workflow and verification. Create another
explicit job when work needs independent scheduling, judgment, reporting,
recovery, or user authority. Maintainer guidance is indexed in
[maintainer-guidance.md](maintainer-guidance.md).
