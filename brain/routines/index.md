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
| https://www.anthropic.com/research/agents-in-biology | 2026-06-12 | opened-PR | Reconsidered from June 11 deferred; PR #51 (grader-rng-determinism). June 8 run also opened PR #42 (grader-provenance-layer) from same URL — different angle. |
| https://code.claude.com/docs/en/changelog.md | 2026-06-12 | opened-PR | v2.1.172 depth guard → PR #52; v2.1.169 post-session hook → PR #53. Changelog page discovered via llms.txt; not scanned by prior runs. |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-12 | out-of-scope | Public opinion survey, no technical architecture content. |
| https://www.anthropic.com/news/claude-corps | 2026-06-12 | out-of-scope | Workforce development fellowship, no agent architecture content. |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-12 | out-of-scope | Business partnership announcement. |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-12 | out-of-scope | Business partnership announcement. |
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-12 | opened-PR | Reconsidered-skipped; already covered by PRs #44, #46, #49. |
