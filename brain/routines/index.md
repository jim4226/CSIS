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
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-19 | deferred | GRAM per-category knowledge compartments; design sketch to extend `TierGuard` with a per-domain-adapter ceiling axis. See `brain/routines/2026-07-19.md`. |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-19 | out-of-scope | Values-expression measurement study on deployed consumer product; no CSIS primitive. |
| https://www.anthropic.com/research/claude-plays-robotics | 2026-07-19 | out-of-scope | Frontier Red Team capability benchmark (Project Fetch phase 2), not a primitive. |
| https://www.anthropic.com/news/claude-for-teachers | 2026-07-19 | out-of-scope | Consumer/education product launch. |
| https://www.anthropic.com/news/canadian-ai-research | 2026-07-19 | out-of-scope | Funding/grants announcement. |
| https://www.anthropic.com/news/ust-claude | 2026-07-19 | out-of-scope | Partner case study, no new primitive. |
| https://www.anthropic.com/news/hard-questions | 2026-07-19 | out-of-scope | Brand/marketing campaign. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-19 | out-of-scope | Governance/personnel announcement. |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-19 | out-of-scope | Consumer usage-history dashboard, not an agent memory primitive. |
| https://www.anthropic.com/research/how-canada-uses-claude | 2026-07-19 | out-of-scope | Economic-impact research, no engineering primitive. |
