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
| https://www.anthropic.com/news/hard-questions | 2026-07-09 | out-of-scope | Public stakeholder-engagement initiative; governance/transparency, no theme mapping. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-09 | out-of-scope | Long-Term Benefit Trust board appointment; governance news, no theme mapping. |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-09 | out-of-scope | Consumer usage-analytics dashboard; checked against theme 4 (persistent memory), doesn't hold up — retrospective metadata, not a memory/context primitive. |
| https://code.claude.com/docs/en/changelog (v2.1.198) | 2026-07-09 | out-of-scope | CLI-internal (subagents background-by-default, auto-PR on completion); no API/SDK primitive CSIS's Coordinator/backends consume. Same reasoning as the 07-07 run applied to v2.1.202 (see PR #93's branch copy of this ledger). |
| https://code.claude.com/docs/en/changelog (v2.1.203) | 2026-07-09 | out-of-scope | CLI-internal session/auth plumbing (login-expiry warning, MCP roots/list, daemon token fix); no consumable primitive. |
| https://code.claude.com/docs/en/changelog (v2.1.205) | 2026-07-09 | out-of-scope | Auto-mode transcript-tamper-blocking rule looked like theme 2, but CSIS's event log already has independent tested tamper-evidence (`EventLog.verify_chain`, `test_event_log_detects_tampering`) — no gap to close. |
| (operational) | 2026-07-09 | flagged | Backlog unresolved: **89 total PRs (#6-#94) per a full `list_pull_requests` scan today, 88 open, 1 merged** (only the routine's own registration PR, #7). No merges landed since PR #94's 2026-07-08 run. Same recommendation stands (log-only PRs first, then the #83/#85 duplicate, then #81, then remaining code PRs oldest-first). See `brain/routines/2026-07-09.md` and, for full prior context, PR #94 / branch `claude/daily-2026-07-07-log`. |
| (note) | 2026-07-09 | — | Like every run since 07-08, `main`'s copy of this ledger still predates every `claude/daily-*` PR (none have merged), so it only carries the rows this run and PR #94 added — not the full reconstructed ledger, which lives on `claude/daily-2026-07-07-log` (PR #93) and PR #94's diff. See the operational note above. |
