# CSIS routine index — URL ledger

This file is the durable cross-run memory for `.claude/routines/daily-improvement.md`. Every URL the routine has ever considered appears here exactly once, with the date of first sighting and the action taken. The routine reads this file first thing every morning to avoid re-considering items already triaged.

Status values:

- `opened-PR` — a draft PR was opened for this item; do not reconsider unless the PR was closed without merging
- `deferred` — design sketch only; eligible for reconsideration on any later run with a status of `reconsidered`
- `out-of-scope` — doesn't map to a CSIS theme; do not reconsider
- `quiet-day-empty` — placeholder row used on days when no in-window items were found (URL field reads `(none)`)

| URL | First seen | Status | Notes |
|---|---|---|---|
| https://www.anthropic.com/research/glasswing-initial-update | 2026-05-23 | opened-PR | PR #8 — glasswing frontier ranking (Theme 7) |
| https://www.anthropic.com/news/widening-conversation-ai | 2026-05-24 | opened-PR | PRs #10, #18 — ValueReminderTool + Constitution.reminder() (Theme 3) |
| https://code.claude.com/docs/en/changelog#v2.1.145 | 2026-05-25 | opened-PR | PR #12 — event-span-agent-ids (Theme 1+2) |
| https://code.claude.com/docs/en/changelog#v2.1.147 | 2026-05-25 | opened-PR | PR #13 — critic-effort-levels (Theme 5) |
| https://code.claude.com/docs/en/changelog#v2.1.149 | 2026-05-25 | out-of-scope | CLI security fixes; not CSIS permission model |
| https://code.claude.com/docs/en/changelog#v2.1.150 | 2026-05-25 | out-of-scope | Internal infra; no CSIS theme |
| https://www.anthropic.com/engineering/how-we-contain-claude | 2026-05-26 | opened-PR | PR #15 — external-content-layer (Theme 3+6) |
| https://code.claude.com/docs/en/agent-sdk/overview | 2026-05-26 | opened-PR | PR #16 — domain-system-prompt (Theme 1+6) |
| https://platform.claude.com/docs/en/managed-agents/overview | 2026-05-26 | deferred | Maps to ROADMAP P1.1; blocked on operator access confirmation |
| https://www.anthropic.com/news/claude-opus-4-8 | 2026-05-28 | opened-PR | PR #20 — opus-4-8-effort (Theme 6+2) |
| https://www.anthropic.com/research/coding-agents-social-sciences | 2026-05-28 | out-of-scope | Adoption demographics study; no CSIS theme |
| https://code.claude.com/docs/en/changelog#v2.1.157 | 2026-05-29 | opened-PR | PR #22 — event-tool-parameters (Theme 2) |
| https://code.claude.com/docs/en/changelog#v2.1.154 | 2026-05-29 | opened-PR | PR #23 — dynamic-workflow-tripwire (Theme 3); deferred: dynamic-workflows-orchestration (Theme 1) |
| https://www.anthropic.com/news/series-h | 2026-05-29 | out-of-scope | Series H fundraising; business news |
| https://www.anthropic.com/news/milan-office-opening | 2026-05-29 | out-of-scope | Geographic expansion |
| https://www.anthropic.com/news/kiyoung-choi-representative-director-anthropic-korea | 2026-05-29 | out-of-scope | Personnel announcement |
| https://www.anthropic.com/news/chris-olah-pope-leo-encyclical | 2026-05-29 | out-of-scope | Cultural commentary |
| https://www.anthropic.com/news/anthropic-kpmg | 2026-05-29 | out-of-scope | Enterprise partnership |
