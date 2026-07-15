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
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-15 | deferred | Theme 3; design sketch for a value-drift probe in `csis/safety/`. |
| https://www.anthropic.com/news/claude-for-teachers | 2026-07-15 | out-of-scope | Consumer/education product, no primitive. |
| https://www.anthropic.com/news/canadian-ai-research | 2026-07-15 | out-of-scope | Funding announcement. |
| https://www.anthropic.com/news/ust-claude | 2026-07-15 | out-of-scope | Robotics partnership announcement. |
| https://www.anthropic.com/news/hard-questions | 2026-07-15 | out-of-scope | Public-communications initiative. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-15 | out-of-scope | Governance/board news. |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-15 | out-of-scope | Consumer claude.ai UI feature. |
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-15 | out-of-scope | Customer case study. |
| https://www.anthropic.com/research/how-canada-uses-claude | 2026-07-15 | out-of-scope | Economic-impact research. |
| https://www.anthropic.com/research/claude-plays-robotics | 2026-07-15 | out-of-scope | Embodiment/robotics research. |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-15 | out-of-scope | Training-time weight compartmentalization (GRAM); below CSIS's inference-time capability-tier layer. |
| https://www.anthropic.com/research/global-workspace | 2026-07-15 | out-of-scope | Model-internal interpretability finding; no external API primitive to consume. |
| https://platform.claude.com/docs/en/release-notes/api#july-14-2026 | 2026-07-15 | out-of-scope | Admin API org/member management; unrelated to agent primitives. |
| https://platform.claude.com/docs/en/release-notes/api#july-10-2026-dreams | 2026-07-15 | out-of-scope | Dreams model-support expansion; already tracked under ROADMAP P1.1, access still gated. |
| https://platform.claude.com/docs/en/release-notes/api#july-10-2026-access-transparency | 2026-07-15 | out-of-scope | Access Transparency `cmek_preserve` doc expansion; enterprise compliance, unrelated to CSIS's event log. |
| https://platform.claude.com/docs/en/release-notes/api#july-8-2026 | 2026-07-15 | out-of-scope | API key expiration, console/account feature. |
