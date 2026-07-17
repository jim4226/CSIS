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
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-16 | opened-PR | PR #103. GRAM — cited as related work for P1.2 / capability-tier §9.1. |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-16 | opened-PR | PR #103. Cited as related work for P1.5 (V5 calibration) and a new §16 open question. |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-10 entry: Dreams supports Fable 5 / Sonnet 5) | 2026-07-16 | deferred | Design sketch in `brain/routines/2026-07-16.md`. Directly relevant to ROADMAP P1.1; needs its own dedicated effort + confirmed operator access, not a daily-routine drive-by. |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-16 | out-of-scope | Consumer claude.ai usage-analytics feature. |
| https://www.anthropic.com/research/claude-plays-robotics | 2026-07-16 | out-of-scope | Physical robotics, no CSIS theme mapping. |
| https://www.anthropic.com/news/ust-claude | 2026-07-16 | out-of-scope | Partnership/business announcement. |
| https://www.anthropic.com/news/hard-questions | 2026-07-16 | out-of-scope | Comms initiative. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-16 | out-of-scope | Governance/board news. |
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-16 | out-of-scope | Customer case study. |
| https://www.anthropic.com/news/claude-for-teachers | 2026-07-16 | out-of-scope | Consumer/education product launch. |
| https://www.anthropic.com/news/canadian-ai-research | 2026-07-16 | out-of-scope | Funding/business announcement. |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-14 entry: Admin API org member management) | 2026-07-16 | out-of-scope | Org-admin API surface, no CSIS consumer. |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-15 entry: mid-conversation system messages availability correction) | 2026-07-16 | out-of-scope | Corrects availability of a feature already covered by prior run (`mid-conv-system-blocks`, 2026-06-01). |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-08 entry: API key expiration) | 2026-07-16 | out-of-scope | Account/credential-management feature. |
| https://code.claude.com/docs/en/changelog (v2.1.200–v2.1.211, Jul 3–15) | 2026-07-16 | out-of-scope | Full changelog + Week 27/28 digests scanned; no crisp 1:1 CSIS parallel this week. |
