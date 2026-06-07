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
| https://platform.claude.com/docs/en/release-notes/overview | 2026-06-07 | opened-PR | Advisor tool max_tokens update (June 2) → PR #39 advisor-tool-builder |
| https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool | 2026-06-07 | opened-PR | Full advisor tool docs — same PR #39 |
| https://code.claude.com/docs/en/whats-new/2026-w22.md | 2026-06-07 | opened-PR | Security guidance plugin tiered-review → PR #40 tiered-audit-precheck |
| https://code.claude.com/docs/en/security-guidance.md | 2026-06-07 | opened-PR | Security guidance plugin docs — same PR #40 |
| https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes | 2026-06-07 | deferred | Self-hosted sandboxes on AWS — medium size, maps to ROADMAP P1.2 |
| https://www.anthropic.com/news/services-track-partner-hub | 2026-06-07 | out-of-scope | Business partner program announcement |
| https://www.anthropic.com/news/AI-enabled-cyber-threats-mitre-attack | 2026-06-07 | out-of-scope | Threat research report; observational, no actionable CSIS change |
| https://www.anthropic.com/news/expanding-project-glasswing | 2026-06-07 | out-of-scope | External defensive cybersecurity program |
| https://www.anthropic.com/news/confidential-draft-s1-sec | 2026-06-07 | out-of-scope | Corporate finance event |
| https://www.anthropic.com/research/making-claude-a-chemist | 2026-06-07 | out-of-scope | Domain-specific chemistry research |
| https://code.claude.com/docs/en/workflows.md | 2026-06-07 | out-of-scope | Already covered by PR #23 (dynamic-workflow-tripwire 2026-05-29) |
