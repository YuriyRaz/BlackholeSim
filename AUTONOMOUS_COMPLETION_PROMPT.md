# Autonomous Completion Prompt

This prompt is reusable for executing the job-orchestrator control loop to
drive a TDE completion run to `run_complete`. It must be used by a **root
session** (control plane only) — never by a worker session performing domain
work.

## Prerequisites

1. Read `.job-orchestrator/inputs/tde-completion-request.md` to understand the
   completion goal and acceptance criteria.
2. Read `.job-orchestrator/inputs/tde-completion-jobs.json` to understand the
   job definitions and dependencies.
3. Ensure `scripts/jobctl.py` is available at the workspace root.

## Control Loop

Execute the following loop until `jobctl next` returns `run_complete`:

### Step 1: Initialize (first run only)

```bash
python scripts/jobctl.py init \
  --request-file .job-orchestrator/inputs/tde-completion-request.md \
  --goal "Complete all TDE rebuild tasks and verify full test suite passes"

python scripts/jobctl.py register \
  --run .job-orchestrator/runs/<run-id> \
  --definition .job-orchestrator/inputs/tde-completion-jobs.json
```

### Step 2: Loop

```bash
python scripts/jobctl.py next --run .job-orchestrator/runs/<run-id>
```

| `jobctl next` result | Root action |
|----------------------|-------------|
| `start_job`          | Create a **real persistent worker session** (not an invented reference). Send the returned prompt verbatim. Record the session with `jobctl session`. |
| `resume_job`         | Send the returned continuation prompt to the **existing** worker session identified by session ID. |
| `ask_user`           | Obtain the requested authority or answer from the user, then record it with `jobctl answer`. |
| `wait`               | Wait for a transport event. Do not invent state. |
| `run_complete`       | Report completion. Stop the loop. |

## Hard Constraints

### No root-session domain work
The root session MUST NOT perform implementation, investigation, verification,
or synthesis work directly. All domain work MUST be routed to explicit jobs
executed by real persistent worker sessions.

### Real persistent worker sessions
Every `start_job` action MUST create a real worker session with a genuine
conversation context. Never fabricate session references, never claim a
"phantom" session exists, and never use `completed` status for sessions that
were never actually created.

### Evidence-gated outcomes
No job may be marked `completed` without:
1. A `report.md` that documents what was changed.
2. Concrete evidence (test output, file diffs, verification logs) referenced
   in the report.
3. All acceptance criteria from the job definition satisfied.

### Continuation until run_complete
The loop MUST continue until `jobctl next` returns `run_complete`. Do not
prematurely terminate the loop by:
- Declaring "all jobs done" without `jobctl` confirmation.
- Skipping `next` calls because the goal "seems met."
- Fabricating a `run_complete` result.

## Outcomes

Each worker session MUST return exactly one normalized outcome:

```json
{"status":"completed","summary":"...","report_path":"jobs/Jxxx/report.md"}
```

```json
{"status":"needs_input","summary":"...","question":"...","context":"..."}
```

```json
{"status":"failed","summary":"..."}
```

Only claim `completed` after the job's report and evidence satisfy all
completion conditions. Ask blocking questions early.

## Example Completion Sequence

```
1. init → register
2. next → start_job J001 → session-abc created → session J001 → session-abc
3. (worker completes) → outcome J004 → {"status":"completed",...}
4. next → start_job J002 → session-def created → session J002 → session-def
5. (worker completes) → outcome J002 → {"status":"completed",...}
6. next → start_job J003 → session-ghi created → session J003 → session-ghi
7. (worker completes) → outcome J003 → {"status":"completed",...}
8. next → run_complete → REPORT
```

## Recovery

If `jobctl` reports corruption or an unrecoverable state, follow
`.agents/skills/job-orchestrator/references/recovery.md`. Do not manually
patch persisted run-state JSON.
