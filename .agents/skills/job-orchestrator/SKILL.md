---
name: job-orchestrator
description: Orchestrate complex requests through a durable, resumable queue of sequential subagent jobs while keeping the root session limited to coordination and continuously improving the skill from execution evidence. Use when a request should be decomposed into role-driven jobs, executed one workflow step at a time, persisted as reports and state files, resumed after interruption, escalated through advisory jobs, expressed as a composite workflow, or used to identify and apply reusable protocol improvements.
---

# Job Orchestrator

Operate the main session as a control plane. Delegate all domain work, including
investigation, implementation, verification, architecture decisions, and final
synthesis, to explicit jobs.

Read [protocol.md](references/protocol.md) before starting a run. Read
[state-schema.md](references/state-schema.md) when creating or modifying run
state. Read [recovery.md](references/recovery.md) whenever resuming an existing
run or reconciling an interrupted step. Read
[composite-workflows.md](references/composite-workflows.md) when a role flow
mixes parent-session commands, child jobs, nested delegation, or verification
and repair loops. Use [job-protocol.md](references/job-protocol.md) only as the
worker-facing protocol snapshot; do not replace it with the full orchestrator
instructions. Read
[continuous-improvement.md](references/continuous-improvement.md) before
processing improvement observations or creating a skill-maintenance job.

## Establish The Run

1. Preserve the user's initial request verbatim in `request.md`.
2. Normalize its goal, requirements, acceptance criteria, roles, job types,
   role workflows, and policy overrides into `setup.json`.
3. Treat roles and job types as open string registries. The initial request may
   define, replace, or extend them.
4. Treat role definitions as collaborator profiles and suggested workflows,
   not rigid permission classes.
5. Initialize durable state with:

   ```text
   python scripts/init_run.py --request-file <path> --goal "<goal>"
   ```

   The default state root is this skill's `runs/` directory. Pass
   `--state-root` when the request or environment requires another location.
   Initialization snapshots and hashes the worker protocol into the run.
   It also records the canonical skill source and initializes the improvement
   ledger.
6. Decompose the goal into jobs and persist them before dispatching any work.
   Compile each selected role flow into workflow nodes and snapshot it into the
   job so later setup changes do not silently alter active work.
7. Mark each node with an execution target:
   - `job_session`: send one command to this job's persistent session
   - `child_job`: create a tracked child through the root orchestrator
8. Create `contract.json` for each job. Point it to the run's frozen protocol,
   include the protocol version and hash, and describe that job's identity,
   paths, capabilities, restrictions, and related reports.

## Maintain Control-Plane Boundaries

Perform only these actions in the root orchestrator session:

- create, prioritize, pause, resume, cancel, and close jobs
- validate child-job requests and attach children to parent workflow nodes
- dispatch one workflow step to one subagent
- evaluate structured job responses
- route messages and artifact paths between jobs
- collect, deduplicate, and classify improvement observations
- persist state transitions and recovery checkpoints
- detect blocked work, loops, and exhausted approaches
- decide whether additional advisory, remediation, verification, or synthesis
  jobs are needed

Do not perform the domain task, answer a job's technical question, make an
architecture decision, verify work, or synthesize the final result in the main
session. Create a job for that work.

## Run Composite Jobs

Treat `composite` as a workflow shape, not a privileged job type. A composite
job has the same priority, status, report contract, and queue representation as
any other job. It may keep a persistent session, execute commands there, and
request child jobs.

Keep one queue owner:

- a job may return `proposed_jobs`
- only the root orchestrator validates and creates those jobs
- all children enter the same global queue
- the parent becomes `waiting` and releases the active execution slot
- completed child report paths are routed back to the parent session
- the next parent-session command is sent only after acknowledgement

Do not allow a composite job or a skill invoked inside it to spawn untracked
subagents when durable orchestration is required. Instruct it to request
tracked child jobs instead. If direct nested agents cannot be prevented, treat
that execution as opaque and record the reduced recovery guarantees.

## Execute Sequentially

1. Select the highest-priority ready job. Break equal priorities by queue
   order. Keep only one global dispatch active in sequential mode.
2. Start or resume the job's persistent subagent session.
3. Bootstrap every new or replacement session before domain work:

   ```text
   Read <protocol-path> and <contract-path>. Do not perform domain work.
   Return protocol_ack with the protocol version, hash, job ID, and current
   workflow node.
   ```

