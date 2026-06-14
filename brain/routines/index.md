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
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-14 | opened-PR | PR #57: fable/mythos checkpoint labels in _DEFAULT_MODEL_MAP |
| https://www.anthropic.com/research/agents-in-biology | 2026-06-14 | deferred | Deterministic retrieval layer → DeterministicGrader protocol; needs AST-vs-regex design decision |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-14 | out-of-scope | Pure chemistry domain benchmarking; no CSIS theme |
| https://www.anthropic.com/news/claude-corps | 2026-06-14 | out-of-scope | Community/workforce program; no CSIS theme |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-14 | out-of-scope | Business partnership; no CSIS theme |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-14 | out-of-scope | Business partnership; no CSIS theme |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-14 | out-of-scope | Government policy statement; no CSIS theme |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-14 | out-of-scope | Corporate governance; no CSIS theme |
