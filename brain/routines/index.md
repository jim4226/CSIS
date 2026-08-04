# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

**2026-08-03 note (carried forward):** this file was reconstructed from the open PR list (GitHub MCP `list_pull_requests`), not from a prior day's branch, because the branch-to-branch reconstruction chain (each day copying only the *previous* day's log branch) had already silently dropped seven `opened-PR` entries from 2026-07-16 through 2026-07-26 — see `2026-08-03.md` for the full explanation. **None of these PRs are merged as of 2026-08-04 either** (`#100`–`#129` all still open); every run since has had to re-verify against the live PR list rather than trust this file, since nothing actually lands on `main` until a human merges the backlog.

| URL | First seen | Status | Notes |
|---|---|---|---|
| (none) | (initial) | quiet-day-empty | Ledger initialized; first real entries land on the routine's first scheduled run. |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-16 | opened-PR | PR #103 — GRAM safety-research citation (`CSIS-architecture.html` §9.1, §16, §17; `ROADMAP.md` P1.2/P1.5) |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-16 | opened-PR | PR #103 — values-drift citation as P1.5 (V5 calibration) related work |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-17 | opened-PR | PR #105 — `brain/research/03-gram-capability-gating.md` design note (re-seen; same source as PR #103, different angle) |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-10 entry: Dreams supports Fable 5 / Sonnet 5) | 2026-07-17 | opened-PR | PR #106 — `ROADMAP.md` P1.1 dated note |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-22 entry: effort parameter) | 2026-07-22 | opened-PR | PR #112 — `effort_map` threaded through `AnthropicBackend` |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-22 entry: Managed Agents webhooks, initial_events, event deltas) | 2026-07-23 | opened-PR | PR #114 — `brain/research/01-anthropic-sdk.md` API-surface refresh |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (v2.1.214: memory file `modified` timestamp) | 2026-07-24 | opened-PR | PR #116 — `MemoryEntry.deprecated_at` field + `deprecate_live()` stamp |
| https://platform.claude.com/docs/en/release-notes/api (2026-07-22 entry: memory_store/environment webhooks) | 2026-07-26 | opened-PR | PR #119 — `ROADMAP.md` P1.9 design note (re-seen; overlaps PR #114's source) |
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-07-30 | opened-PR | PR #123 — `ROADMAP.md` P1.7 motivating-evidence citation |
| https://code.claude.com/docs/en/routines | 2026-07-31 | opened-PR | PR #125 — `false_authorization_claim` tripwire pattern |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-08-01 | deferred | design sketch: `validation_chain` field on frontier items — see `2026-08-01.md` (branch `claude/kind-euler-9505c6`); no PR opened yet |
| https://platform.claude.com/docs/en/release-notes/api (agent-memory-2026-07-22 header) | 2026-08-01 | deferred | forward-compat note only, no live integration point yet — see `2026-08-01.md` |
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-08-01 | opened-PR | PR #126 — `sim_rationalization` tripwire pattern (re-seen; second, distinct angle on the same source as PR #123) |
| https://www.anthropic.com/news/claude-opus-5 | 2026-08-01 | out-of-scope | product/model release, no theme |
| https://www.anthropic.com/news/position-open-weights-models | 2026-08-01 | out-of-scope | policy statement, no theme |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-08-01 | out-of-scope | business partnership, no theme |
| https://www.anthropic.com/research/project-pilot | 2026-08-01 | out-of-scope | physical-world robotics eval, doesn't map to CSIS software substrate |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2-1-219-sandbox-strictallowlist | 2026-08-01 | out-of-scope | Claude Code CLI sandbox setting, not a primitive CSIS consumes |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2-1-219-nested-subagent-depth | 2026-08-01 | out-of-scope | Claude Code CLI subagent-spawn-depth feature, CSIS has its own coordinator, not via Claude Code subagents |
| https://platform.claude.com/docs/en/release-notes/api (2026-08-01 entry: Dreams supports Opus 5) | 2026-08-03 | out-of-scope | model-support bump only, no new capability or access change; P1.1 already tracks Dreams integration as blocked on operator access, not model support |
| https://www.anthropic.com/news/claude-opus-5 (2026-07-24 launch detail: effort ladder, mid-conversation tool changes, fallback defaults) | 2026-08-03 | out-of-scope | model launch; effort ladder already consumed via PR #112, no further action item |
| https://www.anthropic.com/news/position-open-weights-models | 2026-08-03 | out-of-scope | policy statement, no theme (re-seen) |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-08-03 | out-of-scope | business partnership, no theme (re-seen) |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-08-03 | deferred | reconsidered — no new information since 2026-08-01 triage; design sketch stands, not re-sketched today |
| https://www.anthropic.com/news/tino-cuellar | 2026-08-04 | out-of-scope | personnel/leadership announcement, no theme |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (v2.1.220-v2.1.222) | 2026-08-04 | out-of-scope | Claude Code CLI harness features (worktree isolation, SendMessage permission classifier, MCP/auth fixes); CSIS's coordinator is its own Python substrate, not Claude Code subagents — same reasoning as the v2.1.219 entries |
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-08-04 | opened-PR | re-seen, no new angle — fully covered by PR #123 and PR #126 |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-08-04 | deferred | reconsidered again — still no new information; refined the deferral reasoning to cite the D9/F4/H8 decorative-field anti-pattern from CSIS's own cycle history as the reason not to rush a same-day PR |
| https://platform.claude.com/docs/en/release-notes/api (agent-memory-2026-07-22 header) | 2026-08-04 | deferred | reconsidered — still no live `csis/memory/` integration point to change |
