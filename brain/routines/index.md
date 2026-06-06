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
| https://code.claude.com/docs/en/changelog | 2026-06-06 | opened-PR | v2.1.163 version gate → PR #35; v2.1.166 fallback model → PR #36; v2.1.166 thinking-disable → PR #37; v2.1.162 waitingFor → deferred |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-06 | out-of-scope | NMR spectroscopy benchmark; no CSIS theme match (confirmed from 2026-06-05 log). |
