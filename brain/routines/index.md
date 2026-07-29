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
| https://platform.claude.com/docs/en/release-notes/api (mid-conversation tool changes, 2026-07-24) | 2026-07-29 | deferred | Blocked on `LLMRequest.tools` actually being wired into `AnthropicBackend.complete()`. |
| https://platform.claude.com/docs/en/release-notes/api (Managed Agents memory-store webhooks + per-agent effort, 2026-07-22) | 2026-07-29 | deferred | Blocked on ROADMAP P1.1 (real Managed Agents / Dreams API integration). |
| https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback (`fallbacks: "default"`, 2026-07-24) | 2026-07-29 | deferred | Refusal classifiers only run on Fable 5 / Opus 5; CSIS's checkpoint map still points at Opus 4.7 / Sonnet 4.6. |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-07-29 | deferred | Hypothesis→experiment→verify scaffold; candidate `hypothesis` field for `csis/curiosity.py` `FrontierItem`. |
| https://www.anthropic.com/research/project-pilot | 2026-07-29 | deferred | Multi-run consistency data point reinforcing ROADMAP P1.4 (V4 replication verification); no new code surface. |
| https://www.anthropic.com/news/claude-opus-5 | 2026-07-29 | out-of-scope | Model launch, no theme mapping. |
| https://platform.claude.com/docs/en/release-notes/api (Opus 4.7 fast mode removal, 2026-07-24) | 2026-07-29 | out-of-scope | Pricing/perf flag CSIS doesn't set. |
| https://www.anthropic.com/news/position-open-weights-models | 2026-07-29 | out-of-scope | Policy position, not technical. |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-07-29 | out-of-scope | Enterprise/business announcement. |
| https://www.anthropic.com/news/economic-futures-research-fund-agenda | 2026-07-29 | out-of-scope | Economic research program. |
| https://www.anthropic.com/news/anthropic-economic-index-connector | 2026-07-29 | out-of-scope | claude.ai consumer connector feature. |
| https://www.anthropic.com/news/donation-public-first-action | 2026-07-29 | out-of-scope | Philanthropy announcement. |
| https://www.anthropic.com/news/rare-disease-research-grants | 2026-07-29 | out-of-scope | Grant program announcement. |
| https://code.claude.com/docs/en/changelog (v2.1.216–2.1.220, 2026-07-20→25) | 2026-07-29 | out-of-scope | Claude Code host features, not primitives CSIS's standalone Python system consumes. |
| https://platform.claude.com/docs/en/release-notes/api (Managed Agents session ergonomics, 2026-07-22) | 2026-07-29 | out-of-scope | API ergonomics for a surface CSIS doesn't call yet. |
