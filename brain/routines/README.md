# `brain/routines/` — daily routine reports

This folder is the reviewed-memory channel for the [daily improvement routine](../../.claude/routines/daily-improvement.md). Proposal-bearing runs may add a `YYYY-MM-DD.md` file (UTC date) describing what the routine considered and proposed.

`index.md` is the cross-run URL ledger — read by the routine before every scan so it can dedup against prior days' findings without re-fetching everything.

## File layout

```text
brain/routines/
├── README.md           ← you are here
├── index.md            ← merged cross-run URL ledger
└── YYYY-MM-DD.md       ← proposal-bearing run record
```

## Why these are committed

CSIS's `brain/` folder is durable working memory across context windows — see `brain/README.md` for the broader doctrine. Routine records land here for the same reason snapshots do: so the next agent (human or AI) picking this up cold has a human-reviewed audit trail. The record, ledger update, implementation, and tests share one proposal PR and become durable only after a human merges it.

Quiet days, deferred-only scans, and runs stopped by the open-PR cap remain text-only session results. They do not create log-only PRs. Missing dates are therefore expected and do not imply that the schedule failed.

## Reading order if you're picking this up cold

1. `index.md` — what URLs have been considered, and what we did with each
2. The latest date file — the most recent merged proposal-bearing run's findings
3. The first preceding date file with `items_opened_pr > 0` — the most recent run that actually shipped code

## Manual cleanup

The routine never deletes prior records. If `brain/routines/` grows past a year or so, a human may archive files older than 6 months into `brain/routines/archive/YYYY/` in a separate maintenance PR. Preserve ledger entries and source-PR provenance during any consolidation.
