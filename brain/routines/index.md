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
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-23 | opened-PR | PR #8 glasswing-frontier-ranking |
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-24 | opened-PR | PR #10 value-reminder-tripwire (also PR #18 constitution-reminder-tool) |
| https://code.claude.com/docs/en/changelog | 2026-05-25 | opened-PR | PR #12 event-span-agent-ids, PR #13 critic-effort-levels |
| https://www.anthropic.com/engineering/how-we-contain-claude | 2026-05-26 | opened-PR | PR #15 external-content-layer |
| https://code.claude.com/docs/en/agent-sdk/overview | 2026-05-26 | opened-PR | PR #16 domain-system-prompt |
| https://www.anthropic.com/news/claude-opus-4-8 | 2026-05-28 | opened-PR | PR #20 opus-4-8-effort |
| https://www.anthropic.com/research/coding-agents-social-sciences | 2026-05-28 | out-of-scope | Behavioral adoption study, no technical CSIS-theme content |
