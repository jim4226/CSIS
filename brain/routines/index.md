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
| https://code.claude.com/docs/en/changelog | 2026-06-20 | opened-PR | v2.1.183 auto-mode destructive-command blocking → irreversible_state_mutation tripwire (PR #67) |
| https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem | 2026-06-20 | out-of-scope | Business/partnership announcement |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-20 | out-of-scope | Policy document; adjacent concerns covered by PR #49 and PR #57 |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-20 | out-of-scope | Public opinion survey; no technical content |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-20 | out-of-scope | Business announcement |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-20 | out-of-scope | Business announcement |
| https://www.anthropic.com/news/claude-corps | 2026-06-20 | out-of-scope | Workforce development program; no technical content |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-20 | out-of-scope | Robotics/physical agent control; no CSIS module covers this |
| https://www.anthropic.com/research/claude-code-expertise | 2026-06-20 | out-of-scope | Economic study of human-AI collaboration; no CSIS code change implied |
| https://www.anthropic.com/engineering/multi-agent-research-system | 2026-06-20 | out-of-scope | Published Jun 2025; outside 9-day window |
