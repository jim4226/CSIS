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
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-05 | out-of-scope | CJS framework already actioned twice (PR #83, PR #85 — unmerged duplicates); did not open a third. See 2026-07-05 log for the duplicate-work incident write-up. |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-05 | out-of-scope | Model version bookkeeping, not load-bearing for any of the seven themes. Prior runs reached inconsistent conclusions on this URL (07-01 vs 07-02 logs) — symptom of the broken ledger, not re-resolved here. |
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-05 | out-of-scope | Product availability/policy news, distinct from the CJS technical content. |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-05 | deferred | Still deferred per 07-02 design sketch (provenance-tracked reviewer-agent → ROADMAP P1.8); no new info today. |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-05 | out-of-scope | Usage-pattern economics research; no theme mapping. |
| https://code.claude.com/docs/en/changelog | 2026-07-05 | out-of-scope | v2.1.197-201 (Jun 30-Jul 3): background-agent CLI features and reliability fixes, no CSIS-consumable API/SDK primitive. v2.1.199 fix already actioned as PR #87 (07-03). |
| (operational) | 2026-07-05 | flagged | ~30 `claude/daily-*` PRs open unmerged since 2026-06-15; index.md on `main` never accumulates. First flagged 2026-06-30 (PR #82), reconfirmed every run since; today it caused a real duplicate-PR incident (see above). Recommend maintainer merge/close pass, log-only PRs first. |
