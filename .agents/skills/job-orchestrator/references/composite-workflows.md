# Composite Workflows

Use a composite job when one persistent session should own an arbitrary
multi-stage workflow. A composite job may perform research, implementation,
verification, repair, and synthesis while its context remains useful.

If work requires independent scheduling, independent judgment, a separate
report, a scheduling dependency, a recovery boundary, or isolated external
effects, register another explicit job instead of a hidden execution layer.

```text
one persistent job:  apply -> verify -> repair -> report
separate jobs:       implement -> independent verification -> conditional repair
one job:             investigate only
```

## Persistent Jobs

A persistent job may execute an arbitrary sequence of phases within one
conversation. The prompt can prescribe an ordered workflow or leave the method
open. The orchestrator stores the workflow as prompt instructions; it does not
interpret skill names, verification methods, or workflow stages as protocol
states.

## Explicit Jobs

Use separate jobs for independently scheduled or independently owned work.
Express ordering with `depends_on`. Dependencies must complete before a job is
eligible for scheduling and automatically propagate accepted worker-attested
reports in deterministic order.

For independent verification, assign the verifier in the target completion
condition. The verifier schedules from `completion_claimed`, and only that
verifier's authenticated condition result can satisfy the independent gate.

`related_reports` provides additional attested context. It does not replace
dependency ordering, automatic dependency-report propagation, or verifier
authority.

## Expansion Workflows

The v6 protocol adds dynamic graph expansion. Expansion workflows:

1. Goal Judge produces CONTINUE with expansion_plan
2. Expansion is staged with canonical identities
3. CAS commit adds new jobs to graph
4. New jobs are dispatched in subsequent cycles

Expansion workflows support:
- **Hypothesis investigation** — one job per hypothesis
- **Synthesis** — consume all settled hypotheses
- **Work planning** — select path and produce expansion
- **Implementation delivery** — execute the plan

## Safety Limits

Configure limits for maximum jobs per run, repeated jobs with the same purpose,
and dependency-cycle rejection.

Direct subagents created inside a job session are opaque to the root
orchestrator. Permit them only when loss of their individual state and reports
is acceptable. Otherwise require explicit job registration.
