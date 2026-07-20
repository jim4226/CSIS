# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| https://www.anthropic.com/news/rare-disease-research-grants | 2026-07-20 | out-of-scope | Grant program announcement |
| https://www.anthropic.com/news/claude-for-teachers | 2026-07-20 | out-of-scope | Consumer/education product launch |
| https://www.anthropic.com/news/canadian-ai-research | 2026-07-20 | out-of-scope | Funding announcement |
| https://www.anthropic.com/research/how-canada-uses-claude | 2026-07-20 | out-of-scope | Economic-impact research |
| https://www.anthropic.com/research/claude-values-models-languages | 2026-07-20 | out-of-scope | Observational value-drift study; no code primitive |
| https://platform.claude.com/docs/en/release-notes/overview#july-17-2026 | 2026-07-20 | out-of-scope | Workbench sunset, unused by CSIS |
| https://platform.claude.com/docs/en/release-notes/overview#july-15-2026 | 2026-07-20 | out-of-scope | Mid-conversation system messages; no multi-turn state in CSIS backend to attach to |
| https://platform.claude.com/docs/en/release-notes/overview#july-14-2026 | 2026-07-20 | out-of-scope | Admin API user management, no admin surface in CSIS |
| https://code.claude.com/docs/en/whats-new/2026-w29 | 2026-07-20 | out-of-scope | CLI/product surface features; trust-lattice equivalent already enforced in CSIS code |
