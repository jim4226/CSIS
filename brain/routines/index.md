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
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-17 | opened-PR | GRAM dual-use knowledge off-switch — PR #105 |
| https://platform.claude.com/docs/en/release-notes/api#dreams-fable5-sonnet5 | 2026-07-17 | opened-PR | Dreams adds Fable 5 / Sonnet 5 support — PR #106 |
| https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages | 2026-07-17 | out-of-scope | No multi-turn conversation state in CSIS's backend calls |
| https://platform.claude.com/docs/en/api/admin | 2026-07-17 | out-of-scope | Org/people management, no theme mapping |
| https://platform.claude.com/docs/en/manage-claude/access-transparency | 2026-07-17 | out-of-scope | Compliance/audit docs, not a CSIS-consumed primitive |
| https://platform.claude.com/docs/en/manage-claude/authentication#key-expiration | 2026-07-17 | out-of-scope | Console/account admin, no theme mapping |
| https://www.anthropic.com/research (Claude's values across models and languages) | 2026-07-17 | out-of-scope | Interpretability research, no code hook |
| https://www.anthropic.com/news (Claude for Teachers) | 2026-07-17 | out-of-scope | Consumer/education product |
| https://www.anthropic.com/news ($10M Canadian AI research) | 2026-07-17 | out-of-scope | Corporate funding announcement |
| https://www.anthropic.com/news (UST bringing Claude to physical AI) | 2026-07-17 | out-of-scope | Customer case study |
| https://www.anthropic.com/news (Inviting hard questions) | 2026-07-17 | out-of-scope | Public-engagement initiative |
| https://www.anthropic.com/news (Ben Bernanke appointed to Long-Term Benefit Trust) | 2026-07-17 | out-of-scope | Governance appointment |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-17 | out-of-scope | Consumer claude.ai UI feature |
| https://www.anthropic.com/research (Claude plays robotics) | 2026-07-17 | out-of-scope | Robotics capability eval, no domain fit |
| https://www.anthropic.com/news (How Canada uses Claude) | 2026-07-17 | out-of-scope | Economic Index report |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md#v2.1.212 | 2026-07-17 | out-of-scope | Harness bug fixes, not a CSIS-adoptable capability |
