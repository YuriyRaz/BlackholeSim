# Orchestration Protocol

> [!CAUTION]
> **INFORMATIONAL ONLY.**
> The protocol described here is mechanically enforced by the `scripts/jobctl.py` control plane script.
> The LLM agent acts as the operator invoking the script, not the manual parser of the state files.
> Do NOT manually parse, edit, or interact with the JSON state files directly.

## Core Model

A run consists of:

```text
goal + setup + queue + jobs + messages + reports + event journal
```

A job is a durable unit of responsibility assigned to a role. A job may own an
ordered workflow and a persistent subagent conversation. A workflow node
either dispatches one command to that job session or requests a tracked child
job. A step is one command sent to a job conversation. A dispatch is one
attempt to execute a step.

All work has the same abstraction. Research, implementation, verification,
architecture review, remediation, and final synthesis are jobs with different
profiles, workflows, priorities, and inputs.

## Invariants

1. The orchestrator performs coordination only.
2. Only the orchestrator mutates the queue.
3. Only one dispatch is active in sequential mode.
4. Every job has a stable directory and report path.
5. Every lifecycle transition is appended through `jobctl` before snapshots.
6. A dispatch is persisted before it is sent.
7. A response and its artifacts are persisted before dependent work starts.
8. Jobs communicate through persisted messages and artifact references.
9. Role and job-type registries remain extensible by the initial request.
10. Advisory and final synthesis work never occurs implicitly.
11. Parent and child jobs share one global queue and one queue owner.
12. A waiting parent never occupies the active dispatch slot.
13. Every job session acknowledges a frozen worker protocol and job contract
    before receiving domain work.
14. Every job reports improvement observations; only an explicitly authorized
    skill-maintenance job may modify the canonical skill.
15. The root orchestrator session never performs job execution. Domain
    investigation, code edits, verification, technical answers, architecture
    decisions, and final synthesis are executed only inside tracked job
    sessions or child jobs.

## Root Session Boundary

`jobctl next` returns control-plane actions, not permission for the root
session to do job work. When the action type is `spawn_and_bootstrap` or
`send_dispatch`, the action prompt is a payload for the worker subagent. The
root session must create or resume the job's subagent session, send that prompt
there verbatim, wait for the worker response, and record that response with
`jobctl record`.

If the root session notices itself starting to inspect domain code, apply a
change, run job acceptance checks, invoke a job-specific skill, answer an
architecture or implementation question, synthesize job output, or continue
after a user points out this violation, it must stop immediately. The only
valid recovery is to persist or report the protocol deviation as required and
route the remaining work through the active job session or a new explicit job.

## Initial Prompt Normalization

Extract:

- the run goal and completion conditions
- verbatim requirements and constraints
- role profiles
- role workflows
- workflow-node execution targets and child-job boundaries
- default and custom job types
- priority guidance
- automation, escalation, retry, and user-contact policies
- requested advisory, verification, delivery, and synthesis jobs

A role definition may be informal:

```text
Proposal:
1. use OpenSpec explore
2. use OpenSpec proposal
```

Normalize it without making it stricter:

```json
{
  "name": "Proposal",
  "purpose": "Investigate and prepare a proposal",
  "workflow": [
    {"id": "investigate", "command": "use OpenSpec explore"},
    {"id": "create-proposal", "command": "use OpenSpec proposal"}
  ]
}
```

## Scheduling

A job is ready when it is queued, its dependencies are complete, it is not
waiting on a message or job, and its next step is eligible. Select the highest
numeric priority, then the smallest queue sequence.

Pause the origin job while a resolution job runs. The resolution job is
sequential queue work, not nested hidden execution.

Keep the queue globally flat. `parent_job_id` and workflow-node links describe
ownership but do not create a second scheduler. When a parent requests a child,
persist the request, validate it, enqueue the child, mark the parent waiting,
and release the active slot. Resume the parent only after the required child
reports have been persisted and routed to it.

Reject dependency edges from an ancestor to a descendant that indirectly wait
on that same ancestor.

## Composite Workflows

A composite job mixes commands in its own persistent session with child jobs.
It is not a special rank or closed job type. Use the same queue, priority,
status, artifact, and messaging contracts.

Compile nested-looking prompt syntax into explicit workflow nodes before
execution. See [composite-workflows.md](composite-workflows.md) for the model
and a complete example.

## Dispatch Contract

Do not send the full orchestrator protocol to workers. At run creation,
snapshot [job-protocol.md](job-protocol.md) into
`<run-root>/protocol/job-protocol.md`, calculate its SHA-256 hash, and record
the version and hash in `protocol/manifest.json`.

