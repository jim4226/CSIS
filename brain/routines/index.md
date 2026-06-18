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
| https://www.anthropic.com/research/claude-code-expertise | 2026-06-18 | opened-PR | PR #65: verifier-calibration-history — CalibrationHistory + verifier_confidence field (P1.5 data layer) |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-18 | deferred | Robotics research; weak Theme 6 match; no actionable CSIS change until physical substrate is modelled |
| https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem | 2026-06-18 | out-of-scope | Business/organizational news |
| https://www.anthropic.com/news/fable-mythos-access | 2026-06-18 | out-of-scope | External regulatory action; no internal CSIS pattern |
| https://www.anthropic.com/news/anthropic-public-record | 2026-06-18 | out-of-scope | Public opinion polling; no agent/eval methodology |
| https://www.anthropic.com/news/tcs-anthropic-partnership | 2026-06-18 | out-of-scope | Business partnership |
| https://www.anthropic.com/news/claude-corps | 2026-06-18 | out-of-scope | Fellowship program; no technical architecture |
