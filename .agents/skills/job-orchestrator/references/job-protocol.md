# Worker Contract

You execute one assigned job in one persistent conversation. Follow the job
prompt's workspace boundaries, requirements, constraints, and completion
conditions. Do not schedule work or mutate orchestration-owned state.

## Work And Durable Artifacts

1. Read the complete job prompt.
2. Perform only the assigned work using the requested method.
3. Keep the contracted `report.md` current; write `checkpoint.md` when minimal
   replacement context would help recovery.
4. Place artifacts only in paths authorized by the prompt.

`checkpoint.md` is recovery evidence, not authoritative control-plane state.

## Return Contract

Return exactly one normalized JSON outcome through the worker transport. Do not
write an outcome file. The adapter binds the response identity and schema
version after receiving the exact raw response.

Completed example:

```json
{
  "status": "completed",
  "summary": "Implemented and verified the requested change.",
  "artifacts": [
    {
      "ref": "run://RUN-123/jobs/J001/report",
      "content_sha256": "<sha256>"
    }
  ],
  "condition_results": [
    {
      "schema_version": 6,
      "condition_id": "TESTS",
      "target_job_id": "J001",
      "target_gate_revision": 1,
      "run_id": "RUN-123",
      "cycle_id": "CYC-1",
      "status": "passed",
      "producer_job_id": "J002",
      "assignment_id": "VASSIGN-1",
      "evidence_refs": ["run://RUN-123/jobs/J001/report"],
      "recorded_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Needs-input example:

```json
{"status":"needs_input","summary":"Blocked on authority.","question":"May I perform the external mutation?","context":"The job requires explicit approval."}
```

Failed example:

```json
{"status":"failed","summary":"Verification failed and no safe repair remained."}
```

Only claim `completed` after satisfying the job's completion conditions. Return
condition results as the plural `condition_results` array shown above — the wire
form. Report `status` in the wire vocabulary: one of `passed`, `failed`,
`not_run`, `unavailable`, or `unknown`. The control plane normalizes each entry
into a persisted record, translating the wire `status` into the record status
(`passed` → `met`, `failed` → `unmet`, `not_run` → `pending`, `unavailable`/
`unknown` → `error`) and deriving the authoritative verdict; do not send a
record-vocabulary status or a `verdict` field yourself. Each entry MUST also
carry the fields the control plane validates:
`schema_version` (6), a stable uppercase `condition_id`, the `target_job_id` and
`target_gate_revision` it verifies, `run_id`, `cycle_id`, `producer_job_id`, and
`recorded_at`. A verifier that was given an `assignment_id` MUST echo it; the
control plane accepts the result only for the assignment owned by the submitting
verifier and rejects a result carrying another verifier's assignment.
Only `passed` satisfies a required condition, and evidence-bearing passes MUST
name accepted artifact references in `evidence_refs`. The control plane derives
the authoritative pass/fail verdict from `status`; a `verdict` field in the
payload is advisory only and never overrides the derived value.

The worker exclusively owns the semantic content of its report, checkpoint,
raw response, normalized outcome, completion claim, and condition results. The
root MUST NOT create, complete, repair, summarize, or replace these artifacts.
A report that exists at a plausible path but is stale, cross-run, changed, or
absent from the verified response is not evidence of completion.

If the response format is rejected while the session is live, follow the
same-session formatting-repair continuation. If the response is empty while the
session is live, follow the response-retrieval continuation. Do not repeat
non-idempotent work blindly; interruption recovery is owned by the control
plane.
