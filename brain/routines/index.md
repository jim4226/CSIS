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
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.214-2026-07-18-modified-timestamp | 2026-07-24 | opened-PR | `modified` timestamp on memory frontmatter → `deprecated_at` on `MemoryEntry`. PR #116. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.214-2026-07-18-endconversation | 2026-07-24 | deferred | `EndConversation` tool for abusive users → possible new tripwire category for hostile external input; needs threat-model note first. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.219-2026-07-24-nested-subagents | 2026-07-24 | deferred | Nested subagents to depth 3 → recursive-delegation design question for `Coordinator`; architecturally significant, needs its own design doc. |
| https://platform.claude.com/docs/en/release-notes/overview#2026-07-22-memory-store-webhooks | 2026-07-24 | deferred | Managed Agents `environment.*`/`memory_store.*` webhooks → only relevant if CSIS ever swaps its self-hosted EventLog for the real Managed Agents substrate (not on the roadmap yet). |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#sandbox-settings-2026-07-20-and-2026-07-24 | 2026-07-24 | deferred | `sandbox.filesystem.disabled` / `sandbox.network.strictAllowlist` → proof-point for ROADMAP.md P1.2's OS-subprocess-sandbox path; doc-only if pursued. |
| https://www.anthropic.com/news/claude-opus-5 | 2026-07-24 | out-of-scope | General model release; no unique theme linkage. |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-24 | out-of-scope | Economic research funding program. |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-24 | out-of-scope | Consumer connector product feature. |
| https://www.anthropic.com/news/donation-public-first-action | 2026-07-24 | out-of-scope | Philanthropic announcement. |
| https://www.anthropic.com/news/rare-disease-research-grants | 2026-07-24 | out-of-scope | Grants program announcement. |
| https://www.anthropic.com/research/project-pilot | 2026-07-24 | out-of-scope | Single-model drone-control capability benchmark, not multi-agent red-teaming or frontier-item generation (confirmed by full read). |
| https://platform.claude.com/docs/en/release-notes/overview#2026-07-17-workbench-sunset | 2026-07-24 | out-of-scope | Console Workbench + experimental prompt-tools API retirement. |
| https://platform.claude.com/docs/en/release-notes/overview#2026-07-15-mid-conversation-system-messages | 2026-07-24 | out-of-scope | Availability-note correction, not a new capability. |
| https://platform.claude.com/docs/en/release-notes/overview#2026-07-24-mid-conversation-tool-changes | 2026-07-24 | out-of-scope | Beta feature for long multi-turn tool-set changes; CSIS role calls are one-shot per iteration. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.218-2026-07-22 | 2026-07-24 | out-of-scope | `/code-review` as background subagent — internal CLI skill implementation detail. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.215-2026-07-19-and-v2.1.217-2026-07-21 | 2026-07-24 | out-of-scope | Skill auto-run change, emoji autocomplete, MCP tool-output-truncation memory leak fix — CLI UX/bug fixes. |
