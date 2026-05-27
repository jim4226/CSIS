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
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-27 | opened-PR | PR #18 — Constitution.reminder() (theme 3) |
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-27 | deferred | multi-agent scanning pattern → researcher.py / security_audit domain |
| https://www.anthropic.com/news/anthropic-acquires-stainless | 2026-05-27 | deferred | Stainless MCP manifest → substrate/capability.py (speculative) |
| https://www.anthropic.com/news/kiyoung-choi-representative-director-anthropic-korea | 2026-05-27 | out-of-scope | corporate/HR announcement |
| https://www.anthropic.com/news/chris-olah-pope-leo-encyclical | 2026-05-27 | out-of-scope | societal commentary, no CSIS theme |
| https://www.anthropic.com/news/anthropic-kpmg | 2026-05-27 | out-of-scope | business partnership, consumer Claude.ai |
| https://www.anthropic.com/research/coding-agents-social-sciences | 2026-05-27 | out-of-scope | sociological survey, no technical CSIS mapping |
