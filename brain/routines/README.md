# `brain/routines/` — daily routine reports

This folder is the output channel for the [daily improvement routine](../../.claude/routines/daily-improvement.md). One file per day, named `YYYY-MM-DD.md` (UTC date), each one a structured report of what the routine considered and what it shipped.

`index.md` is the cross-run URL ledger — read by the routine before every scan so it can dedup against prior days' findings without re-fetching everything.

## File layout

```text
brain/routines/
├── README.md           ← you are here
├── index.md            ← cross-run URL ledger (append-only)
└── YYYY-MM-DD.md       ← one per run, structured per the routine's output contract
```

## Why these are committed

CSIS's `brain/` folder is durable working memory across context windows — see `brain/README.md` for the broader doctrine. Routine logs land here for the same reason snapshots do: so the next agent (human or AI) picking this up cold has the audit trail.

A quiet day still gets a committed log. Absence of news is itself a signal, and the cycle log already established that omitted evidence is the failure mode that bites hardest.

## Reading order if you're picking this up cold

1. `index.md` — what URLs have been considered, and what we did with each
2. The highest-numbered date file — the most recent run's findings
3. The first preceding date file with `items_opened_pr > 0` — the most recent run that actually shipped code

## Manual cleanup

The routine is append-only; it never deletes prior days' logs. If `brain/routines/` grows past a year or so, archive everything older than 6 months into `brain/routines/archive/YYYY/` as a separate maintenance PR. Don't delete entries from `index.md` — its whole point is to remember forever.
