# CSIS routine index — URL ledger

This file is the merged, human-reviewed cross-run memory for `.claude/routines/daily-improvement.md`. URLs recorded by proposal-bearing runs appear here with the date of first sighting and the action taken. Open routine PRs are an additional live state layer and must be inspected before this ledger so unmerged proposals are not duplicated.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — legacy placeholder from the initial ledger; new quiet runs do not create repository artifacts

| URL | First seen | Status | Notes |
|---|---|---|---|
| (none) | (initial) | quiet-day-empty | Ledger initialized; first real entries land on the routine's first scheduled run. |
| https://www.anthropic.com/research/discovering-cryptographic-weaknesses | 2026-08-05 | opened-PR | PR #131 `curiosity-redirect-driven` |
| https://platform.claude.com/docs/en/manage-claude/inference-hooks | 2026-08-05 | deferred | Design sketch in `brain/routines/2026-08-05.md`; touches the `Coordinator.__init__` chokepoint, needs a slower look |
| Dreams now supports Claude Opus 5 (platform release note, 2026-08-01) | 2026-08-05 | out-of-scope | Model-support bump only; same pattern already covered by PR #79 and #106 |
| Claude Opus 4.1 retirement (platform release note, 2026-08-05) | 2026-08-05 | out-of-scope | Model lifecycle notice, not an engineering pattern |
| https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals | 2026-08-05 | out-of-scope | Already covered by PR #123 `cybersecurity-eval-sandbox-isolation` (2026-07-30 run) |
| https://www.anthropic.com/research/project-pilot | 2026-08-05 | out-of-scope | Embodied/robotics red-teaming; no theme match |
| https://www.anthropic.com/news/tino-cuellar | 2026-08-05 | out-of-scope | Personnel announcement |
| https://www.anthropic.com/news/position-open-weights-models | 2026-08-05 | out-of-scope | Policy position, not engineering |
| https://www.anthropic.com/news/cognizant-anthropic | 2026-08-05 | out-of-scope | Business partnership announcement |
| Claude Code changelog v2.1.221 / v2.1.222 (2026-08-04) | 2026-08-05 | out-of-scope | CLI implementation details (Focus view, sandbox masking, bug fixes); no disclosed mechanism to design against |

**Note (2026-08-05 run):** this ledger is out of sync with reality — every prior `routine log:` PR (back to #9, 2026-05-23) is still open on `main`, so none of their index/log updates ever landed here. See `brain/routines/2026-08-05.md` for the full note. Rows above are this run's additions only; treat the open-PR list as the actual source of truth for dedup until the backlog is merged.