4. Validate and persist the acknowledgement. Bootstrap again only when the
   session is replaced or the contract revision changes.
5. Persist a dispatch envelope and send exactly one workflow command.
   Explicitly forbid later steps:

   ```text
   Execute only the workflow step below. Do not begin later steps.
   Persist your report at <report-path>.
   Return the required result envelope when this step is complete.
   ```

6. Record the dispatch before sending it. Record the response before changing
   job or queue state.
7. Require the subagent to update its stable `report.md` after every step and
   write detailed outputs under its job directory.
8. Evaluate the response, then either advance one node, create requested child
   jobs, wait, retry with a changed approach, or complete the job.

Never send a complete multi-step role workflow in one prompt. Deliver a
resolution message and the next workflow command as separate prompts.

Do not rely on a subagent discovering the installed skill. The frozen protocol
path, job contract path, and current dispatch are required inputs. Enforce the
contract by validating acknowledgements, result envelopes, report existence,
child requests, and workflow boundaries.

## Improve Continuously

Require every job result to include `improvement_observations`, even when it is
an empty list. Capture errors, recurring friction, missing safeguards,
ambiguous instructions, concept weaknesses, and credible optimizations.
Persist every observation in `improvements.jsonl` before acting on it.

Do not let ordinary jobs edit the canonical skill. The root orchestrator:

1. Deduplicates observations by evidence and failure signature.
2. Classifies each as transient, project-specific, or generalizable.
3. Creates an explicit skill-maintenance job for a generalizable defect or
   optimization with sufficient evidence.
4. Gives only that job `may_update_skill: true`, the canonical skill path,
   evidence report paths, and a narrowly scoped objective.
5. Requires the maintenance job to make the smallest reusable change, test
   affected scripts or templates, run the skill validator, and report changed
   files and validation evidence.
6. Records a deferral reason when an observation is unsafe, speculative,
   duplicate, project-specific, or outside current authority.

Prioritize a maintenance job immediately when the current protocol could cause
data loss, unsafe actions, repeated failure, or invalid recovery. Schedule
lower-risk optimizations without displacing critical task work, but process
every unresolved observation before completing the run.

Skill changes affect future runs by default. Never mutate the frozen protocol
snapshot of an active run. If a current run requires new semantics, create a
separate migration job, persist the decision, update contracts, and
re-bootstrap affected sessions.

Bound continuous improvement with configured limits. Deduplicate repeated
lessons, prohibit an improvement job from recursively editing the skill without
a new accepted observation, and never weaken safety or validation merely to
make a failing run pass.

## Route Concerns

All job communication passes through the orchestrator as persisted messages.
Jobs may propose child jobs but may not mutate the queue themselves.

When an unfinished job can continue after receiving an answer:

1. Mark it `waiting`.
2. Create a higher-priority resolution job.
3. Pass the origin report path and precise question to that job.
4. Persist the resolution result.
5. Send only the answer to the original job and wait for acknowledgement.
6. Send the next workflow command separately.

When the origin job is complete, blocked, or no longer useful to resume, let
the resolution job propose follow-up jobs. Validate and enqueue those jobs
instead of reviving the origin job.

Architecture review is not privileged behavior. It is an ordinary job,
usually with higher priority and a role suited to strategic uncertainty.
When a persistent verification or implementation job raises a major concern,
pause it, run the architecture job separately, route the architecture report
back, and resume the original session. This preserves worker context without
hiding the architecture decision inside that worker job.

## Handle Loops And User Escalation

Track attempts, approach identifiers, repeated concerns, and unchanged failure
signatures. When work repeats without material progress, create a job to
investigate substantially different approaches. Do not merely retry the same
prompt.

Apply loop limits independently to parent nodes, child requests, and
verification-repair cycles. Reject child requests that create an ancestor
dependency cycle or exceed configured nesting and child-count limits.

Ask the user only when a material scope or risk decision requires their
authority, required information is unavailable, or multiple investigated
approaches remain blocked. Persist the question and the answer.

## Finish The Run

Final synthesis is always an explicit job when requested by the initial prompt
or added by the orchestrator. Pass it the relevant report paths. The
orchestrator may relay that job's result but must not silently synthesize it.

Complete a run only when no required job remains queued, running, waiting, or
blocked; acceptance criteria have been addressed; and any required synthesis
job has completed. Persist the terminal state before reporting completion.
