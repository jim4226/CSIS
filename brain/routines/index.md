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
| https://www.anthropic.com/research/agents-in-biology | 2026-06-17 | opened-PR | PR #63 (context-engine-domain-protocol); additive to PR #42 (grader-provenance-layer, 2026-06-08) — different CSIS surface |
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-17 | reconsidered-skipped | Already covered by PRs #44/#49/#57 across three prior runs |
| https://www.anthropic.com/research/claude-code-expertise | 2026-06-17 | out-of-scope | Economic/observational study; no CSIS code surface |
| https://www.anthropic.com/research/n-days | 2026-06-17 | out-of-scope | Offensive security research; no CSIS theme match |
| https://www.anthropic.com/news/claude-corps | 2026-06-17 | out-of-scope | Policy/workforce program; no technical content |
| https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem | 2026-06-17 | out-of-scope | Business announcement |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-17 | out-of-scope | Government policy directive; no technical content |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-17 | out-of-scope | Transparency report; no CSIS theme match |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-17 | out-of-scope | Business partnership; no technical content |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-17 | out-of-scope | Business partnership; no technical content |
