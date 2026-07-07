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
| https://www.anthropic.com/features/making-of-claude-code | 2026-07-07 | out-of-scope | Content not fetchable (interactive terminal-style page, WebFetch returned only a header/placeholder). Not guessing at theme mapping from the title alone. |
| https://code.claude.com/docs/en/changelog (v2.1.202) | 2026-07-07 | out-of-scope | CLI-internal plumbing (dynamic-workflow-size setting, workflow OTel attributes, assorted bug fixes); no API/SDK primitive CSIS's Coordinator can consume. |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-07 | out-of-scope | Reconfirmed. Note: PR #81 (2026-06-30) already opened a `beta`-checkpoint bump for this URL as `opened-PR`; later runs (07-05, 07-06, and now 07-07) independently re-triaged it `out-of-scope`. Ledger-fragmentation drift — see 2026-07-07 log's operational note. If #81 merges, correct this row to `opened-PR`. |
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-07 | out-of-scope | Reconfirmed — already actioned twice as unmerged duplicates (PR #83, PR #85). |
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-07 | out-of-scope | Reconfirmed — product availability/policy news. |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-07 | deferred | Reconfirmed — still deferred per 07-02 design sketch (ROADMAP P1.8); no new info. |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-07 | out-of-scope | Reconfirmed — usage-pattern economics, no theme mapping. |
| https://www.anthropic.com/research/global-workspace | 2026-07-07 | out-of-scope | Reconfirmed — interpretability finding requires weight/activation access; no viable API-only technique. |
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-07 | opened-PR | Reconfirmed — already PR #91 (2026-07-06). |
| (operational) | 2026-07-07 | flagged | `claude/daily-*` PR backlog now 40+ (PR #52–#92), unmerged since 2026-06-15. Two concrete duplicate/drift incidents to date (tripwire severity scoring in #83+#85; Sonnet-5 bump in #81 vs. later out-of-scope re-triage). First flagged 2026-06-30 (PR #82), reconfirmed and escalating every run since. Recommend maintainer merge/close pass, log-only PRs first. |
