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
| https://platform.claude.com/docs/en/build-with-claude/effort | 2026-07-22 | opened-PR | `effort_map` on `AnthropicBackend`, PR #112. See `brain/routines/2026-07-22.md`. |
| https://platform.claude.com/docs/en/managed-agents/webhooks#supported-event-types | 2026-07-22 | deferred | `memory_store.*`/`environment.*` lifecycle events → promote() callback sketch. |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-22 | deferred | Four-axis value measurement as a future distributional-grader dimension; needs a design doc first. |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-22 | out-of-scope | Economic-policy grant program. |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-22 | out-of-scope | Consumer connector for a public dataset. |
| https://www.anthropic.com/news/donation-public-first-action | 2026-07-22 | out-of-scope | Philanthropy. |
| https://www.anthropic.com/news/rare-disease-research-grants | 2026-07-22 | out-of-scope | Grant program. |
| https://www.anthropic.com/news/claude-for-teachers | 2026-07-22 | out-of-scope | Consumer/education product. |
| https://www.anthropic.com/news/canadian-ai-research | 2026-07-22 | out-of-scope | Philanthropy/policy. |
| https://www.anthropic.com/research/how-canada-uses-claude | 2026-07-22 | out-of-scope | Economic-usage research, not agent architecture. |
| https://platform.claude.com/docs/en/release-notes/overview#workbench-sunset-2026-07-17 | 2026-07-22 | out-of-scope | Console feature deprecation CSIS doesn't use. |
| https://platform.claude.com/docs/en/managed-agents/sessions#seed-the-session-with-initial-events | 2026-07-22 | out-of-scope | Session-bootstrap convenience on an API surface CSIS doesn't call through. |
| https://platform.claude.com/docs/en/managed-agents/events-and-streaming#event-deltas | 2026-07-22 | out-of-scope | Live subagent-thread preview; different surface from CSIS's own event-log tail. |
| https://platform.claude.com/docs/en/managed-agents/agent-setup#update-semantics | 2026-07-22 | out-of-scope | Same CAS pattern CSIS's `promote()` already implements; validation, not new work. |
| https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages | 2026-07-22 | out-of-scope | Availability correction for an existing capability. |
| https://platform.claude.com/docs/en/api/admin | 2026-07-22 | out-of-scope | Enterprise org administration. |
