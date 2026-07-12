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
| https://www.anthropic.com/research/global-workspace | 2026-07-12 | deferred | J-space interpretability paper; design sketch in 2026-07-12.md re: future V3/V5 verification layers. No API surface to consume yet. |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-12 | out-of-scope | GRAM training-time technique; CSIS never trains/fine-tunes models. |
| https://www.anthropic.com/news/ust-claude | 2026-07-12 | out-of-scope | Customer/partnership story (robotics). |
| https://www.anthropic.com/news/hard-questions | 2026-07-12 | out-of-scope | Public-communications initiative. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-12 | out-of-scope | Governance/board news. |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-12 | out-of-scope | Consumer claude.ai usage-analytics dashboard. |
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-12 | out-of-scope | Customer case study. |
| https://www.anthropic.com/features/making-of-claude-code | 2026-07-12 | out-of-scope | Narrative/behind-the-scenes piece, no technical architecture content. |
| https://platform.claude.com/docs/en/release-notes/api#july-10-2026 | 2026-07-12 | out-of-scope | Access Transparency / cmek_preserve docs expansion — Console compliance feature. |
| https://platform.claude.com/docs/en/release-notes/api#july-8-2026 | 2026-07-12 | out-of-scope | API key expiration settings — Console key-management feature. |
