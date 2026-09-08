# Maintainer Guidance

Use this index when changing the skill or designing multi-job workflows.

- [Composite workflows](composite-workflows.md): decide when work needs one
  persistent job or separately scheduled jobs.
- [Continuous improvement](continuous-improvement.md): turn durable evidence
  into narrowly scoped, validated skill maintenance.

Protocol semantics belong in [protocol.md](protocol.md); worker instructions
belong in [job-protocol.md](job-protocol.md). Do not duplicate them here.

Trusted protocol changes must include schema, receipt, transition, recovery,
artifact, completion-gate, and documentation-conformance tests. Do not weaken
provenance checks to preserve a legacy workflow; label v4 evidence as
`legacy_unattested` and collect new worker/verifier evidence in v5.
