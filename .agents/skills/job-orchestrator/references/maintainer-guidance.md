# Maintainer Guidance

Use this index when changing the skill or designing multi-job workflows.

- [Composite workflows](composite-workflows.md): decide when work needs one
  persistent job or separately scheduled jobs.
- [Continuous improvement](continuous-improvement.md): turn durable evidence
  into narrowly scoped, validated skill maintenance.
- [Strategy](strategy.md): canonical strategy definition, compilation modes,
  and composition operations.
- [Dynamic graph](dynamic-graph.md): graph state, append-only records,
  digest computation, and expansion transactions.
- [Architect roles](architect-roles.md): Architect role boundaries, evidence
  requirements, and prohibited patterns.
- [Campaign](campaign.md): campaign lifecycle, branch management, cycle
  finalization, and publication.

Protocol semantics belong in [protocol.md](protocol.md); worker instructions
belong in [job-protocol.md](job-protocol.md). Do not duplicate them here.

Protocol changes must include schema, receipt, transition, recovery, artifact,
completion-gate, and documentation-conformance tests. Do not weaken provenance
checks or accept state that lacks the required authenticated evidence.
