# State Schema

The canonical field definitions and validity rules are the version-4 JSON
schemas in [`../schemas/v4/`](../schemas/v4/). `jobctl --help` is authoritative
for command parameters.

`run.json` and `jobs/*/job.json` are authoritative run state; `jobs/index.json`
is a rebuildable discovery index. Operators do not manually inspect, edit, or
reconstruct any of them. Use [recovery.md](recovery.md) for supported audit,
recovery, and repair routing.

Worker reports and optional checkpoints are durable work evidence, not
authoritative control-plane state.
