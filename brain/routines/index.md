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
| https://www.anthropic.com/news/redeploying-fable-5 | 2026-07-01 | opened-PR | Jailbreak severity framework → tripwire severity scoring, PR #83. |
| https://www.anthropic.com/news/claude-sonnet-5 | 2026-07-01 | opened-PR | Re-observed; already opened as PR #81 on 2026-06-30 (see that run's log). No new action. |
| https://www.anthropic.com/news/introducing-claude-tag | 2026-07-01 | out-of-scope | Re-observed; already logged out-of-scope 2026-06-30 (consumer/admin product, no API primitive). |
| https://www.anthropic.com/news/claude-science-ai-workbench | 2026-07-01 | out-of-scope | Re-observed; already logged out-of-scope 2026-06-30 (consumer research workbench). |
| https://www.anthropic.com/research/economic-index-june-2026-report | 2026-07-01 | out-of-scope | Re-observed; already logged out-of-scope 2026-06-30 (usage-pattern research, no theme mapping). |
| https://platform.claude.com/docs/en/release-notes/overview#2026-06-30-managed-agents | 2026-07-01 | deferred | Re-observed; already logged deferred 2026-06-30 (Managed Agents API additions — event deltas, pagination, session overrides, vault injection_location, webhooks). Design sketch unchanged. |
