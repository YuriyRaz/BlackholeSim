# TDE Physics Rebuild Completion

Finish the `rebuild-tde-physics-core` work honestly and end to end.

The previous run was recorded as completed, but its own reports disclose missing
browser, benchmark, and README evidence. The OpenSpec task list also leaves
groups 1-3 unchecked, while groups 6-7 contain claims not supported by the
reported verification. Audit the implementation rather than trusting prior
completion claims, repair every confirmed defect, and independently verify the
result against `GREAT_GOAL.md`.

The root session is only the job-orchestrator control plane. All repository
investigation, editing, testing, visual verification, and synthesis must happen
inside explicit persistent jobs. Continue the `jobctl next` loop until it
returns `run_complete`.
