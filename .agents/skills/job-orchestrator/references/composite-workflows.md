# Composite Workflows

## Purpose

Use a composite job when one role flow needs both:

- a persistent parent session for context-sensitive commands
- separately tracked child jobs for delegated or independently recoverable work

The parent may coordinate semantically, but the root orchestrator remains the
only scheduler and queue mutator.

## Execution Targets

Each workflow node declares one target:

```text
job_session | child_job
```

`job_session` sends exactly one command to the persistent session belonging to
the current job. `child_job` asks the root orchestrator to create a separate
job and suspends the parent until the required child result is available.

Do not use `main_session`; it is ambiguous. The root orchestrator session never
performs domain work. Use `job_session` for the composite parent's own context.

## Normalized Example

Normalize a Proposal flow like this:

```json
{
  "role": "Proposal",
  "session_policy": "persistent",
  "workflow": [
    {
      "id": "apply",
      "position": 1,
      "run_in": "child_job",
      "child_template": {
        "title": "Apply the OpenSpec change",
        "role": "Implementation",
        "command": "/openspec-apply-change",
        "delegation_policy": "request_tracked_child_jobs",
        "instruction": "Use a tracked child job for each implementation task"
      }
    },
    {
      "id": "verify-and-fix",
      "position": 2,
      "run_in": "child_job",
      "child_template": {
        "title": "Verify and repair the OpenSpec change",
        "role": "Verifier",
        "session_policy": "persistent",
        "workflow": [
          {"id": "verify", "command": "/openspec-verify-change"},
          {
            "id": "fix",
            "command": "Fix every finding, including minor findings"
          },
          {"id": "reverify", "command": "/openspec-verify-change"}
        ],
        "repeat": {
          "from": "verify",
          "until": "verification_has_no_findings",
          "max_attempts": 3
        },
        "escalation": {
          "major_finding": {
            "request_job": {
              "role": "Architect",
              "priority": 80
            },
            "resume_origin_session": true
          }
        }
      }
    },
    {
      "id": "sync",
      "position": 3,
      "run_in": "job_session",
      "command": "/openspec-sync-specs"
    },
    {
      "id": "archive",
      "position": 4,
      "run_in": "job_session",
      "command": "/openspec-archive-change"
    },
    {
      "id": "publish",
      "position": 5,
      "run_in": "job_session",
      "command": "Commit to main and push",
      "side_effect_class": "external_non_idempotent",
      "recovery_check": "Verify the expected commit on the remote branch"
    }
  ]
}
```

Commands inside the Verify/Fix child are still dispatched as one bounded batch
at a time. One workflow node may own multiple dispatches; partial results keep
that node active and only remaining work units enter a later dispatch.

## Runtime Sequence

1. Obtain the persisted action from `jobctl next`.
2. Perform only that generated external action.
3. For `child_job`, create a child request record before creating the job.
4. Enqueue accepted children and mark the parent `waiting`.
5. Run children through the global sequential queue.
6. Persist each child report before satisfying the parent wait condition.
7. Send child report references to the parent session.
8. Wait for acknowledgement without combining it with the next command.
9. Advance to the next node.
10. Record the response through `jobctl record`; never hand-edit parent,
    child, workflow, or queue state.

If an apply child discovers implementation tasks, it returns additional
`proposed_jobs`. The root orchestrator creates them as grandchildren, while
the apply child waits. Do not allow the apply child to mutate the queue or
start untracked subagents directly.

## Verification And Repair

Keep verification and repair in one persistent child session when repair
benefits from the verifier's context. Dispatch:

1. verification
2. repair, only when findings exist
3. verification again

Repeat within configured limits. Minor findings do not require escalation.
For major findings, pause the Verify/Fix child and create a separate advisory
job. Route its report back to the same Verify/Fix session before repair.

If the initial prompt explicitly requests reconsideration in the same session,
model it as another step in that job rather than calling it a separate
Architect job. Use a separate job whenever independent judgment, a distinct
role, or a durable decision artifact is required.

## Safety Limits

Configure:

- maximum hierarchy depth
- maximum children per job and per node
- maximum repeated child requests with the same signature
- maximum verification-repair attempts
- ancestor-cycle rejection
- explicit recovery checks for external side effects

Direct subagents created inside a child are opaque to the root orchestrator.
Permit them only when loss of their individual state and reports is acceptable.
Otherwise require tracked child-job requests.
