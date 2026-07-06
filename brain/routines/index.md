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
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-06 | opened-PR | PR #91 — red-team/blue-team curiosity seed added to `pr_maintenance` domain. |
| https://www.anthropic.com/research/global-workspace | 2026-07-06 | out-of-scope | Interpretability finding requires weight/activation access; no viable API-only technique for CSIS's `AnthropicBackend`. |
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-06 | out-of-scope | Reconfirmed — already actioned twice as unmerged duplicates (PR #83, PR #85). See 2026-07-06 log. |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-06 | out-of-scope | Reconfirmed — model version bookkeeping, not load-bearing for any theme. |
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-06 | out-of-scope | Reconfirmed — product availability/policy news. |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-06 | deferred | Reconfirmed — still deferred per 07-02 design sketch (ROADMAP P1.8); no new info. |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-06 | out-of-scope | Reconfirmed — usage-pattern economics, no theme mapping. |
| (operational) | 2026-07-06 | flagged | `claude/daily-*` PR backlog (30+, unmerged since 2026-06-15) still unaddressed; index.md on `main` still never accumulates. First flagged 2026-06-30 (PR #82), reconfirmed every run since including today. Recommend maintainer merge/close pass, log-only PRs first. |
