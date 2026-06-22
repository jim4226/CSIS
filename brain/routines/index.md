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
| https://code.claude.com/docs/en/changelog | 2026-06-22 | opened-PR | v2.1.186 Agent(type) deny-rule gap → agent-role-tier-enforcement (PR #69); v2.1.183 also covered by PR #67 (June 20 run) |
| https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem | 2026-06-22 | out-of-scope | Business/partnership announcement; also in June 20 run (PR #68) |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-22 | out-of-scope | Robotics/physical agent research; no CSIS module covers this; also in June 20 run (PR #68) |
| https://www.anthropic.com/research/claude-code-expertise | 2026-06-22 | out-of-scope | Economic study of human-AI coding collaboration; no CSIS code change implied; also in June 20 run (PR #68) |
