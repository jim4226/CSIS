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
| https://platform.claude.com/docs/en/release-notes/overview#dreams-fable-5-sonnet-5 | 2026-07-13 | deferred | Dreams (research preview) now supports Claude Fable 5 + Sonnet 5; design sketch in 2026-07-13.md ties directly to ROADMAP.md P1.1 (real Dreams API integration). Needs Managed Agents gated access + a memory-store translation layer — large/medium risk, not same-day. |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-13 | out-of-scope | Values/behavior measurement study across models and languages; descriptive research on Anthropic's own consumer traffic, no API primitive or technique CSIS's V1/V2 stack can consume. |
| (operational) | 2026-07-13 | flagged | PR backlog now 93 open / 94 total (only #7 ever merged), unmerged since 2026-06-23. Two NEW drift incidents found on top of the known #83/#85 duplicate: (1) Alberta case study correctly opened as PR #91 (confirmed real diff) on 07-06/07-07, then wrongly re-triaged out-of-scope by both the 07-11 and 07-12 runs, which had no ledger to check against; (2) J-space paper (global-workspace) went out-of-scope on 07-06/07-07/07-11 then flipped to deferred on 07-12. Full reconstruction + notification sent to operator in 2026-07-13.md. Recommend merge/close pass, log-only PRs first, per every prior run's note since 2026-06-30. |