Create a job-specific `contract.json` that references this snapshot. It
contains identity, role, goal, capabilities, restrictions, output paths,
related reports, and the expected result shape. Child jobs receive their own
contracts derived from accepted child requests; they do not inherit the
parent's whole prompt.

Before the first domain dispatch in a new or replacement session, send only a
bootstrap request. Require:

```json
{
  "protocol_ack": {
    "schema_version": 3,
    "protocol_version": 3,
    "protocol_sha256": "...",
    "job_id": "J001",
    "contract_revision": 1,
    "current_workflow_node_id": "verify"
  }
}
```

Reject a mismatched acknowledgement. Persist a valid acknowledgement in the
job record before dispatching work. Re-bootstrap when the session changes or
the contract revision changes.

Send the subagent:

- the frozen protocol path and hash
- the job contract path and revision
- run ID, job ID, and current workflow node
- exactly one current step command
- requirements and acceptance criteria relevant to that step
- absolute paths for its job directory and report
- explicit paths to related reports
- the expected result envelope

Require this result:

```json
{
  "status": "completed | partial | blocked | failed",
  "summary": "brief outcome",
  "artifacts": [{"path": "...", "purpose": "..."}],
  "concerns": [{"id": "...", "summary": "...", "impact": "..."}],
  "questions": [{"id": "...", "question": "...", "blocking": true}],
  "proposed_jobs": [{
    "request_id": "CR001",
    "for_workflow_node": "apply",
    "title": "Apply OpenSpec change",
    "role": "Implementation",
    "command": "/openspec-apply-change",
    "priority": 50
  }],
  "improvement_observations": [],
  "completed_work_units": [],
  "acceptance_evidence": [],
  "checkpoint_sha256": "..."
}
```

Readiness is derived by the control plane and never asserted by a worker.
`partial` retains the current node and schedules only remaining work units.
Reject ambiguous completion. A subagent that performed later workflow steps
has violated the dispatch boundary; record the deviation and reconcile actual
side effects before continuing.

Validate every proposed job against the run goal, current workflow node,
nesting limits, duplication, dependencies, and side-effect policy. Assign the
actual job ID only after acceptance.

Protocol awareness does not replace enforcement. Validate result envelopes,
verify required files, reject future-step execution, and treat queue mutations
or unapproved nested agents as protocol violations.

## Continuous Improvement

Append every job's `improvement_observations` to `improvements.jsonl`. Use a
stable signature based on category, affected instruction or component, failure
pattern, and proposed outcome. Preserve duplicates as events but link them to
the same candidate.

Classify observations:

- `transient`: environmental or one-time failure with no reusable correction
- `project_specific`: useful locally but inappropriate for the shared skill
- `generalizable`: a reusable prevention, correction, safety rule, or
  optimization

For a supported generalizable observation, create a normal queue job whose
contract alone grants `may_update_skill: true`. Pass the canonical skill source
path, observation IDs, evidence paths, current files, and required validation.
The root orchestrator does not design or apply the update itself.

See [continuous-improvement.md](continuous-improvement.md) for acceptance,
priority, validation, migration, and loop-control rules.

## Artifact References

Every job report lives at:

```text
<run-root>/jobs/<job-id>/report.md
```

Pass related artifacts explicitly:

```json
{
  "run_id": "20260708-120000-example",
  "job_id": "J002",
  "path": "C:\\...\\jobs\\J002\\report.md",
  "purpose": "Architecture answer for concern C1",
  "revision": 4,
  "sha256": "optional-content-hash"
}
```

Paths are authoritative for access. Job IDs provide discovery and correlation.
Include a revision or hash when a consumer must read a stable version.

## Concern Resolution

Use explicit actions rather than a vague combined mode:

```json
{
  "reply_to_origin": {
    "job_id": "J002",
    "message": "..."
  },
  "create_followup_jobs": [],
  "ask_user": null
}
```

More than one action may be present. Persist each action independently.

## Loop Detection

Build a failure signature from the job goal, step, concern category, observed
error, and approach ID. Treat repeated signatures or repeated approaches with
no changed evidence as a loop. Before user escalation, create an alternate
approach job that receives prior reports but is explicitly asked not to repeat
their approaches.

## Completion

A job report is the durable product of a job. Queue status alone is not proof
of completion. Verify that required reports and artifacts exist before marking
a job complete.

When final synthesis is needed, create a synthesis job and provide selected
report paths. Keep raw reports available so the synthesis can be audited.

Before completing the run, resolve every improvement candidate by recording a
completed maintenance job, rejection, or explicit deferral reason.
