# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-02 | opened-PR | PR #85 — tripwire severity scoring, 4-axis jailbreak framework |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-02 | deferred | Provenance/reviewer-agent pattern — design sketch ties to ROADMAP.md P1.8 |
| https://www.anthropic.com/news/introducing-claude-tag | 2026-07-02 | out-of-scope | Consumer/Enterprise Slack product feature |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-02 | out-of-scope | New model launch; no CSIS behavior impact, routine version bookkeeping only |
| https://platform.claude.com/docs/en/release-notes/api#june-30-2026-event-deltas | 2026-07-02 | out-of-scope | Managed Agents streaming preview; CSIS agents are synchronous, not streamed |
| https://platform.claude.com/docs/en/release-notes/api#june-30-2026-session-overrides | 2026-07-02 | out-of-scope | Managed Agents per-session overrides; CSIS already has an equivalent (`model_map`) |
| https://platform.claude.com/docs/en/release-notes/api#june-30-2026-webhooks | 2026-07-02 | out-of-scope | Managed Agents webhook lifecycle events; CSIS is poll-based, no webhook receiver |
| https://platform.claude.com/docs/en/release-notes/api#june-30-2026-vaults | 2026-07-02 | out-of-scope | Managed Agents vault credential injection location; no vault system in CSIS Phase-0 |
| https://platform.claude.com/docs/en/release-notes/api#june-30-2026-pagination | 2026-07-02 | out-of-scope | Managed Agents session-listing backward pagination; pure API ergonomics |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-02 | out-of-scope | Human usage-pattern research; no agent-architecture theme match |
