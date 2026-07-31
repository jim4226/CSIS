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
| https://code.claude.com/docs/en/routines | 2026-07-31 | opened-PR | v2.1.214 prompt-provenance framing → new `false_authorization_claim` tripwire pattern. |
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-07-31 | deferred | Real sandbox-escape incidents; motivates P1.2/P1.7 process isolation, not a Phase-0 patch. |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-07-31 | deferred | Hypothesis-driven multi-agent research loop; candidate feedback signal for `csis/curiosity.py` scoring. |
| https://www.anthropic.com/news/claude-opus-5 | 2026-07-31 | out-of-scope | Model version launch; doesn't map to a CSIS architecture theme. |
| https://www.anthropic.com/news/position-open-weights-models | 2026-07-31 | out-of-scope | Policy position, not an architectural change CSIS consumes. |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-07-31 | out-of-scope | Enterprise partnership announcement. |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-31 | out-of-scope | Economic research funding agenda, no architectural theme. |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-31 | out-of-scope | Consumer Claude.ai connector feature. |
| https://www.anthropic.com/research/project-pilot | 2026-07-31 | out-of-scope | Drone-control frontier red-team study; no multi-agent/trust/curiosity theme fit beyond generic capability eval. |
| https://www.anthropic.com/research/how-canada-uses-claude | 2026-07-31 | out-of-scope | Economic Index regional usage study, outside the 9-day window and no theme fit. |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-31 | out-of-scope | Societal-impacts study, outside the 9-day window and no theme fit. |
