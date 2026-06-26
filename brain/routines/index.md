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
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-06-26 | out-of-scope | Economic/observational — usage cadence patterns (hourly, daily, seasonal rhythms); no CSIS theme mapping |
| https://code.claude.com/docs/en/changelog | 2026-06-26 | reconsidered-skipped | Parent URL first seen 2026-06-22 (opened-PR #69/#67); new versions v2.1.187-v2.1.193 reconsidered-skipped per dedup rule; flag in 2026-06-26.md for human review of v2.1.187 credential-file-tripwire opportunity |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-26 | deferred | Physical robotics frontier research; weak Theme 7 mapping; reconsidered 3× (Jun 18, Jun 25, Jun 26) — judgment unchanged each time |
