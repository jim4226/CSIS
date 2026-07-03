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
| https://code.claude.com/docs/en/changelog | 2026-07-03 | opened-PR | v2.1.199 (Jul 2) subagent partial-output/error-reporting fixes → PR #87, `csis/agents/builder.py` stop_reason handling. Other bullets in this changelog are Claude Code CLI features, out-of-scope for CSIS's Python harness. |
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-03 | deferred | Cyber Jailbreak Severity four-axis rubric → design sketch for `csis/safety/tripwires.py` severity scoring. Deferred: changes real halt semantics, needs its own critique cycle. |
| https://platform.claude.com/docs/en/release-notes/overview | 2026-07-03 | deferred | Jun 30 Managed Agents webhooks + `agent_with_overrides` → design sketch, P1.1-adjacent. Other bullets (Sonnet 5 pricing, fast-mode deprecations, rate-limit tier consolidation) out-of-scope. |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-03 | out-of-scope | Model release/pricing announcement; no CSIS theme. |
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-03 | out-of-scope | Product policy/availability news; not a mechanism CSIS consumes. |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-03 | out-of-scope | Vertical consumer/researcher product. |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-03 | out-of-scope | Usage-pattern economics research; no theme match. |
