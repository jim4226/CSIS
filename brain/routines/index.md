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
| (operational) | 2026-07-18 | flagged | `claude/daily-*` PR backlog is **101 open PRs**, oldest from 2026-05-20 — still none merged/closed. Up from 87 on 2026-07-08. Confirmed duplicate: PR #94 (2026-07-08) and PR #105 (2026-07-17) both add a GRAM dual-use-knowledge note independently. Escalating since 2026-06-30 (PR #82); unresolved. See 2026-07-18 log for the full note and recommendation. |
| (note) | 2026-07-18 | — | `main`'s copy of this ledger predates every `claude/daily-*` PR (none have merged), so it does not carry forward rows already triaged by unmerged branches. This run's actual dedup was done against `claude/daily-2026-07-17-log` (PR #107)'s `index.md`/day file, not this file — 0 new in-window items found, so no new triage rows are added here. Do not treat this file's brevity as "little has been triaged"; see the operational note above and `brain/routines/2026-07-18.md`. |
