# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-23 | opened-PR | PR #8 glasswing-frontier-ranking (Theme 7) — backfilled from PR description |
| https://www.anthropic.com/news/anthropic-acquires-stainless | 2026-05-23 | deferred | MCP server generation; no stable post-acquisition API surface yet; reconsidered 2026-05-26, still deferred |
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-24 | opened-PR | PR #10 value-reminder-tripwire (Theme 3) — backfilled from PR description |
| https://www.anthropic.com/news/anthropic-kpmg | 2026-05-24 | out-of-scope | Enterprise partnership announcement — backfilled from log PR #11 |
| https://code.claude.com/docs/en/changelog | 2026-05-25 | opened-PR | PR #12 event-span-agent-ids (v2.1.145) + PR #13 critic-effort-levels (v2.1.147) — backfilled from PR descriptions |
| https://www.anthropic.com/news/chris-olah-pope-leo-encyclical | 2026-05-25 | out-of-scope | Alignment/ethics commentary, not an architectural primitive — backfilled from log PR #14 |
| https://www.anthropic.com/engineering/how-we-contain-claude | 2026-05-26 | opened-PR | PR #15 external-content-layer (Theme 3+6) |
| https://code.claude.com/docs/en/agent-sdk/overview | 2026-05-26 | opened-PR | PR #16 domain-system-prompt (Theme 1+6) |
| https://platform.claude.com/docs/en/managed-agents/overview | 2026-05-26 | deferred | Dreams API in research preview; awaiting operator access confirmation (P1.1) |
