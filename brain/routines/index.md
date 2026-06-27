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
| https://code.claude.com/docs/en/workflows.md | 2026-06-27 | opened-PR | PR #76: multi_critic_vote() adversarial-verify pattern; Theme 2 |
| https://www.anthropic.com/news/introducing-claude-tag | 2026-06-27 | out-of-scope | Consumer Slack product; no CSIS code path |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-27 | out-of-scope | Robotics experiment; physical substrate, not CSIS |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-06-27 | out-of-scope | Economic usage analysis; no CSIS theme |
