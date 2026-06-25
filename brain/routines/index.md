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
| https://www.anthropic.com/research/claude-code-expertise | 2026-06-16 | out-of-scope | Economic/observational research; prior run judged no code-change surface. This run flagged potential Theme 5/7 touch in csis/curiosity.py — see 2026-06-25.md. |
| https://www.anthropic.com/research/project-fetch-phase-two | 2026-06-18 | deferred | Robotics research validates T2+ tier gates; design sketch: tier-violation counter in capability.py. Confirm coordinator.py event emission before opening. |
| https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem | 2026-06-22 | out-of-scope | Business/geographic expansion; no CSIS theme mapping. |
| https://www.anthropic.com/news/introducing-claude-tag | 2026-06-23 | opened-PR | Deferred 2026-06-23 (memory domain isolation); reconsidered 2026-06-24 → PR #72 (memory-domain-guard). |
