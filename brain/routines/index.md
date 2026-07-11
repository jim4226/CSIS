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
| https://platform.claude.com/docs/en/release-notes/overview#agent-memory-2026-07-22 | 2026-07-11 | opened-PR | `agent-memory-2026-07-22` memory-listing beta header → PR #97. |
| https://www.anthropic.com/research/off-switch-dual-use | 2026-07-11 | out-of-scope | Already covered by PR #94 (2026-07-08, GRAM research note); not re-opened. |
| https://www.anthropic.com/news/fable-safeguards-jailbreak-framework | 2026-07-11 | out-of-scope | Already covered — see PRs #83/#85 (`tripwire-severity-score`, opened 2026-07-01 and 2026-07-02, apparent duplicate pair for this same item; see 2026-07-11 log "Operational note"). |
| https://www.anthropic.com/news/reflect-with-claude | 2026-07-11 | out-of-scope | Consumer Claude.ai UI feature, no theme mapping. |
| https://www.anthropic.com/news/hard-questions | 2026-07-11 | out-of-scope | Public-engagement/policy initiative, no theme mapping. |
| https://www.anthropic.com/news/ben-bernanke | 2026-07-11 | out-of-scope | Corporate governance news, no theme mapping. |
| https://www.anthropic.com/news/ust-claude | 2026-07-11 | out-of-scope | Customer case study, no theme mapping. |
| https://www.anthropic.com/news/alberta-government-claude-cybersecurity | 2026-07-11 | out-of-scope | Customer case study (cybersecurity vuln-finding); not a new Anthropic primitive. |
| https://www.anthropic.com/research/global-workspace | 2026-07-11 | out-of-scope | Single-model interpretability finding (J-space); explicitly not multi-agent coordination. |
| https://platform.claude.com/docs/en/release-notes/overview#api-key-expiration | 2026-07-11 | out-of-scope | Console/API-key-management feature, no theme mapping. |
| https://platform.claude.com/docs/en/release-notes/overview#cmek-content-preservation | 2026-07-11 | out-of-scope | Enterprise compliance/audit-log docs, no CSIS touchpoint. |
| https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md | 2026-07-11 | out-of-scope | Undated entries; can't be windowed reliably. No unambiguous new in-scope item found. |
