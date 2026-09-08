# Campaign Reference

The canonical campaign implementation is in `scripts/strategy_v6.py` and
`scripts/transaction_v6.py`. This reference documents campaign lifecycle,
branch management, cycle finalization, and publication.

## Campaign Lifecycle

1. **Initialize** — `init` creates a trusted v6 run with campaign envelope
2. **Strategy Compilation** — Default strategy compiled into phase sequence
3. **Initial Jobs** — First cycle jobs registered and dispatched
4. **Dynamic Cycles** — Goal Judge produces CONTINUE with expansion plans
5. **Expansion Commit** — CAS commit adds new jobs to graph
6. **Delivery** — Implementation, verification, review, finalization
7. **Goal Assessment** — Goal Judge evaluates terminal conditions
8. **Seal** — Terminal commit binds graph digest

## Campaign Envelope

The campaign envelope is frozen at initialization:

```json
{
  "schema_version": 6,
  "strategy_id": "default_adaptive",
  "strategy_version": 1,
  "strategy_mode": "full_campaign",
  "goal": "...",
  "limits": { "max_cycles": 10, "max_total_jobs": 100 }
}
```

The envelope cannot be modified after creation. Branch metadata is
persisted in the envelope by `CampaignBranchInitializer`.

## Feature Branch

Each campaign operates on a feature branch:

- Branch name: `campaign/{campaign_id}`
- Baseline commit: HEAD at initialization
- Cycle ID: Deterministic from campaign ID and timestamp

The `CampaignBranchInitializer` creates the branch and persists
branch info in the frozen envelope.

## Cycle Finalization

Each cycle is finalized through explicit worker jobs:

1. **Resolve OpenSpec Stores** — Re-resolve specs paths
2. **Sync Required Specs** — Ensure specs are present
3. **Archive Completed Changes** — Move to archive directory
4. **Verify Final Artifacts** — Confirm artifact presence

## Cycle Commit

`CycleCommitter` creates exactly one commit per accepted cycle:

- Filters to campaign-owned files (openspec/, docs/, strategy_*)
- Validates only allowed paths are committed
- Creates a single atomic commit
- Records commit hash and metadata

## Cycle Push

`CyclePusher` pushes the feature branch after each commit:

- Idempotency check prevents duplicate pushes
- Remote ref recovery verifies push success
- Observable recovery for push failures

## Publication

Publication is opt-in. Campaigns do not automatically publish results.
The root orchestrator decides when to publish based on:
- Goal Judge terminal decision
- All findings dispositioned
- All verification gates passed
- All review lenses satisfied
