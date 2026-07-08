# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| (none) | (initial) | quiet-day-empty | Ledger initialized; first real entries land on the routine's first scheduled run. |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-08 | opened-PR | GRAM dual-use knowledge compartmentalization; theme 3. Doc-only note at `brain/research/03-dual-use-knowledge-compartments.md`. |
| (operational) | 2026-07-08 | flagged | `claude/daily-*` PR backlog is **87 open PRs**, oldest from 2026-05-20 — none ever merged/closed. Corrects prior runs' "40+" estimate (full `list_pull_requests` scan, not default first page). See 2026-07-08 log for the full breakdown and recommended merge order. Escalating since 2026-06-30 (PR #82); unresolved. |
| (note) | 2026-07-08 | — | This row and the one above are the only rows this run added. `main`'s copy of this ledger predates every `claude/daily-*` PR (none have merged), so it does not carry forward the dozens of rows already triaged by unmerged branches through 2026-07-07 (see `claude/daily-2026-07-07-log`, PR #93, for that reconstructed ledger). Do not treat this file's brevity as "little has been triaged" — see the operational note. |
