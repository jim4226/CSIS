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
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-08-01 | opened-PR | PR #126 — `sim_rationalization` tripwire pattern |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-08-01 | deferred | design sketch: `validation_chain` field on frontier items, see 2026-08-01.md |
| https://platform.claude.com/docs/en/release-notes/overview | 2026-08-01 | deferred | `agent-memory-2026-07-22` header — no live memory-store integration to touch yet; forward-compat note, see 2026-08-01.md |
| https://www.anthropic.com/news/claude-opus-5 | 2026-08-01 | out-of-scope | product/model release, no theme |
| https://www.anthropic.com/news/position-open-weights-models | 2026-08-01 | out-of-scope | policy statement, no theme |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-08-01 | out-of-scope | business partnership, no theme |
| https://www.anthropic.com/research/project-pilot | 2026-08-01 | out-of-scope | physical-world robotics eval, doesn't map to CSIS software substrate |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2-1-219-sandbox-strictallowlist | 2026-08-01 | out-of-scope | Claude Code CLI sandbox setting, not a primitive CSIS consumes |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2-1-219-nested-subagent-depth | 2026-08-01 | out-of-scope | Claude Code CLI subagent-spawn-depth feature, CSIS has its own coordinator, not via Claude Code subagents |
