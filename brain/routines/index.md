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
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-24 | opened-PR | PR #10 — ValueReminderTool in csis/safety/value_reminder.py |
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-24 | deferred | Multi-agent scanning harness for Auditor; design sketch in 2026-05-24.md |
| https://www.anthropic.com/news/anthropic-acquires-stainless | 2026-05-24 | deferred | MCP server stubs for agent roles; blocked on post-acquisition Stainless tooling |
| https://www.anthropic.com/news/anthropic-kpmg | 2026-05-24 | out-of-scope | Enterprise partnership, no CSIS-relevant technical content |
| https://www.anthropic.com/news/pwc-expanded-partnership | 2026-05-24 | out-of-scope | Enterprise partnership, outside 9-day window, no CSIS-relevant technical content |
