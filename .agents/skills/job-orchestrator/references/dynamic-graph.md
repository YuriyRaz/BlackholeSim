# Dynamic Graph Reference

The canonical graph model is in `scripts/graph_v6.py`. This reference
documents graph state, append-only records, digest computation, and
expansion transactions.

## Graph Status Lifecycle

```
planning → pending → committing → open → planning (next cycle)
                 ↓                   ↓
           canceling            sealed
                 ↓                   ↓
              sealed         recovery_required
```

Transitions are validated by `transition_graph_status()`. Only allowed
transitions succeed; invalid transitions raise `OrchestratorError`.

## Append-Only Records

| Record | Key | Overwrite Policy |
|--------|-----|------------------|
| Job | `job_id` | append-only |
| Edge | `edge_id` | append-only |
| Verifier Assignment | `assignment_id` | append-only |
| Repair Gate | `history_id` | append-only |
| Expansion | `expansion_id` | append-only |
| Batch | `batch_id` | append-only |

## Graph Digest

The graph digest is computed over immutable topology and authority fields:

- Envelope (limits, strategy)
- Job identities (job_id, role, purpose_key, generation, origin, authority)
- Edge identities (edge_id, source, target, type, revision)
- Verifier assignments (assignment_id, target, gate revision, verifier)
- Repair gate history (history_id, target, revision, repair, finding, status)
- Batch membership (batch_id, status, job_ids)
- Terminal outcomes (outcome_type, graph_revision, graph_digest)

Volatile state (status, timestamps, runtime data) is excluded.

## Expansion Transactions

An expansion transaction follows this lifecycle:

1. **Plan** — Work Planner produces expansion_plan
2. **Stage** — ExpansionStager assigns identities, renders prompts
3. **Manifest** — TransactionManifest persists durable manifest
4. **CAS Commit** — ExpansionCommitter validates compare-and-swap
5. **Visibility** — Graph revision advanced, new records visible
6. **Cleanup** — Staged bytes and manifest removed

Compare-and-swap checks:
- `expected_graph_revision` matches actual
- `expected_graph_digest` matches actual
- `expansion_id` matches manifest
- `plan_digest` matches manifest

## Identity Generation

All identities use `stable_id()` with deterministic inputs:

- `EXP-{hash}` — expansion ID
- `BATCH-{hash}` — batch ID
- `DEC-{hash}` — decision ID
- `JOB-{hash}` — global job ID
- `EDGE-{hash}` — edge ID

Pattern: `[A-Z][A-Z0-9_-]{0,127}`

## Immutable Ceilings

Limits are set at campaign creation and cannot be changed:

- `max_total_jobs` — total job count ceiling
- `max_jobs_per_cycle` — per-expansion job ceiling
- `max_cycles` — cycle count ceiling
- `max_vertices` — graph vertex ceiling
- `max_edges` — graph edge ceiling
- `max_expansion_depth` — expansion depth ceiling
- `fan_out_limit` — fan-out ceiling
- `max_concurrency` — concurrent job ceiling
- `max_external_effects` — external effect ceiling
- `max_prompt_size` — prompt size ceiling
- `max_plan_size` — plan size ceiling
- `max_time_seconds` — time ceiling
- `max_cost` — cost ceiling
