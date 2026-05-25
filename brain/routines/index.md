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
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-23 | opened-PR | PR #8 glasswing-frontier-ranking (confirmed from PR history; log PR #9 not yet merged to main) |
| https://www.anthropic.com/news/anthropic-kpmg | 2026-05-23 | out-of-scope | Enterprise partnership announcement (confirmed from PR #9 description) |
| https://www.anthropic.com/news/pwc-expanded-partnership | 2026-05-23 | out-of-scope | Enterprise partnership announcement (confirmed from PR #9 description) |
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-24 | opened-PR | PR #10 value-reminder-tripwire (confirmed from PR history; log PR #11 not yet merged to main) |
| https://www.anthropic.com/news/anthropic-acquires-stainless | 2026-05-24 | deferred | Post-acquisition MCP server tooling not yet released; reconsidered 2026-05-25, still deferred |
| https://code.claude.com/docs/en/changelog | 2026-05-25 | opened-PR | v2.1.145→PR#12 (event span IDs); v2.1.147→PR#13 (critic effort levels); v2.1.149+v2.1.150 out-of-scope |
| https://www.anthropic.com/news/chris-olah-pope-leo-encyclical | 2026-05-25 | out-of-scope | Public statement / policy commentary; no CSIS theme |
