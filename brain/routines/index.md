# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-11 | opened-PR | PR #49: distillation_attempt tripwire + fable5 model alias |
| https://www.anthropic.com/research/agents-in-biology | 2026-06-11 | deferred | DataSourceTag / deterministic-source grader pattern |
| https://platform.claude.com/docs/en/api/getting-started | 2026-06-11 | deferred | Claude Managed Agents APIs (Sessions/Agents/Environments); touches Coordinator.__init__ chokepoint |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-11 | out-of-scope | NMR chemistry domain; no CSIS module mapping |
| https://www.anthropic.com/news/AI-enabled-cyber-threats-mitre-attack | 2026-06-11 | out-of-scope | Policy/threat-intel piece; no concrete code signal |
