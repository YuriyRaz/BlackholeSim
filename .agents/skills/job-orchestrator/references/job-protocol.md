# Worker Contract

You execute one assigned job in one persistent conversation. Follow the job
prompt's workspace boundaries, requirements, constraints, and completion
conditions. Do not schedule work or mutate orchestration-owned state.

## Work and durable artifacts

1. Read the complete job prompt.
2. Perform only the assigned work using the requested method.
3. Keep the contracted `report.md` current; write `checkpoint.md` when its
   minimal replacement context would help recovery.
4. Place artifacts only in the paths authorized by the prompt.

`checkpoint.md` is recovery evidence, not an orchestration-state contract.

## Return a normalized outcome

Return exactly one outcome:

```json
{"status":"completed","summary":"what was accomplished","report_path":"path/to/report.md"}
```

```json
{"status":"needs_input","summary":"where work stopped","question":"precise question","context":"optional context"}
```

```json
{"status":"failed","summary":"what failed and why"}
```

Only claim `completed` after satisfying the job's completion conditions. Ask
blocking questions early. Do not blindly repeat a possible side effect; follow
the prompt's recovery check first. A replacement worker inspects the supplied
report, checkpoint, transcript reference, and workspace observations before
continuing.

Workers may recommend follow-up work in their report, but only the root
operator creates explicit jobs.

## Trusted v5 Output Contract

The worker exclusively owns the semantic content of its report, checkpoint,
raw response, normalized outcome, completion claim, and condition results. The
root MUST NOT create, complete, repair, summarize, or replace these artifacts.

The generated prompt provides both a canonical reference such as
`run://RUN-123/jobs/J001/report` and an absolute authorized write path. Return
the reference and SHA-256 content digest in the adapter response. A report that
exists at a plausible path but is stale, cross-run, changed, or absent from the
verified response is not evidence of completion.

Return condition results with stable IDs and one of `passed`, `failed`,
`not_run`, `unavailable`, or `unknown`. Only `passed` satisfies a required
condition, and evidence-bearing passes must name accepted artifact references.
Return exactly one normalized JSON outcome through the worker transport. Never
write an outcome file for the root to copy into the control plane.

If the response format is rejected while the session is live, follow the
same-session formatting-repair continuation. If the response is empty while
the session is live, follow the response-retrieval continuation. Do not repeat
non-idempotent work blindly; interruption recovery is owned by the control
plane.
