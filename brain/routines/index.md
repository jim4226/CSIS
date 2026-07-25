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
| https://platform.claude.com/docs/en/release-notes/overview (2026-07-24 entry: mid-conversation tool changes) | 2026-07-25 | deferred | Beta tool-swap-mid-conversation API; CSIS has no tool-calling plumbing yet — see 2026-07-25.md design sketch. |
| https://platform.claude.com/docs/en/release-notes/overview (2026-07-24 entry: Opus 5 launch) | 2026-07-25 | out-of-scope | New model release; no CSIS theme. |
| https://platform.claude.com/docs/en/release-notes/overview (2026-07-22 entries: Managed Agents effort/webhooks/initial_events/version/event-deltas) | 2026-07-25 | out-of-scope | Managed Agents product surface; CSIS doesn't consume it. |
| https://platform.claude.com/docs/en/release-notes/overview (2026-07-17 entries: Workbench sunset, prompt-tools retirement) | 2026-07-25 | out-of-scope | Console deprecation notices; no CSIS theme. |
| https://www.anthropic.com/research/project-pilot | 2026-07-25 | out-of-scope | Drone-Bench physical robotics benchmark, not automated AI red-teaming. |
| Claude Code CLI CHANGELOG.md (subagent depth 3, sandbox.network.strictAllowlist, workflow size config) | 2026-07-25 | out-of-scope | Claude Code CLI features; CSIS's agent loop is custom Python, no consuming call site. |
| anthropic.com/news items 2026-07-09 through 2026-07-24 (donations, Teachers, grants, physical-AI partnership, hard-questions, Bernanke) | 2026-07-25 | out-of-scope | Corporate/product announcements, no theme mapping. |
