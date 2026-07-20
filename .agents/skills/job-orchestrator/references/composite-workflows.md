# Composite Workflows

## Maintainer Guidance: Composite Workflows

Use a composite job when one persistent session needs to own an arbitrary
multi-stage workflow. A composite job may perform research, implementation,
verification, repair, and synthesis in one conversation while its context is
useful across those stages.

If work requires a distinct role, independent judgment, separate report,
scheduling dependency, user-visible recovery boundary, or isolated external
effect, the orchestrator creates another explicit job rather than a hidden
execution layer.

```text
one persistent job:  apply -> verify by any method -> repair -> report

separate jobs:       implement -> independent review -> conditional repair

one job:             investigate only, no verification stage
```

## Persistent Job Owns Arbitrary Phases

A persistent job may execute an arbitrary sequence of phases within one
conversation. The job prompt can prescribe an ordered workflow, or leave
the method open. The job is not split into orchestrator-visible steps or
dispatches.

Example: a single job may implement a change, verify it by any suitable
method, repair findings, re-verify, and produce a final report. All of
this happens in one persistent conversation with one normalized outcome.

The orchestrator stores the workflow as prompt instructions. It does not
interpret skill names, verification methods, or workflow stages as protocol
states.

## Independently Scheduled Work Becomes Another Job

When a phase of work needs any of the following, represent it as a separate
explicit job:

- **Independent scheduling**: the phase may run at a different time or
  priority.
- **Independent responsibility**: a different role owns the work and its
  judgment.
- **Separate report**: the phase produces its own durable report artifact.
- **Scheduling dependency**: the phase must complete before other work can
  proceed, and the origin job cannot continue until it does.
- **Recovery boundary**: the phase has different side-effect or recovery
  requirements.
- **User-visible decision**: the phase requires its own user interaction or
  authority.

### Example: Advisory Job

When a job returns `needs_input` and the question requires separate
architecture consultation:

1. The orchestrator creates an architect job as an ordinary explicit job.
2. The origin job is marked `waiting_for_job` with the architect job in
   `waiting_on`.
3. When the architect job completes with a report, the origin job receives
   that report as a related report.
4. The origin session resumes with the continuation prompt containing the
   architect report.

### Example: Verification Job

When the orchestration plan requests independent verification:

1. The orchestrator creates a verification job with `depends_on` pointing
   to the implementation job.
2. The verification job receives the implementation report as context.
3. The verification job returns its own report with findings.
4. If findings require repair, a repair job may be created, or the origin
   job may handle repair in its own session.

## Job Relationships

### Dependencies

`depends_on` lists job IDs that must be `completed` before a job becomes
eligible for scheduling. Dependencies express ordering, not parent-child
ownership.

### Parent Relationship

`parent_job_id` indicates that a job was created as part of another job's
work. Parent jobs may wait on child jobs using `waiting_on`. Parent
relationships describe ownership but do not create a second scheduler.

### Waiting

`waiting_on` lists job IDs whose terminal reports are required before the
origin session can continue. A job in `waiting_for_job` does not occupy a
sequential execution slot.

## Safety Limits

Configure limits as appropriate:

- maximum job hierarchy depth
- maximum jobs per run
- maximum repeated jobs with the same purpose
- ancestor-cycle rejection

## Direct Subagents

Direct subagents created inside a job session are opaque to the root
orchestrator. Permit them only when loss of their individual state and
reports is acceptable. Otherwise require explicit job creation through the
orchestrator.
