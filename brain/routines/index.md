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
| https://platform.claude.com/docs/en/release-notes/overview#admin-api-user-management | 2026-07-14 | out-of-scope | Claude Enterprise Admin API user/group/role management (beta); console/org-admin feature, no CSIS touchpoint. |
| https://www.anthropic.com/news (Introducing Claude for Teachers) | 2026-07-14 | out-of-scope | Consumer/education product launch, no technical content. |
| https://www.anthropic.com/news ($10M Canadian AI research commitment) | 2026-07-14 | out-of-scope | Philanthropic/funding announcement, no technical content. |
| https://www.anthropic.com/research (How Canada uses Claude — Economic Index) | 2026-07-14 | out-of-scope | Macro usage-pattern report; descriptive, no technique or primitive CSIS could consume. |
| https://www.anthropic.com/research/claude-plays-robotics | 2026-07-09 | out-of-scope | Frontier Red Team robotics-capability eval; domain-specific report, no generalizable eval methodology or API surface for CSIS's grader stack. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (v2.1.205-2.1.209) | 2026-07-14 | out-of-scope | Claude Code CLI product/UX fixes (auto mode expansion, screen-reader mode, plugin-hook shell-injection fix); not an API/architecture primitive `csis/*` consumes. |
| (operational) | 2026-07-14 | flagged | PR backlog now 94 open / 95 total (only #7 ever merged), unmerged since 2026-05-23. No new duplicates introduced today (0 code PRs opened). tripwire-severity-score (#83/#85) and Alberta/J-space status conflicts (see 2026-07-13.md) remain unresolved. Full detail + repeated recommendation in 2026-07-14.md. |
