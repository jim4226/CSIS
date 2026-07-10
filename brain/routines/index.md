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
| https://www.anthropic.com/news/ust-claude | 2026-07-10 | out-of-scope | Customer case study (robotics/physical-AI partner story); no theme mapping. |
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-10 | out-of-scope | CJS severity framework — same idea PR #83/#85 already implement (duplicated) from the 06-30 Fable-5 announcement; a third implementation was drafted then reverted rather than shipped. See 2026-07-10 log. |
| https://www.anthropic.com/features/making-of-claude-code | 2026-07-10 | inconclusive | WebFetch returned obfuscated page content, no article text; re-check next run before triaging. |
| (operational) | 2026-07-10 | flagged | Backlog unresolved, day 4 of escalation: **89 open PRs (#6-#95)** per a full `list_pull_requests` scan, oldest 2026-05-20 (PR #6). Zero merges since PR #7. A third near-duplicate (fuzzer.py severity scoring, mirroring #83/#85) was caught and reverted before opening. Same recommendation stands (log-only PRs first, then #83/#85, then #81, then remaining code PRs oldest-first). See `brain/routines/2026-07-10.md` and PR #94/#95 for full history. |
| (note) | 2026-07-10 | — | `main`'s copy of this ledger still predates every `claude/daily-*` PR (none have merged) — this run's rows are appended on top of what PR #95 carried forward, not a full reconciliation. See the operational note above. |
