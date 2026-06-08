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
| https://www.anthropic.com/research/agents-in-biology | 2026-06-08 | opened-PR | PR #42 (grader-provenance-layer) |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-08 | out-of-scope | Capability benchmark, no CSIS theme match |
| https://www.anthropic.com/news/expanding-project-glasswing | 2026-06-08 | out-of-scope | Security access program, no CSIS architecture content |
| https://www.anthropic.com/news/services-track-partner-hub | 2026-06-08 | out-of-scope | Partner program announcement |
| https://www.anthropic.com/news/confidential-draft-s1-sec | 2026-06-08 | out-of-scope | Financial event |
| https://www.anthropic.com/news/AI-enabled-cyber-threats-mitre-attack | 2026-06-08 | reconsidered-skipped | Already covered by PR #31 (agentic-chain-tripwire, 2026-06-03) |
