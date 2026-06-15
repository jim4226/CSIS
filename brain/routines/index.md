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
| https://www.anthropic.com/news/claude-fable-5-mythos-5 | 2026-06-15 | opened-PR | Fable 5 tripwire retention → PR #60; also informed PR #59 (self-reflection / trace) |
| https://www.anthropic.com/research/agents-in-biology | 2026-06-15 | opened-PR | Grader execution traces → PR #59; deterministic retrieval sub-insight deferred |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-15 | out-of-scope | Public opinion survey; no technical content |
| https://www.anthropic.com/news/claude-corps | 2026-06-15 | out-of-scope | Fellowship program; no technical content |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-15 | out-of-scope | Policy/export-control document; no new safety primitives |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-15 | out-of-scope | Business partnership |
| https://www.anthropic.com/news/dxc-anthropic-alliance | 2026-06-15 | out-of-scope | Business partnership |
| https://code.claude.com/docs/en/routines | 2026-06-15 | out-of-scope | Documents CSIS's own routine infrastructure; no code change needed |
