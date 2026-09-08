# LEGACY: Root Session Orchestration

> **⚠️ DEPRECATED**: This file documents the legacy root-session control-loop approach.
> The recommended approach is the standalone orchestrator script documented in
> [SKILL.md](../SKILL.md#standalone-orchestrator-script).
>
> This file is retained for backward compatibility. It will be removed in a future version.
> Use the script approach for new orchestration work.

---

## Dynamic Normal Loop Operations

The normal control loop iterates through `next` calls:

| Operation | Root action |
| --- | --- |
| `prepare_dispatch` | Run `prepare-dispatch` with the returned job, revision, and dependency digest. |
| `commit_expansion` | Run `commit-expansion` with expansion_id, expected_graph_revision, expected_graph_digest, and plan_digest for compare-and-swap. |
| `start_job` | Create a worker session and send the persisted prompt verbatim. |
| `resume_job` | Send the returned continuation prompt to the existing session. |
| `ask_user` | Obtain the requested answer, then record it with `answer`. |
| `wait` | Wait for a transport event; do not invent state. |
| `recover` | Run `recover` when `next` returns a recovery-required operation. |
| `run_complete` | Relay `run_status` and `successful`; do not equate terminal with success. |

`next` is byte-for-byte read-only. Dispatch creation is the locked mutation:

```text
python scripts/jobctl.py prepare-dispatch --run <run-root> --job <job-id> --expected-revision <revision> --dependency-evidence-digest <digest>
```

Expansion commits use compare-and-swap:

```text
python scripts/jobctl.py commit-expansion --run <run-root> --expansion <expansion-id> --expected-graph-revision <revision> --expected-graph-digest <digest> --plan-digest <digest>
```

## Structured Question Format

When the orchestrator sends a question to the UI session, it uses this format:

```
[WORKER QUESTION]
Question ID: Q-001
Job ID: JOB-001
Run: .job-orchestrator/runs/RUN-XXX
---
<question text>
---
Context: <context>
```

The agent must parse `question_id` and `job_id` from this format to pass them to the `answer` command.

## Answering Questions

When the agent receives a question message from the orchestrator:

1. Parse `question_id` and `job_id` from the message
2. Obtain the user's response
3. Invoke the answer command:
   ```bash
   python scripts/jobctl.py answer --run <run> --question-id <id> --answer <reply>
   ```

## Listing Pending Questions

To check for outstanding questions:

```bash
python scripts/jobctl.py pending --run <run>
```

Returns a JSON array of unanswered questions with `question_id`, `job_id`, `question`, and `asked_at`.

---

**For the current orchestration approach, see [SKILL.md](../SKILL.md#standalone-orchestrator-script).**
