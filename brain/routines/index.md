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
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-13 | opened-PR | PR #55: update alpha checkpoint to claude-opus-4-8 (Theme 6) |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-13 | opened-PR | Triaged jointly with Fable 5 launch; both informed PR #55 |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-13 | out-of-scope | Social science survey, no technical content |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-13 | out-of-scope | Business partnership |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-13 | out-of-scope | Business integration announcement |
| https://www.anthropic.com/news/claude-corps | 2026-06-13 | out-of-scope | Human fellowship program, no agent architecture |
| https://www.anthropic.com/research/agents-in-biology | 2026-06-13 | out-of-scope | Biology domain tooling; not a CSIS architectural theme |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-13 | out-of-scope | Chemistry domain-specific; pre-triaged by title analogy |
| https://www.anthropic.com/news/AI-enabled-cyber-threats-mitre-attack | 2026-06-13 | out-of-scope | External threat-intel survey; Theme 7 applies to CSIS's own loop, not external surveys |
| https://www.anthropic.com/news/services-track-partner-hub | 2026-06-13 | out-of-scope | Business program |
| https://www.anthropic.com/engineering/multi-agent-research-system | 2026-06-13 | out-of-scope | Outside 9-day window (dated 2025-06-13); relevant content noted in log design sketch |
