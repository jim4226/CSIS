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
| https://www.anthropic.com/news/position-open-weights-models | 2026-07-27 | out-of-scope | Public-policy stance on open-weights releases; no CSIS theme mapping |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-07-27 | out-of-scope | Enterprise partnership announcement; no CSIS theme mapping |
| https://platform.claude.com/docs/en/release-notes/overview#memory-store-webhooks-2026-07-22 | 2026-07-27 | opened-PR | Backfilled from unmerged `claude/daily-2026-07-26-log` branch — see PR #119 (not yet merged) |
| https://www.anthropic.com/news/claude-opus-5 | 2026-07-27 | deferred | Backfilled from unmerged `claude/daily-2026-07-26-log` branch — design sketch in 2026-07-26.md (not yet merged) |
| https://platform.claude.com/docs/en/release-notes/overview#mid-conversation-tool-changes-2026-07-24 | 2026-07-27 | deferred | Backfilled from unmerged `claude/daily-2026-07-26-log` branch — design sketch in 2026-07-26.md (not yet merged) |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-27 | out-of-scope | Backfilled from unmerged `claude/daily-2026-07-26-log` branch (not yet merged) |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-27 | out-of-scope | Backfilled from unmerged `claude/daily-2026-07-26-log` branch (not yet merged) |
| https://www.anthropic.com/news/donation-public-first-action | 2026-07-27 | out-of-scope | Backfilled from unmerged `claude/daily-2026-07-26-log` branch (not yet merged) |
| https://www.anthropic.com/research/project-pilot | 2026-07-27 | out-of-scope | Backfilled from unmerged `claude/daily-2026-07-26-log` branch (not yet merged) |
| https://platform.claude.com/docs/en/release-notes/overview#managed-agents-session-ergonomics-2026-07-22 | 2026-07-27 | out-of-scope | Backfilled from unmerged `claude/daily-2026-07-26-log` branch (not yet merged) |
