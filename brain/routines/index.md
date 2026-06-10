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
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-10 | opened-PR | PR #46 (tripwire-disposition) — reconsidered from 2026-06-09 deferred sketch; PR #44 covered distillation guard on 2026-06-09 |
| https://www.anthropic.com/research/agents-in-biology | 2026-06-10 | opened-PR | PR #42 (grader-provenance-layer) opened 2026-06-08 |
| https://www.anthropic.com/news/AI-enabled-cyber-threats-mitre-attack | 2026-06-10 | opened-PR | PR #31 (agentic-chain-tripwire) opened 2026-06-03 |
| https://www.anthropic.com/news/expanding-project-glasswing | 2026-06-10 | out-of-scope | Policy/access program; CSIS tier enforcement already implemented |
| https://www.anthropic.com/news/services-track-partner-hub | 2026-06-10 | out-of-scope | Business/partner program; no CSIS theme match |
| https://www.anthropic.com/news/confidential-draft-s1-sec | 2026-06-10 | out-of-scope | Financial/SEC filing; no CSIS theme match |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-10 | out-of-scope | Chemistry NMR benchmark; no CSIS theme match (confirmed by 2026-06-05 run) |
