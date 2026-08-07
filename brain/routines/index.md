# CSIS routine index — URL ledger

This file is the merged, human-reviewed cross-run memory for `.claude/routines/daily-improvement.md`. URLs recorded by proposal-bearing runs appear here with the date of first sighting and the action taken. Open routine PRs are an additional live state layer and must be inspected before this ledger so unmerged proposals are not duplicated.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — legacy placeholder from the initial ledger; new quiet runs do not create repository artifacts

| URL | First seen | Status | Notes |
|---|---|---|---|
| (none) | (initial) | quiet-day-empty | Ledger initialized; first real entries land on the routine's first scheduled run. |
| https://platform.claude.com/docs/en/release-notes/overview#memory-store-webhooks-2026-07-22 | 2026-07-26 | opened-PR | PR #119 — P1.9 roadmap note on Managed Agents memory_store/environment webhooks |
| https://www.anthropic.com/news/claude-opus-5 | 2026-07-26 | deferred | Opus 5 launch surfaces stale checkpoint model strings in `csis/backends/anthropic.py` + `csis/budget.py`; design sketch in 2026-07-26.md |
| https://platform.claude.com/docs/en/release-notes/overview#mid-conversation-tool-changes-2026-07-24 | 2026-07-26 | deferred | Mid-conversation tool add/remove (beta) — design sketch for domain-adapter tool swapping in 2026-07-26.md |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-26 | out-of-scope | Philanthropic/economic-policy research priorities; no CSIS theme mapping |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-26 | out-of-scope | Consumer economic-index Q&A connector; not a CSIS-relevant technique |
| https://www.anthropic.com/news/donation-public-first-action | 2026-07-26 | out-of-scope | Philanthropy announcement; no CSIS theme mapping |
| https://www.anthropic.com/research/project-pilot | 2026-07-26 | out-of-scope | Frontier Red Team drone-control capability research; not a red-teaming methodology CSIS's curiosity engine could adopt |
| https://platform.claude.com/docs/en/release-notes/overview#managed-agents-session-ergonomics-2026-07-22 | 2026-07-26 | out-of-scope | Managed Agents session/API ergonomics (effort config, seeded events, optional version field, thread event deltas); CSIS doesn't call this API today and none map to a specific theme |
