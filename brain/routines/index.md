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
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md | 2026-07-21 | out-of-scope | v2.1.211–v2.1.217 (Jul 15–21) — CLI/harness plumbing (EndConversation tool, filesystem isolation setting, permission/OAuth/worktree fixes); no attachment point since CSIS calls the Anthropic API directly, not the Claude Code CLI. |
| (operational) | 2026-07-21 | flagged | `claude/daily-*` PR backlog now **104 open / 105 total**, only PR #7 ever merged (2026-05-23), oldest unmerged branch from 2026-05-20. Up from 101 on 2026-07-18. Unresolved since first flagged 2026-06-30 (PR #82); see `brain/routines/2026-07-21.md` for the full recommendation (merge log-only PRs first). |
| (note) | 2026-07-21 | — | `main`'s copy of this ledger predates every `claude/daily-*` PR (none have merged), so it does not carry forward the ~100+ rows already triaged across unmerged branches. This run's actual dedup was done against `claude/daily-2026-07-20-log` (PR #110)'s `index.md`/day file, not this file. Do not read this file's brevity as "little has been triaged" — see the operational note above and `brain/routines/2026-07-21.md`. |
