# State Schema

The canonical field definitions and validity rules are the JSON schemas in
[`../schemas/v6/`](../schemas/v6/). `jobctl --help` is authoritative for command
parameters.

## V6 Schema Registry

All 41 v6 schemas are listed in `orchestrator_core.SCHEMA_REGISTRY`:

| Schema | Purpose |
|--------|---------|
| `run` | Top-level run state |
| `setup` | Initialization configuration |
| `job-definition` | Job registration |
| `job` | Persistent job state |
| `dispatch` | Immutable dispatch record |
| `outcome` | Worker outcome |
| `artifact` | Worker artifact |
| `completion-claim` | Worker completion claim |
| `condition-result` | Verification condition result |
| `terminal-commit` | Terminal graph seal |
| `recovery` | Recovery evidence |
| `verifier-assignment` | Verifier binding |
| `repair-gate-history` | Repair gate revision |
| `campaign-envelope` | Frozen campaign config |
| `graph-policy` | Graph constraints |
| `authority` | Authority scope |
| `role` | Role definition |
| `role-result` | Role-typed execution result |
| `context-snapshot` | Context binding |
| `typed-dependency-edge` | Typed graph edge |
| `dynamic-batch` | Batch membership |
| `progress-fingerprint` | Progress measurement |
| `goal-judgment` | Goal Judge decision |
| `finding` | Finding record |
| `finding-group` | Finding group |
| `hypothesis-result` | Hypothesis investigation result |
| `synthesis-result` | Synthesis output |
| `work-plan` | Work plan decision |
| `campaign-terminal-claim` | Terminal campaign claim |
| `strategy-decision` | Strategy decision |
| `graph-expansion-plan` | Expansion plan |
| `retained-expansion` | Retained expansion |
| `expansion-commit` | Expansion commit |
| `graph-transaction` | Transaction manifest |
| `activation` | Job activation |
| `graph-generation` | Graph generation |
| `goal-gate` | Goal gate |
| `goal-gate-result` | Goal gate result |
| `response-transaction` | Response transaction receipt |
| `finding-disposition` | Finding disposition |
| `cancellation-transaction` | Cancellation record |

## Authoritative State

`run.json` and `jobs/*/job.json` are authoritative run state; `jobs/index.json`
is a rebuildable discovery index. Operators do not manually inspect, edit, or
reconstruct any of them. Use [recovery.md](recovery.md) for supported audit,
recovery, and repair routing.

Worker reports and optional checkpoints are durable work evidence, not
authoritative control-plane state.
