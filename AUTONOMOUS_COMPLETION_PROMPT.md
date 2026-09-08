# Autonomous Completion Prompt

Use this prompt only in a **root control-plane session**. The root must route
all repository investigation, implementation, testing, verification, report
writing, and domain decisions to persistent worker jobs.

## Prerequisites

1. Read `.job-orchestrator/inputs/tde-completion-request.md` for the goal and
   acceptance conditions.
2. Read `.job-orchestrator/inputs/tde-completion-jobs-v6.json` for v6 job
   definitions and dependencies.
3. Set `JOBCTL_PYTHON` to the Python executable installed for this environment.
   Do not assume that `python` is on PATH.

```powershell
$env:JOBCTL_PYTHON = "C:\Projects\AkitoBlogBot\.venv\Scripts\python.exe"
```

4. Use the actual control-plane script:
   `.agents/skills/job-orchestrator/scripts/jobctl.py`.

## Initialize

PowerShell command shape:

```powershell
& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py init `
  --request-file .job-orchestrator/inputs/tde-completion-request.md `
  --goal "Complete all TDE rebuild tasks and verify every required condition"

& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py register `
  --run .job-orchestrator/runs/<run-id> `
   --definition .job-orchestrator/inputs/tde-completion-jobs-v6.json
```

`--outcome`, `--receipt`, and `--evidence` options consume file paths. They do
not accept inline JSON.

## Control Loop

Repeat the read-only `next` query until it returns `operation: run_complete`.
When it returns `prepare_dispatch`, run the locked preparation command before
starting the host Task:

```powershell
& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py next `
  --run .job-orchestrator/runs/<run-id>
```

| Result | Root action |
| --- | --- |
| `prepare_dispatch` | Run `prepare-dispatch --job <job-id> --expected-revision <revision> --dependency-evidence-digest <digest>`, then send the persisted prompt. |
| `start_job` | Send the returned prompt byte-for-byte through the configured transport. Record the adapter-issued receipt with `launch-receipt`. |
| `resume_job` | Send the returned continuation prompt byte-for-byte to the existing native session. Record its adapter-issued launch/resume receipt. |
| `ask_user` | Obtain the requested authority, then run `answer`; process the immediate `resume_job` result on the same worker session. |
| `wait` with `reason: advisory_decision_required` | Make the explicit advisory decision with `advisory-decision`. Do not treat this as an ordinary transport wait. |
| `wait` with `reason: transport_unavailable` | The transport cannot reach the worker. Wait for connectivity to resume before retrying. |
| `wait` with `reason: dependency_pending` | A required upstream job has not completed. Continue the control loop to process upstream jobs. |
| ordinary `wait` | Wait for a transport event. Do not invent state from workspace files. |
| `run_complete` | Stop. Treat only `run_status: completed` and `successful: true` as successful completion. Failed and canceled runs are terminal but unsuccessful. |

## Receipt Ingestion

The worker owns the semantic response and report. The root only relays exact
adapter receipts:

```powershell
& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py launch-receipt `
  --run .job-orchestrator/runs/<run-id> `
  --receipt <adapter-launch-receipt.json>

& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py response-receipt `
  --run .job-orchestrator/runs/<run-id> `
  --receipt <adapter-response-receipt.json>

& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py answer `
  --run .job-orchestrator/runs/<run-id> --job <job-id> `
  --answer "<answer>" --source user

& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py advisory-decision `
  --run .job-orchestrator/runs/<run-id> --origin <origin-job-id> `
  --advisory <advisory-job-id> `
  --decision <keep_waiting|ask_user|select_another|fail_origin> `
  [--replacement <replacement-job-id>] `
  [--reason "<reason-text>"]
```

Never invent a session reference, edit a worker prompt, create or replace a
worker report, or synthesize an outcome from workspace observations. v6 rejects
standalone `session` and `outcome` submissions because they have no transport
provenance.

## Recovery

Cancellation, loss, unavailable status, empty response with uncertain liveness,
or contradictory transport evidence exits the normal loop:

```powershell
& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py audit `
  --run .job-orchestrator/runs/<run-id>

& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py recover `
  --run .job-orchestrator/runs/<run-id> `
  --job <job-id> `
  --evidence <recovery-evidence.json>
```

Recovery evidence must be a file containing a valid v6 recovery-evidence record:

```json
{
  "schema_version": 5,
  "job_id": "<job-id>",
  "observed_at": "<ISO-8601-timestamp>",
  "classification": "canceled|lost|unknown|contradictory|active|returned",
  "transport": { },
  "recovery_id": "<unique-recovery-id>",
  "side_effect_check": {
    "check_id": "<configured-check-id>",
    "observation": "<direct-observation>",
    "result": "retry_safe|effect_confirmed|unknown",
    "reference": "<direct-evidence-reference>",
    "idempotency_key": "<registered-key-or-null>"
  }
}
```

Do not start a replacement until recovery explicitly authorizes it. Preserve
all prior session attempts. For non-idempotent effects, include the configured
external side-effect check in recovery evidence.

## Repair

Use `repair` only for an explicit failed or canceled disposition; it cannot
claim completion:

```powershell
& $env:JOBCTL_PYTHON .agents/skills/job-orchestrator/scripts/jobctl.py repair `
  --run .job-orchestrator/runs/<run-id> `
  --job <job-id> `
  --disposition failed `
  --reason "<reason-text>"
```

The `--disposition` must be exactly `failed` or `canceled`.

## Sample Sequence

A correct orchestration starts every job before recording any response. The
following two-job example (J001 implements, J002 verifies independently)
shows the full lifecycle:

```
1.  init      → run created
2.  register  → jobs registered
3.  next      → {operation: prepare_dispatch, job_id: J001, expected_revision: N}
4.  prepare-dispatch → {operation: start_job, job_id: J001}
5.  launch-receipt  → J001 session established
6.  next      → {operation: prepare_dispatch, job_id: J002, expected_revision: N}
7.  prepare-dispatch → {operation: start_job, job_id: J002}
8.  launch-receipt  → J002 session established
9.  response-receipt → J001 completion_claimed
10. response-receipt → J002 completed
11. next      → {operation: run_complete, successful: true}
```

Steps 3-4 and 5-6 must both occur before step 7. A job must be started
(receipt recorded) before its response can be recorded.
