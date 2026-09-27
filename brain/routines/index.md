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
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-06-30 | opened-PR | PR #81 — bumped `beta` checkpoint to claude-sonnet-5 in `csis/backends/anthropic.py`. |
| https://platform.claude.com/docs/en/release-notes/overview#june-30-2026-managed-agents | 2026-06-30 | deferred | Managed Agents event deltas/pagination/session overrides/vault injection_location/webhooks — CSIS doesn't call the Managed Agents API today; needs a Phase-1 design doc before any code change. |
| https://www.anthropic.com/news/introducing-claude-tag | 2026-06-30 | out-of-scope | Slack team product; no API/SDK primitive to consume. |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-06-30 | out-of-scope | Consumer research-workbench product; no API primitive to consume. |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-06-30 | out-of-scope | Usage-pattern research; confirmed no multi-agent/self-improvement content. |
| https://platform.claude.com/docs/en/release-notes/overview#june-22-2026-mcp-tunnels | 2026-06-30 | out-of-scope | MCP tunnels admin-API relocation; CSIS has no MCP usage in the codebase. |
